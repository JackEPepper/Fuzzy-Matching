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
# What scores meant in synthetic company-name testing with these settings
# (benchmarks/company_names.py - re-run it on your own list to check):
#   90+     top match right ~99.7% of the time
#   85-90   usually right (~98% overall precision at 85)
#   75-85   worth a manual look
#   < 75    usually wrong, or the company isn't in the other list
INCLUDE_UNMATCHED = True        # keep left rows that found no match
INCLUDE_NORMALIZED_TEXT = True  # show the cleaned text that was compared

# Speed: a fast first pass picks this many candidates per left value, then
# the weighted scorer ranks them. Raise it if good matches are being missed,
# or set to None to compare every pair (exact, but slow on big data).
CANDIDATES_PER_ROW = 10

# Scorer(s) for that fast first pass (from the rapidfuzz library). With
# several, each one contributes its own CANDIDATES_PER_ROW candidates.
#   "token_sort_ratio" - ignores word order ("Smith & Jones" ~ "Jones & Smith")
#   "ratio"            - plain edit distance; catches glued words ("ReedElectric")
#   "token_set_ratio"  - good when one side has extra words
#   "partial_ratio"    - good when one side is a substring of the other
#   "WRatio"           - smartest blend, but ~50x slower
PREFILTER_SCORER = ["token_sort_ratio", "ratio"]

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
COLLAPSE_ACRONYMS = True     # True:  "L.L.C." == "LLC", "J.P." == "JP"

# Plain text find -> replace (after lower-casing, if CASE_SENSITIVE=False)
REPLACEMENTS = {
    "&": " and ",
}

# Whole-word find -> replace. Use this to make different spellings of the
# same word identical. Keys are matched as whole words only, so "co" will
# not touch "costco". Write keys in lower case. Add your own!
WORD_REPLACEMENTS = {
    # --- legal suffixes -> one standard form ---
    "incorporated": "inc",
    "corporation": "corp",
    "company": "co",
    "limited": "ltd",
    "and co": "co",          # "Smith & Co." == "Smith Company"
    "limited liability company": "llc",
    "limited partnership": "lp",
    "public limited company": "plc",
    # --- common business abbreviations -> full word ---
    # (Expanding is better than abbreviating: a typo in a long word stays a
    #  small difference instead of breaking the replacement.)
    "intl": "international", "int'l": "international",
    "mfg": "manufacturing", "mfr": "manufacturing",
    "svcs": "services", "svc": "service", "srvcs": "services",
    "assoc": "associates", "assocs": "associates", "assn": "association",
    "bros": "brothers",
    "tech": "technology", "techs": "technologies",
    "sys": "systems",
    "hldgs": "holdings", "hldg": "holding",
    "dist": "distributors", "distr": "distributors",
    "eng": "engineering", "engr": "engineering",
    "constr": "construction", "const": "construction",
    "finl": "financial", "fin": "financial",
    "pharma": "pharmaceuticals", "pharm": "pharmaceuticals",
    "mgmt": "management", "mgt": "management",
    "dev": "development", "devel": "development",
    "natl": "national", "nat'l": "national",
    "inds": "industries", "ind": "industries", "indus": "industries",
    "lab": "laboratory", "labs": "laboratories",
    "comm": "communications", "comms": "communications",
    "dept": "department",
    "ctr": "center", "centre": "center",
    "mtn": "mountain", "mtns": "mountains",
    "med": "medical",
    "prop": "properties", "props": "properties",
    "ins": "insurance",
    "grp": "group",
    "elec": "electric",
    "amer": "american",
    "univ": "university",
    "hosp": "hospital",
    # "st": "saint",       # careful: could also mean "street"
}

# Regular-expression find -> replace, applied last (for anything fancier).
# \b means "word boundary", so r"\bst\b" won't touch "west".
REGEX_REPLACEMENTS = {
    # r"\s*\(.*?\)": "",     # e.g. drop anything in parentheses
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
# Measure the effect on company names (see benchmarks/company_names.py):
#   python benchmarks/company_names.py --config config.py

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
}

# Legal-entity suffixes: "Acme" vs "Acme Inc" vs "Acme LLC" should barely
# differ. (Spellings like "Incorporated" / "L.L.C." are standardized above.)
LEGAL_SUFFIX_WEIGHT = 0.05
LEGAL_SUFFIXES = [
    "inc", "llc", "ltd", "corp", "co", "lp", "llp", "lllp", "plc", "pc", "pa",
    "pllc", "gmbh", "ag", "sa", "nv", "bv", "pty", "srl", "spa", "oy", "ab",
]

# Generic words that are often added/dropped ("Acme Holdings" vs "Acme").
# Half weight was best in testing; lower it if your data drops these a lot,
# raise to 1.0 if "X Holdings" and "X" are usually DIFFERENT companies.
GENERIC_WORD_WEIGHT = 0.5
GENERIC_WORDS = [
    "group", "holdings", "holding", "international", "enterprises",
    "companies", "industries",
]

# Words whose characters should count less (or more). This is a MULTIPLIER on
# the character weights, e.g. 0.2 makes "the" count 20% as much as normal.
# Words are matched after clean-up (lower case, replacements applied).
WORD_WEIGHTS = {
    **{suffix: LEGAL_SUFFIX_WEIGHT for suffix in LEGAL_SUFFIXES},
    **{word: GENERIC_WORD_WEIGHT for word in GENERIC_WORDS},
    "the": 0.2,
    "and": 0.3,
    "of": 0.5,
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

# Swapping two neighbouring letters ("Jhonson" vs "Johnson") counts as one
# edit times this number. None = count it as two edits (plain Levenshtein).
TRANSPOSITION_COST = 1.0

# Also compare with the words sorted alphabetically and keep the better score,
# so "Smith & Jones" == "Jones & Smith". Costs up to ~2x the scoring time.
COMPARE_SORTED_WORDS = True
# Points taken off a match that only works after re-sorting the words, so
# "Smith & Jones" prefers "Smith & Jones" over "Jones & Smith".
SORTED_WORDS_PENALTY = 5
