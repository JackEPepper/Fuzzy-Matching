# Fuzzy-Matching

Fuzzy-match a text column in one table against a text column in another table
(two pandas DataFrames), where **you choose which characters and words matter
less**.

For example, you can make punctuation and spaces count 10% as much as letters,
make `inc` / `llc` barely count, ignore hyphens entirely, or make `0` ↔ `o`
a cheap typo. Everything is set in one plain Python file: **`config.py`**.

The defaults are tuned for **company names**:

```
IBM                 vs  IBM Corp.                93.3
Acme                vs  Acme, Incorporated       96.0
Acme Inc            vs  Acme LLC                 97.6
Smith & Co.         vs  Smith Company            99.9
Keystone Mfg. Ltd   vs  Keystone Manufacturing   99.2
Jones & Smith       vs  Smith & Jones            95.0
```

---

## Quick start

```bash
# 1. Get the code (or download the ZIP from GitHub: Code -> Download ZIP)
git clone https://github.com/JackEPepper/Fuzzy-Matching.git
cd Fuzzy-Matching

# 2. Install dependencies (Python 3.8+)
pip install -r requirements.txt

# 3. Run the built-in example
python run_match.py
#   -> writes output/matches.csv
```

### Run on your own data

1. Copy `config.py` to **`my_config.py`** (git ignores it, so your file and
   column names never get pushed to this public repo).
2. Edit `my_config.py`: set `LEFT_FILE`, `RIGHT_FILE`, `LEFT_COLUMN`,
   `RIGHT_COLUMN`, `OUTPUT_FILE`, and the weights.
3. Run:

```bash
python run_match.py --config my_config.py
```

Supported file types: `.csv`, `.tsv`/`.txt` (tab separated), `.xlsx`/`.xls`,
`.parquet`. Output can be `.csv` or `.xlsx`.

### Tune the weights on a single pair

```bash
python run_match.py --config my_config.py --try "Acme, Inc." "ACME Incorporated"
```

```
A raw:        'Acme, Inc.'
A normalized: 'acme, inc.'
A weights:    'a'=1 'c'=1 'm'=1 'e'=1 ','=0.005 ' '=0.01 'i'=0.05 'n'=0.05 'c'=0.05 '.'=0.005
A total weight: 4.17
B raw:        'ACME Incorporated'
B normalized: 'acme inc'
B weights:    'a'=1 'c'=1 'm'=1 'e'=1 ' '=0.01 'i'=0.05 'n'=0.05 'c'=0.05
B total weight: 4.16
weighted distance: 0.01
score: 99.76
```

This shows exactly what text was compared and what every character was worth,
so you can adjust the config until the scores look right.

---

## How the weights work

The score is a **weighted edit distance** (Levenshtein). A normal edit
distance charges 1 for every inserted, deleted, or changed character. Here
each character has a weight, and an edit costs that weight:

| Edit | Cost |
| --- | --- |
| insert / delete a character | that character's weight |
| change character X to Y | the larger of the two weights × the pair's `SUBSTITUTION_COSTS` multiplier (default 1) |

```
score = 100 × (1 − weighted_distance / max(total weight of A, total weight of B))
```

Each character's weight comes from the first setting that applies:

1. **`CHARACTER_WEIGHTS`**: specific characters, e.g. `{"-": 0.0, "#": 0.5}`
2. **`CHARACTER_CLASS_WEIGHTS`**: `letter`, `digit`, `whitespace`,
   `punctuation` (includes symbols), `other`
3. **`DEFAULT_CHARACTER_WEIGHT`** (1.0)

Then **`WORD_WEIGHTS`** multiplies the weight of every character in a matching
whole word, e.g. `{"inc": 0.2}`. A weight of `0` means the character or word
is ignored completely.

Spaces and punctuation next to a down-weighted word take on that word's
multiplier, so the `, ` and `.` in `Acme, Inc.` count as little as `inc`.

Other scoring options:

* `TRANSPOSITION_COST`: swapping two neighbouring letters (`Jhonson`) counts
  as one edit instead of two.
* `COMPARE_SORTED_WORDS`: also compares the words in alphabetical order, so
  `Smith & Jones` ≈ `Jones & Smith`. A match found only this way loses
  `SORTED_WORDS_PENALTY` points, so a match in the original order ranks higher.

Before scoring, both columns are cleaned up the same way:

1. Accents are removed and text is lower-cased.
2. `REPLACEMENTS` are applied (plain text, e.g. `"&" -> " and "`).
3. Dotted acronyms are collapsed (`L.L.C.` → `llc`, `J.P.` → `jp`).
4. `WORD_REPLACEMENTS` are applied. These are whole words, e.g.
   `"incorporated" -> "inc"`, `"intl" -> "international"`, and `co` never
   touches `costco`.
5. `REGEX_REPLACEMENTS` are applied, then extra whitespace is collapsed.

Each step can be turned off or edited in the config.

---

## Output

One row per (left row, match):

| column | meaning |
| --- | --- |
| `left_index` | row label from the left DataFrame |
| `left_<col>` | the match column + any `KEEP_LEFT_COLUMNS` |
| `left_normalized` | cleaned text that was actually compared |
| `right_index`, `right_<col>`, `right_normalized` | same for the right side |
| `match_rank` | 1 = best match for that left row |
| `match_score` | 0-100 |

Left rows with no match at or above `MIN_SCORE` are kept with blank right-side
columns (set `INCLUDE_UNMATCHED = False` to drop them). If several right rows
have identical cleaned text, they all appear with the same rank.

---

## Company names: tested settings

`benchmarks/company_names.py` generates a synthetic master list of 5,000
companies. About 30% of them have a look-alike *different* company, such as
`Corvana Logistics` vs `Corvana Holdings` or `Corvana` vs `Corvina`. It then
creates messy versions of known companies and 1,000 companies that are not in
the list, and checks whether the matcher picks the right one.

| Variation | Example | Plain fuzzy match | This config |
| --- | --- | --- | --- |
| suffix dropped / added | `Acme` ↔ `Acme Inc` | 58% | **100%** |
| suffix reformatted | `Inc.` ↔ `, Incorporated` ↔ `INC` | 76% | **100%** |
| suffix type changed | `Acme Inc` ↔ `Acme L.L.C.` | 62% | **100%** |
| upper/lower case | `ACME INC` | 86% | **100%** |
| punctuation | `Acme Inc.` ↔ `Acme, Inc` | 86% | **100%** |
| & vs and | `Smith & Jones` ↔ `Smith and Jones`, `& Co.` ↔ `Company` | 68% | **99.7%** |
| "The" added/removed | `The Acme Co` | 80% | **100%** |
| abbreviation | `Intl` ↔ `International`, `Mfg` ↔ `Manufacturing` | 76% | **98%** |
| generic word added/removed | `Acme Holdings` ↔ `Acme` | 54% | **91%** |
| one typo | `Jhonson`, `Acne` | 87% | **96%** |
| spacing | `ReedElectric` ↔ `Reed Electric` | 86% | **96%** |
| word order | `Jones & Smith` ↔ `Smith & Jones` | 26% | **100%** |
| 2-3 of the above at once | `ACME INTL` ↔ `Acme International, Inc.` | 66% | **99%** |
| short names only (`IBM`, `3M`) | | 41% | **95%** |
| **all** | | **70%** | **98.5%** |

(% = the correct company was the top match.)

What the score means (accepting the top match when score ≥ threshold; plain
fuzzy matching in brackets):

| MIN_SCORE | matches found | accepted matches that are correct |
| --- | --- | --- |
| 75 | 95.7% (57%) | 90.1% (72%) |
| 80 | 93.7% (48%) | 95.0% (82%) |
| 85 | 90.8% (36%) | 98.1% (91%) |
| 90 | 88.1% (27%) | 99.7% (96%) |

Most remaining errors are inherently ambiguous: a one-letter typo in a short
name (`Nafi Insurance`) looks the same as a different real company
(`Vafi Insurance`). Short names like `IBM` are the hardest case.

**Check the settings against your own company list.** This runs entirely on
your machine. Your real names become the master list, and the messy versions
are generated from them:

```bash
python benchmarks/company_names.py --config my_config.py \
    --right-file data/vendors.csv --right-column vendor_name
```

Other options: `--compare-baseline` (compare with no weights),
`--show-errors 30` (print sample mistakes), and `--n-master`, `--per-variant`
and `--seed` for the synthetic list.

If the "generic word" row matters for your data (`X Holdings` vs `X`), change
`GENERIC_WORD_WEIGHT`. Raise it toward 1.0 if those are usually *different*
companies for you.

---

## Big files

The matcher works in two passes:

1. Fast standard fuzzy scorers (the `rapidfuzz` library, using all CPU
   cores) each pick the `CANDIDATES_PER_ROW` best right-side candidates for
   every left value. Low-weight characters and words are stripped for this
   pass.
2. Those candidates are re-scored with the weighted scorer.

Duplicate values are scored only once. On a 4-core machine, matching 5,000
against 20,000 company names takes about 15–20 seconds.

If it's still too slow or you're missing matches:

* **`BLOCK_ON = ("state", "state")`**: only compare rows with the same value
  in another column. This is the biggest speed-up.
* Raise `CANDIDATES_PER_ROW` if good matches are being missed. Set it to
  `None` to compare every pair (exact but slow).
* `PREFILTER_SCORER = "token_set_ratio"` helps when one side has extra words.

If `rapidfuzz` can't be installed at work, the code still runs using pure
Python, just more slowly.

---

## Use from Python / Jupyter

If your data is already in DataFrames (e.g. from a SQL query):

```python
from fuzzy_match import WeightSettings, match_dataframes, similarity, explain

settings = WeightSettings(
    char_class_weights={"punctuation": 0.1, "whitespace": 0.2},
    char_weights={"-": 0.0},
    word_weights={"inc": 0.2, "llc": 0.2},
    substitution_costs={("0", "o"): 0.2},
)

result = match_dataframes(
    left_df, right_df,
    left_on="customer_name", right_on="company",
    settings=settings, top_n=3, min_score=80,
    keep_left=["customer_id"], keep_right="all",
)

# or reuse a config file:
from fuzzy_match import load_config, settings_from_config
settings = settings_from_config(load_config("my_config.py"))
```

See `examples/use_in_python.py`.

---

## Project layout (where to change things)

```
config.py                  <- ALL settings. Start here.
run_match.py               <- command-line entry point (read files, match, write)
fuzzy_match/
    scoring.py             <- clean-up + character/word weights + weighted distance
    matcher.py             <- DataFrame matching: candidates, ranking, output table
    config_loader.py       <- reads config.py, reads/writes csv/excel/parquet
examples/                  <- fake sample data + Python usage example
benchmarks/
    company_names.py       <- synthetic company-name accuracy test
tests/                     <- pytest tests (run: python -m pytest)
```

Common modifications:

| I want to… | Change |
| --- | --- |
| down-weight a character / word | `CHARACTER_WEIGHTS` / `WORD_WEIGHTS` in `config.py` |
| standardize abbreviations / spellings | `WORD_REPLACEMENTS` in `config.py` |
| change how much "Inc"/"LLC" matter | `LEGAL_SUFFIX_WEIGHT` in `config.py` |
| a new character class (e.g. vowels) | `char_class()` in `fuzzy_match/scoring.py` |
| a different scoring formula | `similarity_normalized()` in `fuzzy_match/scoring.py` |
| one-to-one matching / extra output columns | the "Assemble output" section in `fuzzy_match/matcher.py` |
| read from a database instead of files | `run_match.py`, or use `match_dataframes` directly |

Run `python -m pytest` after making changes to check nothing broke.

---

## Keeping work data private

`.gitignore` excludes `*.csv`, `*.xlsx`, `*.parquet`, `output/`, `data/` and
`my_config*.py` (the example CSVs in `examples/` are the only exception), so
proprietary data and settings aren't committed by accident. Still check
`git status` before you commit anything from a work machine.
