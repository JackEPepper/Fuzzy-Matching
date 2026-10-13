"""Weighted fuzzy matching of two DataFrame columns.

Quick use from Python / a notebook:

    import pandas as pd
    from fuzzy_match import WeightSettings, match_dataframes, similarity, explain

    settings = WeightSettings(char_class_weights={"punctuation": 0.1})
    result = match_dataframes(left_df, right_df, "name", "company_name",
                              settings=settings, top_n=3, min_score=80)
"""

from .config_loader import load_config, settings_from_config
from .matcher import match_dataframes
from .scoring import WeightSettings, explain, normalize, similarity

__all__ = [
    "WeightSettings",
    "explain",
    "load_config",
    "match_dataframes",
    "normalize",
    "settings_from_config",
    "similarity",
]
