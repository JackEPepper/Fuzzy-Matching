"""Load a ``config.py``-style settings file and read/write data files."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, Optional

import pandas as pd

from .scoring import WeightSettings


def load_config(path) -> ModuleType:
    """Import a Python config file from any path (e.g. ``my_config.py``)."""
    path = Path(path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    spec = importlib.util.spec_from_file_location("fuzzy_match_user_config", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    module.__config_dir__ = path.parent  # used to resolve relative file paths
    return module


def _get(cfg: ModuleType, name: str, default: Any) -> Any:
    return getattr(cfg, name, default)


def settings_from_config(cfg: ModuleType) -> WeightSettings:
    """Build WeightSettings from the UPPER_CASE names in a config module."""
    return WeightSettings(
        case_sensitive=_get(cfg, "CASE_SENSITIVE", False),
        strip_accents=_get(cfg, "STRIP_ACCENTS", True),
        collapse_whitespace=_get(cfg, "COLLAPSE_WHITESPACE", True),
        collapse_acronyms=_get(cfg, "COLLAPSE_ACRONYMS", True),
        replacements=dict(_get(cfg, "REPLACEMENTS", {})),
        word_replacements=dict(_get(cfg, "WORD_REPLACEMENTS", {})),
        regex_replacements=dict(_get(cfg, "REGEX_REPLACEMENTS", {})),
        default_char_weight=_get(cfg, "DEFAULT_CHARACTER_WEIGHT", 1.0),
        char_class_weights=dict(_get(cfg, "CHARACTER_CLASS_WEIGHTS", {})),
        char_weights=dict(_get(cfg, "CHARACTER_WEIGHTS", {})),
        word_weights=dict(_get(cfg, "WORD_WEIGHTS", {})),
        substitution_costs=dict(_get(cfg, "SUBSTITUTION_COSTS", {})),
        transposition_cost=_get(cfg, "TRANSPOSITION_COST", 1.0),
        compare_sorted_words=_get(cfg, "COMPARE_SORTED_WORDS", False),
        sorted_words_penalty=_get(cfg, "SORTED_WORDS_PENALTY", 5.0),
    )


def match_kwargs_from_config(cfg: ModuleType) -> Dict[str, Any]:
    """Keyword arguments for ``match_dataframes`` from a config module."""
    return dict(
        left_on=cfg.LEFT_COLUMN,
        right_on=cfg.RIGHT_COLUMN,
        top_n=_get(cfg, "TOP_N", 1),
        min_score=_get(cfg, "MIN_SCORE", 0),
        candidates_per_row=_get(cfg, "CANDIDATES_PER_ROW", 10),
        prefilter_scorer=_get(cfg, "PREFILTER_SCORER", ("token_sort_ratio", "ratio")),
        block_on=_get(cfg, "BLOCK_ON", None),
        keep_left=_get(cfg, "KEEP_LEFT_COLUMNS", None),
        keep_right=_get(cfg, "KEEP_RIGHT_COLUMNS", None),
        include_unmatched=_get(cfg, "INCLUDE_UNMATCHED", True),
        include_normalized=_get(cfg, "INCLUDE_NORMALIZED_TEXT", True),
    )


def resolve_path(cfg: ModuleType, path) -> Path:
    """Relative paths in the config are relative to the config file."""
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = Path(getattr(cfg, "__config_dir__", ".")) / p
    return p


def read_table(path, options: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
    """Read CSV / TSV / TXT / Excel / Parquet based on the file extension.

    ``options`` are passed straight to the pandas reader, e.g.
    {"sheet_name": "Data"} or {"encoding": "latin-1"}. By default every
    column is read as text so IDs like "00123" keep their leading zeros.
    """
    path = Path(path)
    opts = dict(options or {})
    suffix = path.suffix.lower()
    if suffix in (".csv",):
        opts.setdefault("dtype", str)
        opts.setdefault("keep_default_na", False)
        return pd.read_csv(path, **opts)
    if suffix in (".tsv", ".txt"):
        opts.setdefault("dtype", str)
        opts.setdefault("keep_default_na", False)
        opts.setdefault("sep", "\t")
        return pd.read_csv(path, **opts)
    if suffix in (".xlsx", ".xlsm", ".xls"):
        opts.setdefault("dtype", str)
        return pd.read_excel(path, **opts)
    if suffix == ".parquet":
        return pd.read_parquet(path, **opts)
    raise ValueError(f"Don't know how to read {suffix!r} files: {path}")


def write_table(df: pd.DataFrame, path) -> None:
    """Write CSV or Excel based on the file extension."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        df.to_excel(path, index=False)
    elif suffix == ".parquet":
        df.to_parquet(path, index=False)
    else:
        df.to_csv(path, index=False)
