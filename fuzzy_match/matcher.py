"""
Match one column of a "left" DataFrame against one column of a "right"
DataFrame using the weighted score from ``scoring.py``.

How it works (two passes, for speed):

1. CANDIDATES - a fast, standard fuzzy scorer (rapidfuzz, if installed)
   picks the ``candidates_per_row`` most promising right-side values for
   each left value (using all CPU cores). Low-weight characters/words are stripped first so they
   don't distract this pass.
2. RESCORE - each candidate is scored with the weighted edit distance, and
   the best ``top_n`` at or above ``min_score`` are kept.

Set ``candidates_per_row=None`` to skip pass 1 and compare every pair
(exact but slow: left x right comparisons).

Duplicate values are only scored once, so repeated names are cheap.
"""

from __future__ import annotations

import difflib
import heapq
import sys
import time
from typing import Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

from .scoring import WeightSettings, normalize, position_weights, similarity_normalized

try:  # rapidfuzz is optional but MUCH faster for the candidate pass
    from rapidfuzz import fuzz as _rf_fuzz
    from rapidfuzz import process as _rf_process
except ImportError:  # pragma: no cover - depends on environment
    _rf_fuzz = None
    _rf_process = None

# In the candidate pass, characters whose weight is below this are removed,
# so e.g. punctuation or "inc"/"llc" don't drive which candidates are picked.
PREFILTER_DROP_BELOW = 0.5

ColumnList = Union[None, str, Sequence[str]]


def _prefilter_text(text: str, settings: WeightSettings) -> str:
    weights = position_weights(text, settings)
    kept = "".join(c for c, w in zip(text, weights) if w >= PREFILTER_DROP_BELOW)
    kept = " ".join(kept.split())
    return kept or text


def _find_candidates_batch(
    queries: List[str],
    choices: List[str],
    limit: Optional[int],
    scorer: str,
) -> List[List[int]]:
    """For each query, indices into ``choices`` of the most promising candidates."""
    if limit is None or limit <= 0 or limit >= len(choices):
        return [list(range(len(choices)))] * len(queries)

    if _rf_process is not None:
        scorer_fn = getattr(_rf_fuzz, scorer)
        out: List[List[int]] = []
        # Score in chunks so memory stays small (chunk x len(choices) bytes).
        chunk = max(1, 20_000_000 // max(1, len(choices)))
        for start in range(0, len(queries), chunk):
            scores = _rf_process.cdist(
                queries[start:start + chunk], choices,
                scorer=scorer_fn, dtype=np.uint8, workers=-1,
            )
            top = np.argpartition(-scores.astype(np.int16), limit - 1, axis=1)[:, :limit]
            out.extend(top.tolist())
        return out

    # Pure-Python fallback (much slower) if rapidfuzz isn't installed.
    out = []
    matcher = difflib.SequenceMatcher(autojunk=False)
    for query in queries:
        matcher.set_seq2(query)
        scored = []
        for idx, choice in enumerate(choices):
            matcher.set_seq1(choice)
            scored.append((matcher.ratio(), idx))
        out.append([idx for _r, idx in heapq.nlargest(limit, scored)])
    return out


def _resolve_columns(df: pd.DataFrame, cols: ColumnList, always: str) -> List[str]:
    if cols is None:
        selected: List[str] = []
    elif isinstance(cols, str):
        selected = list(df.columns) if cols == "all" else [cols]
    else:
        selected = list(cols)
    missing = [c for c in selected if c not in df.columns]
    if missing:
        raise KeyError(f"Columns not found: {missing}. Available: {list(df.columns)}")
    return [always] + [c for c in selected if c != always]


def _progress(done: int, total: int, start: float, enabled: bool) -> None:
    if not enabled or total < 500:  # small jobs finish instantly
        return
    step = max(1, total // 20)  # roughly every 5%
    if done % step == 0 or done == total:
        elapsed = time.time() - start
        print(
            f"  matched {done:,}/{total:,} unique values ({100 * done / total:.0f}%) "
            f"- {elapsed:,.1f}s",
            file=sys.stderr,
        )


def match_dataframes(
    left: pd.DataFrame,
    right: pd.DataFrame,
    left_on: str,
    right_on: str,
    settings: Optional[WeightSettings] = None,
    top_n: int = 1,
    min_score: float = 0.0,
    candidates_per_row: Optional[int] = 10,
    prefilter_scorer: str = "token_sort_ratio",
    block_on: Optional[Tuple[str, str]] = None,
    keep_left: ColumnList = None,
    keep_right: ColumnList = None,
    include_unmatched: bool = True,
    include_normalized: bool = True,
    show_progress: bool = True,
) -> pd.DataFrame:
    """Fuzzy-match ``left[left_on]`` against ``right[right_on]``.

    Parameters
    ----------
    left, right : DataFrames to match.
    left_on, right_on : names of the text columns to compare.
    settings : WeightSettings controlling normalization & weights.
    top_n : how many matches to return per left row.
    min_score : drop matches scoring below this (0-100).
    candidates_per_row : size of the fast candidate pass (None = compare all).
    prefilter_scorer : rapidfuzz.fuzz scorer used for the candidate pass:
        "token_sort_ratio" (default, fast, ignores word order), "ratio",
        "token_set_ratio", "partial_ratio" or "WRatio" (best, but slow).
    block_on : optional (left_col, right_col); only rows with EXACTLY equal
        values in these columns are compared (e.g. same state / zip code).
        Greatly speeds up big jobs.
    keep_left, keep_right : extra columns to copy into the output
        (a name, a list of names, or "all").
    include_unmatched : keep left rows with no match (right side left blank).
    include_normalized : add the normalized text that was actually compared.
    show_progress : print progress to stderr.

    Returns
    -------
    DataFrame with one row per (left row, match). Columns:
        left_index, left_<cols...>, right_index, right_<cols...>,
        match_rank (1 = best), match_score (0-100)
    If several right rows have identical normalized text they share a rank.
    """
    settings = settings or WeightSettings()
    for df, col, side in ((left, left_on, "left"), (right, right_on, "right")):
        if col not in df.columns:
            raise KeyError(f"{side} column {col!r} not found. Available: {list(df.columns)}")
    if block_on is not None:
        if block_on[0] not in left.columns or block_on[1] not in right.columns:
            raise KeyError(f"block_on columns {block_on} not found")

    left_cols = _resolve_columns(left, keep_left, left_on)
    right_cols = _resolve_columns(right, keep_right, right_on)

    left_norm = left[left_on].map(lambda v: normalize(v, settings))
    right_norm = right[right_on].map(lambda v: normalize(v, settings))
    left_block = left[block_on[0]] if block_on else pd.Series(0, index=left.index)
    right_block = right[block_on[1]] if block_on else pd.Series(0, index=right.index)

    # --- Build the right-side lookup, grouped by block -------------------- #
    # block -> (unique normalized texts, their prefilter texts,
    #           right row POSITIONS for each unique text)
    right_groups: Dict[object, Tuple[List[str], List[str], List[List[int]]]] = {}
    seen: Dict[Tuple[object, str], int] = {}  # (block, text) -> index in group
    for pos, (text, block) in enumerate(zip(right_norm, right_block)):
        if not text:
            continue
        texts, pre, rows = right_groups.setdefault(block, ([], [], []))
        key = (block, text)
        if key in seen:
            rows[seen[key]].append(pos)
        else:
            seen[key] = len(texts)
            texts.append(text)
            pre.append(_prefilter_text(text, settings))
            rows.append([pos])

    # --- Score each unique (block, left text) once ------------------------ #
    left_by_block: Dict[object, List[str]] = {}
    for block, text in dict.fromkeys(zip(left_block, left_norm)):
        if text:
            left_by_block.setdefault(block, []).append(text)
    total = sum(len(v) for v in left_by_block.values())
    if show_progress:
        print(f"Matching {total:,} unique left values...", file=sys.stderr)
        if _rf_process is None and candidates_per_row:
            print("  (rapidfuzz not installed - using slower pure-Python search)", file=sys.stderr)

    results: Dict[Tuple[object, str], List[Tuple[float, int]]] = {}
    start = time.time()
    done = 0
    for block, left_texts in left_by_block.items():
        group = right_groups.get(block)
        if group is None:
            done += len(left_texts)
            continue
        texts, pre, _rows = group
        candidate_lists = _find_candidates_batch(
            [_prefilter_text(t, settings) for t in left_texts], pre,
            candidates_per_row, prefilter_scorer,
        )
        for text, candidates in zip(left_texts, candidate_lists):
            matches: List[Tuple[float, int]] = []
            for idx in candidates:
                score = similarity_normalized(text, texts[idx], settings)
                if score >= min_score:
                    matches.append((score, idx))
            matches.sort(key=lambda m: (-m[0], m[1]))
            results[(block, text)] = matches[:top_n]
            done += 1
            _progress(done, total, start, show_progress)

    # --- Assemble output -------------------------------------------------- #
    left_records = left[left_cols].to_dict("records")
    right_records = right[right_cols].to_dict("records")
    out_rows: List[dict] = []
    for pos, (text, block) in enumerate(zip(left_norm, left_block)):
        base = {"left_index": left.index[pos]}
        for c in left_cols:
            base[f"left_{c}"] = left_records[pos][c]
        if include_normalized:
            base["left_normalized"] = text

        matches = results.get((block, text), []) if text else []
        emitted = False
        for rank, (score, idx) in enumerate(matches, 1):
            texts, _pre, rows = right_groups[block]
            for r_pos in rows[idx]:
                row = dict(base)
                row["right_index"] = right.index[r_pos]
                for c in right_cols:
                    row[f"right_{c}"] = right_records[r_pos][c]
                if include_normalized:
                    row["right_normalized"] = texts[idx]
                row["match_rank"] = rank
                row["match_score"] = round(score, 2)
                out_rows.append(row)
                emitted = True
        if not emitted and include_unmatched:
            out_rows.append(base)

    columns = (
        ["left_index"]
        + [f"left_{c}" for c in left_cols]
        + (["left_normalized"] if include_normalized else [])
        + ["right_index"]
        + [f"right_{c}" for c in right_cols]
        + (["right_normalized"] if include_normalized else [])
        + ["match_rank", "match_score"]
    )
    result = pd.DataFrame(out_rows, columns=columns)
    result["match_rank"] = result["match_rank"].astype("Int64")
    if show_progress:
        matched = result.loc[result["match_rank"].notna(), "left_index"].nunique()
        print(
            f"Done in {time.time() - start:,.1f}s. {matched:,} of {len(left):,} "
            f"left rows have at least one match.",
            file=sys.stderr,
        )
    return result
