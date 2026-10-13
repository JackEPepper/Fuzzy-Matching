from pathlib import Path

import pandas as pd
import pytest

import fuzzy_match.matcher as matcher_mod
from fuzzy_match import WeightSettings, match_dataframes
from fuzzy_match.config_loader import (
    load_config,
    match_kwargs_from_config,
    read_table,
    resolve_path,
    settings_from_config,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def frames():
    left = pd.DataFrame({"id": [1, 2, 3, 4], "name": ["Acme, Inc.", "Globex", None, "Zzzz"]})
    right = pd.DataFrame(
        {
            "rid": ["a", "b", "c", "d"],
            "company": ["ACME INC", "Globex Corp", "acme inc", "Initech"],
            "state": ["CO", "IL", "CO", "TX"],
        }
    )
    return left, right


def test_basic_match_and_output_columns(frames):
    left, right = frames
    out = match_dataframes(left, right, "name", "company", keep_left="id", keep_right=["rid"],
                           min_score=50, show_progress=False)
    assert list(out.columns) == [
        "left_index", "left_name", "left_id", "left_normalized",
        "right_index", "right_company", "right_rid", "right_normalized",
        "match_rank", "match_score",
    ]
    acme = out[out.left_id == 1]
    # Both right rows normalize to "acme inc" so they share rank 1
    assert sorted(acme.right_rid) == ["a", "c"]
    assert (acme.match_rank == 1).all()
    assert out[out.left_id == 2].right_rid.iloc[0] == "b"


def test_unmatched_and_blank_rows_kept_or_dropped(frames):
    left, right = frames
    out = match_dataframes(left, right, "name", "company", min_score=90, show_progress=False)
    assert set(out.left_index) == {0, 1, 2, 3}
    assert out[out.left_index == 3].match_rank.isna().all()

    out = match_dataframes(left, right, "name", "company", min_score=90,
                           include_unmatched=False, show_progress=False)
    assert 2 not in set(out.left_index) and 3 not in set(out.left_index)


def test_top_n(frames):
    left, right = frames
    out = match_dataframes(left, right, "name", "company", top_n=3, show_progress=False)
    globex = out[out.left_index == 1]
    assert globex.match_rank.max() <= 3
    assert globex.match_score.is_monotonic_decreasing


def test_blocking_restricts_comparisons(frames):
    left, right = frames
    left = left.assign(state=["IL", "IL", "IL", "IL"])
    out = match_dataframes(left, right, "name", "company", block_on=("state", "state"),
                           keep_right="state", show_progress=False)
    assert set(out.right_state.dropna()) == {"IL"}


def test_duplicate_index_labels_are_fine(frames):
    left, right = frames
    left.index = [0, 0, 0, 0]
    right.index = [5, 5, 5, 5]
    out = match_dataframes(left, right, "name", "company", keep_left="id", show_progress=False)
    assert out[out.left_id == 2].right_company.iloc[0] == "Globex Corp"


def test_candidates_none_compares_everything(frames):
    left, right = frames
    a = match_dataframes(left, right, "name", "company", candidates_per_row=None, show_progress=False)
    b = match_dataframes(left, right, "name", "company", candidates_per_row=1, show_progress=False)
    assert a.match_score.max() == b.match_score.max()


def test_pure_python_fallback(frames, monkeypatch):
    monkeypatch.setattr(matcher_mod, "_rf_process", None)
    left, right = frames
    out = match_dataframes(left, right, "name", "company", candidates_per_row=2, show_progress=False)
    assert out[out.left_index == 1].right_company.iloc[0] == "Globex Corp"


def test_missing_column_raises(frames):
    left, right = frames
    with pytest.raises(KeyError):
        match_dataframes(left, right, "nope", "company", show_progress=False)


def test_example_config_runs_end_to_end():
    cfg = load_config(ROOT / "config.py")
    left = read_table(resolve_path(cfg, cfg.LEFT_FILE))
    right = read_table(resolve_path(cfg, cfg.RIGHT_FILE))
    out = match_dataframes(left, right, settings=settings_from_config(cfg), show_progress=False,
                           **match_kwargs_from_config(cfg))
    best = out[out.match_rank == 1].set_index("left_customer_id").right_vendor_id
    assert best["C003"] == "V103"   # Initech LLC -> Initech
    assert best["C006"] == "V107"   # W4yne -> Wayne
    assert best["C010"] == "V111"   # Vandelay -> Vandalay
    assert "C012" not in best.index  # nothing similar


def test_cli_try(capsys):
    import run_match
    assert run_match.main(["--try", "Acme, Inc.", "ACME INC"]) == 0
    assert "score:" in capsys.readouterr().out


def test_prefilter_keeps_word_boundaries():
    s = WeightSettings(char_class_weights={"whitespace": 0.2, "punctuation": 0.1})
    assert matcher_mod._prefilter_text("turner manufacturing, corp", s) == "turner manufacturing corp"


def test_multiple_prefilter_scorers_find_glued_and_reordered_names():
    right = pd.DataFrame({"company": [f"Filler Company {i}" for i in range(50)]
                          + ["Reed Electric", "Baker Packaging"]})
    left = pd.DataFrame({"name": ["ReedElectric", "Packaging Baker"]})
    s = WeightSettings(char_class_weights={"whitespace": 0.2}, compare_sorted_words=True)
    out = match_dataframes(left, right, "name", "company", settings=s,
                           candidates_per_row=2, show_progress=False)
    assert list(out.right_company) == ["Reed Electric", "Baker Packaging"]
