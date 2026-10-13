"""
Using the matcher directly from Python / Jupyter, when you already have
DataFrames in memory (e.g. pulled from a database).

Run from the repo root:  python examples/use_in_python.py
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so "fuzzy_match" imports
from fuzzy_match import WeightSettings, explain, match_dataframes, similarity  # noqa: E402

left = pd.DataFrame({"id": [1, 2, 3], "name": ["Acme, Inc.", "W4yne Enterprises", "Pied-Piper"]})
right = pd.DataFrame({"vid": ["a", "b", "c"], "vendor": ["ACME INC", "Wayne Enterprises", "Pied Piper"]})

# Option A: define the settings right here ...
settings = WeightSettings(
    char_class_weights={"punctuation": 0.1, "whitespace": 0.2},
    char_weights={"-": 0.0},
    word_weights={"inc": 0.2, "llc": 0.2},
    substitution_costs={("4", "a"): 0.3},
)

# ... or Option B: reuse everything in config.py
# from fuzzy_match import load_config, settings_from_config
# settings = settings_from_config(load_config("config.py"))

# Check a single pair while tuning:
print(similarity("Acme, Inc.", "ACME INC", settings))
print(explain("W4yne Enterprises", "Wayne Enterprises", settings))

result = match_dataframes(
    left, right,
    left_on="name", right_on="vendor",
    settings=settings,
    top_n=2, min_score=70,
    keep_left=["id"], keep_right=["vid"],
)
print(result.to_string())
