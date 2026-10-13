"""
=============================================================================
 FUZZY MATCH SETTINGS  -  this is the only file you should need to edit.
=============================================================================

Tip: copy this file to ``my_config.py`` (which git ignores) and run

    python run_match.py --config my_config.py

so your real file names / column names never end up in the public repo.

Relative file paths below are relative to THIS config file's folder.
"""

# --------------------------------------------------------------------------- #
# 1. INPUT / OUTPUT
# --------------------------------------------------------------------------- #
# Supported: .csv, .tsv, .txt (tab separated), .xlsx/.xls, .parquet
LEFT_FILE = "examples/left.csv"
RIGHT_FILE = "examples/right.csv"

# The column in each file holding the text to match
LEFT_COLUMN = "customer_name"
RIGHT_COLUMN = "company"

# Extra options passed to the pandas reader, e.g.
#   {"sheet_name": "Sheet2"}   for Excel
#   {"encoding": "latin-1"}    for CSVs that won't open
LEFT_READ_OPTIONS = {}
RIGHT_READ_OPTIONS = {}

# Output: .csv or .xlsx
OUTPUT_FILE = "output/matches.csv"

# Extra columns to copy into the output so you can identify rows.
# A list of names, "all", or None. The match columns are always included.
KEEP_LEFT_COLUMNS = ["customer_id"]
KEEP_RIGHT_COLUMNS = ["vendor_id", "state"]


# --------------------------------------------------------------------------- #
# 2. MATCHING BEHAVIOUR
# --------------------------------------------------------------------------- #
TOP_N = 3            # how many matches to return for each left row
MIN_SCORE = 70       # 0-100; matches below this are dropped
INCLUDE_UNMATCHED = True        # keep left rows that found no match
INCLUDE_NORMALIZED_TEXT = True  # show the cleaned text that was compared

# Speed: a fast first pass picks this many candidates per left value, then
# the weighted scorer ranks them. Raise it if good matches are being missed,
# or set to None to compare every pair (exact, but slow on big data).
CANDIDATES_PER_ROW = 10

# Scorer for that fast first pass (from the rapidfuzz library):
#   "token_sort_ratio" - fast, ignores word order (default)
#   "ratio"            - fastest, plain edit distance
#   "token_set_ratio"  - good when one side has extra words
#   "partial_ratio"    - good when one side is a substring of the other
#   "WRatio"           - smartest blend, but ~50x slower
PREFILTER_SCORER = "token_sort_ratio"

# Optional "blocking": only compare rows whose values in these two columns
# are EXACTLY equal (e.g. same state or zip). Huge speed-up on big files.
# Format: ("left_column", "right_column")  or  None
BLOCK_ON = None
# BLOCK_ON = ("state", "state")


# --------------------------------------------------------------------------- #
# 3. TEXT CLEAN-UP (applied to both columns before scoring)
# --------------------------------------------------------------------------- #
CASE_SENSITIVE = False       # False: "ACME" == "acme"
STRIP_ACCENTS = True         # True:  "Café" == "Cafe"
COLLAPSE_WHITESPACE = True   # True:  "a   b" == "a b", trims ends

# Plain text find -> replace (after lower-casing, if CASE_SENSITIVE=False)
REPLACEMENTS = {
    "&": " and ",
}

# Regular-expression find -> replace, applied after REPLACEMENTS.
# \b means "word boundary", so r"\bst\b" won't touch "west".
REGEX_REPLACEMENTS = {
    r"\bincorporated\b": "inc",
    r"\bcorporation\b": "corp",
    r"\bcompany\b": "co",
    r"\blimited\b": "ltd",
}


# --------------------------------------------------------------------------- #
# 4. CHARACTER WEIGHTS  -  the main tuning knob
# --------------------------------------------------------------------------- #
# Every character has a weight. A difference involving that character costs
# its weight. 1.0 = normal, 0.5 = half as important, 0 = ignored entirely.
#
# Order of precedence (most specific wins):
#   CHARACTER_WEIGHTS  >  CHARACTER_CLASS_WEIGHTS  >  DEFAULT_CHARACTER_WEIGHT
# Then WORD_WEIGHTS multiplies the weight of every character inside that word.
#
# Try a pair quickly to see the effect:
#   python run_match.py --try "Acme, Inc." "ACME INC"

DEFAULT_CHARACTER_WEIGHT = 1.0

# Weights for whole categories of characters.
# Classes: "letter", "digit", "whitespace", "punctuation", "other"
# ("punctuation" includes symbols like $ % + = etc.)
CHARACTER_CLASS_WEIGHTS = {
    "letter": 1.0,
    "digit": 1.0,
    "whitespace": 0.2,
    "punctuation": 0.1,
}

# Weights for individual characters (override the class weight above).
# Write letters in lower case unless CASE_SENSITIVE = True.
CHARACTER_WEIGHTS = {
    # "-": 0.0,    # ignore hyphens completely
    # "#": 0.5,
    # "x": 0.3,    # e.g. if "x" is a common filler/typo character in your data
}

# Words whose characters should count less (or more). This is a MULTIPLIER on
# the character weights, e.g. 0.2 makes "inc" count 20% as much as normal.
# Words are matched after clean-up (so lower case, replacements applied).
WORD_WEIGHTS = {
    "inc": 0.2,
    "llc": 0.2,
    "ltd": 0.2,
    "corp": 0.2,
    "co": 0.3,
    "the": 0.3,
    "and": 0.5,
}

# Make swapping specific look-alike characters cheaper. The number multiplies
# the normal substitution cost (1.0 = normal, 0.2 = 80% cheaper).
# Pairs work in both directions.
SUBSTITUTION_COSTS = {
    ("0", "o"): 0.2,
    ("1", "l"): 0.2,
    ("1", "i"): 0.2,
    ("5", "s"): 0.3,
}
