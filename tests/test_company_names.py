"""Regression test: the default config.py on synthetic company names.

If you change config.py and this fails, run the full benchmark to see why:
    python benchmarks/company_names.py --compare-baseline
"""

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks"))

import company_names as cn  # noqa: E402
from fuzzy_match.config_loader import (  # noqa: E402
    load_config,
    match_kwargs_from_config,
    settings_from_config,
)


def test_default_config_on_synthetic_company_names():
    rng = random.Random(123)
    master = cn.build_master(1500, rng, lookalike_share=0.3)
    queries = cn.build_queries(master, 40, 200, rng, set(master.base.str.lower()))
    cfg = load_config(ROOT / "config.py")
    res = cn.evaluate(queries, master, settings_from_config(cfg), match_kwargs_from_config(cfg))
    pos = res[res.truth.notna()]

    assert pos.correct.mean() >= 0.95
    suffix = pos[pos.variation.str.startswith("suffix")]
    assert suffix.correct.all()
    assert suffix.score.min() >= 85


def test_split_suffix():
    assert cn.split_suffix("Acme, Inc.") == ("Acme", "inc")
    assert cn.split_suffix("Smith & Co.") == ("Smith", "co")
    assert cn.split_suffix("Vtno L.L.C.") == ("Vtno", "llc")
    assert cn.split_suffix("Costco") == ("Costco", "")
