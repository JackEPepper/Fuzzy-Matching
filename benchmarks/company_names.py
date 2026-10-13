#!/usr/bin/env python
"""
Synthetic accuracy test for COMPANY NAMES.

It builds a "right" master list of companies, then a "left" list containing
messy variants of some of them (Inc vs no Inc, "Corp." vs "Corporation",
"&" vs "and", typos, abbreviations, ...) plus companies that are NOT in the
master list. It runs the matcher and reports, per kind of variation, how
often the correct company came out on top and at what score - so you can
pick MIN_SCORE and tune the weights with evidence.

The master list also contains look-alike DIFFERENT companies ("Corvana
Logistics" vs "Corvana Holdings", "Corvana" vs "Corvina") to make sure the
weights don't merge things they shouldn't.

Usage
-----
    python benchmarks/company_names.py                         # uses config.py
    python benchmarks/company_names.py --config my_config.py
    python benchmarks/company_names.py --compare-baseline      # vs. no weights

Test your settings against YOUR OWN company list (nothing leaves your
machine): the real names become the master list and the variants are
generated from them.

    python benchmarks/company_names.py --config my_config.py \\
        --right-file data/vendors.csv --right-column vendor_name
"""

from __future__ import annotations

import argparse
import random
import re
import string
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fuzzy_match import WeightSettings, match_dataframes  # noqa: E402
from fuzzy_match.config_loader import (  # noqa: E402
    load_config,
    match_kwargs_from_config,
    read_table,
    settings_from_config,
)

# --------------------------------------------------------------------------- #
# Vocabulary
# --------------------------------------------------------------------------- #
SURNAMES = """Smith Johnson Williams Brown Jones Garcia Miller Davis Rodriguez Martinez
Hernandez Lopez Wilson Anderson Thomas Taylor Moore Jackson Martin Lee Thompson White
Harris Clark Lewis Robinson Walker Young Allen King Wright Scott Hill Green Adams Baker
Nelson Carter Mitchell Roberts Turner Phillips Campbell Parker Evans Edwards Collins
Stewart Morris Murphy Cook Rogers Morgan Peterson Cooper Reed Bailey Bell Kelly Howard
Ward Cox Richardson Wood Watson Brooks Bennett Gray Hughes Price Sanders Myers Long Ross
Foster Powell Jenkins Perry Russell Sullivan Fisher Henderson Coleman""".split()

PLACES = """Summit Pacific Atlantic Midwest Northern Southern Lakeside Riverside Coastal
Mountain Valley Prairie Harbor Bay Canyon Eagle Liberty Pioneer Heritage Keystone
Granite Cedar Oak Maple Pine Sierra Gulf Capital Metro Central Western Eastern Tri-State
Great_Lakes Blue_Ridge Golden_Gate Silver_Creek Red_Rock Twin_Cities""".split()
PLACES = [p.replace("_", " ") for p in PLACES]

INDUSTRY = """Logistics Holdings Industries Solutions Systems Technologies Services
Consulting Partners Group Manufacturing Foods Energy Capital Insurance Construction
Healthcare Pharmaceuticals Associates International Supply Electric Marketing Realty
Properties Transport Labs Media Software Distributors Builders Engineering Financial
Medical Plumbing Roofing Landscaping Automotive Packaging Chemicals Steel Textiles""".split()

SYLLABLES = """zen tri cor va na lux no ve gen ix al tra on qua ra ly sio mer ka del
fi ber tek ex pro lo vi ta sun ar mo ri ze ny bo ca tel""".split()

ABBREVIATIONS = {
    "International": "Intl", "Manufacturing": "Mfg", "Services": "Svcs",
    "Associates": "Assoc", "Brothers": "Bros", "Technologies": "Tech",
    "Systems": "Sys", "Holdings": "Hldgs", "Distributors": "Dist",
    "Engineering": "Eng", "Construction": "Constr", "Financial": "Finl",
    "Pharmaceuticals": "Pharma", "Mountain": "Mtn", "Medical": "Med",
    "Automotive": "Auto", "Properties": "Prop", "Insurance": "Ins",
}

# Legal-suffix families and the ways people actually write them
SUFFIXES: Dict[str, List[str]] = {
    "inc": ["Inc", "Inc.", ", Inc.", ", Inc", "Incorporated", ", Incorporated"],
    "llc": ["LLC", ", LLC", "L.L.C.", ", L.L.C."],
    "corp": ["Corp", "Corp.", "Corporation", ", Corp."],
    "co": ["Co", "Co.", "Company", "& Co."],
    "ltd": ["Ltd", "Ltd.", "Limited", ", Ltd."],
    "lp": ["LP", "L.P.", ", L.P."],
    "llp": ["LLP", ", LLP", "L.L.P."],
    "plc": ["PLC", "plc"],
}
SUFFIX_FAMILY_WEIGHTS = {"inc": 30, "llc": 25, "corp": 12, "co": 8, "ltd": 6,
                         "lp": 3, "llp": 3, "plc": 1, "": 20}

_SUFFIX_RE = re.compile(
    r"^(?P<base>.*?)(?P<suffix>(?:,?\s*&\s*co\.?|,?\s+(?:inc\.?|incorporated|llc|"
    r"l\.l\.c\.|corp\.?|corporation|co\.?|company|ltd\.?|limited|lp|l\.p\.|llp|"
    r"l\.l\.p\.|plc)))$",
    re.IGNORECASE,
)


def split_suffix(name: str) -> Tuple[str, str]:
    """'Acme, Inc.' -> ('Acme', 'inc')."""
    m = _SUFFIX_RE.match(name.strip())
    if not m or not m.group("base").strip():
        return name.strip(), ""
    raw = re.sub(r"[\s,.&]", "", m.group("suffix")).lower()
    family = {"incorporated": "inc", "corporation": "corp", "company": "co",
              "limited": "ltd"}.get(raw, raw)
    return m.group("base").strip(" ,"), family if family in SUFFIXES else ""


def attach(base: str, form: str) -> str:
    if not form:
        return base
    return base + form if form.startswith(",") else f"{base} {form}"


# --------------------------------------------------------------------------- #
# Generating companies
# --------------------------------------------------------------------------- #
def brand(rng: random.Random) -> str:
    return "".join(rng.choice(SYLLABLES) for _ in range(rng.randint(2, 3))).capitalize()


def base_name(rng: random.Random) -> str:
    pattern = rng.choices(range(11), weights=[14, 16, 14, 8, 6, 12, 6, 8, 6, 10, 6])[0]
    ind, ind2 = rng.sample(INDUSTRY, 2)
    s1, s2 = rng.sample(SURNAMES, 2)
    place = rng.choice(PLACES)
    if pattern == 0:
        return brand(rng)
    if pattern == 1:
        return f"{brand(rng)} {ind}"
    if pattern == 2:
        return f"{s1} {ind}"
    if pattern == 3:
        return f"{s1} & {s2}"
    if pattern == 4:
        return f"{s1} & {s2} {ind}"
    if pattern == 5:
        return f"{place} {ind}"
    if pattern == 6:
        return f"{place} {ind} {ind2}"
    if pattern == 7:
        return "".join(rng.sample(string.ascii_uppercase, rng.randint(2, 4))) + f" {ind}"
    if pattern == 8:
        return f"{s1} Brothers {ind}"
    if pattern == 10:  # short names like "IBM" or "3M"
        letters = "".join(rng.sample(string.ascii_uppercase, rng.randint(2, 4)))
        return letters if rng.random() < 0.8 else f"{rng.randint(1, 9)}{letters[:2]}"
    return f"{place} {s1} {ind}"


def random_suffix_family(rng: random.Random) -> str:
    fams = list(SUFFIX_FAMILY_WEIGHTS)
    return rng.choices(fams, weights=[SUFFIX_FAMILY_WEIGHTS[f] for f in fams])[0]


def one_letter_change(word: str, rng: random.Random) -> str:
    letters = [i for i, c in enumerate(word) if c.isalpha()]
    if not letters:
        return word
    i = rng.choice(letters[1:] or letters)  # keep the first letter
    new = rng.choice([c for c in "aeiourstnl" if c != word[i].lower()])
    return word[:i] + (new.upper() if word[i].isupper() else new) + word[i + 1:]


def lookalike(base: str, rng: random.Random) -> str:
    """A DIFFERENT company that looks similar."""
    words = base.split()
    industry_pos = [i for i, w in enumerate(words) if w in INDUSTRY]
    if industry_pos and rng.random() < 0.6:
        i = rng.choice(industry_pos)
        words[i] = rng.choice([w for w in INDUSTRY if w != words[i]])
    else:
        i = max(range(len(words)), key=lambda k: len(words[k]))
        words[i] = one_letter_change(words[i], rng)
    return " ".join(words)


def build_master(n: int, rng: random.Random, lookalike_share: float) -> pd.DataFrame:
    rows, seen = [], set()

    def add(base: str, family: str) -> None:
        key = base.lower()
        if key in seen:
            return
        seen.add(key)
        form = rng.choice(SUFFIXES[family]) if family else ""
        rows.append({"base": base, "family": family, "company": attach(base, form)})

    while len(rows) < n:
        base = base_name(rng)
        family = random_suffix_family(rng)
        add(base, family)
        if rng.random() < lookalike_share:
            add(lookalike(base, rng), random_suffix_family(rng))
    df = pd.DataFrame(rows[:n])
    df.insert(0, "company_id", [f"R{i:06d}" for i in range(len(df))])
    return df


# --------------------------------------------------------------------------- #
# Messy variants (each takes base, suffix family -> new full name)
# --------------------------------------------------------------------------- #
def v_suffix_dropped(base, fam, rng):
    return base if fam else attach(base, rng.choice(SUFFIXES["inc"]))  # or added


def v_suffix_reformatted(base, fam, rng):
    fam = fam or "inc"
    return attach(base, rng.choice(SUFFIXES[fam]))


def v_suffix_type_changed(base, fam, rng):
    other = rng.choice([f for f in SUFFIXES if f != fam])
    return attach(base, rng.choice(SUFFIXES[other]))


def v_case(base, fam, rng):
    name = attach(base, rng.choice(SUFFIXES[fam]) if fam else "")
    return rng.choice([name.upper(), name.lower()])


def v_punctuation(base, fam, rng):
    name = attach(base, rng.choice(SUFFIXES[fam]) if fam else "")
    if rng.random() < 0.5:
        return re.sub(r"[.,]", "", name)
    words = name.split()
    i = rng.randrange(len(words))
    words[i] += rng.choice([",", ".", " -"])
    return " ".join(words)


def v_ampersand(base, fam, rng):
    """'&' <-> 'and', or '& Co.' <-> 'Company'."""
    if "&" in base:
        base = base.replace("&", "and")
    elif " and " in base:
        base = base.replace(" and ", " & ")
    else:
        return attach(base, "Company" if fam == "co" else "& Co.")
    return attach(base, rng.choice(SUFFIXES[fam]) if fam else "")


def v_the(base, fam, rng):
    base = base[4:] if base.lower().startswith("the ") else "The " + base
    return attach(base, rng.choice(SUFFIXES[fam]) if fam else "")


_FULL_TO_ABBR = {k.lower(): v for k, v in {**ABBREVIATIONS, **{v: k for k, v in ABBREVIATIONS.items()}}.items()}
GENERIC_WORDS = ["Group", "Holdings", "International", "Enterprises", "Companies"]
_GENERIC_LOWER = {w.lower() for w in GENERIC_WORDS}


def _match_case(template: str, word: str) -> str:
    """Write ``word`` in the same style (UPPER/lower/Title) as ``template``."""
    if template.isupper() and len(template) > 1:
        return word.upper()
    if template.islower():
        return word.lower()
    return word


def _abbreviable(word: str) -> bool:
    return word.lower().rstrip(".") in _FULL_TO_ABBR


def v_abbreviation(base, fam, rng):
    words = base.split()
    i = rng.choice([i for i, w in enumerate(words) if _abbreviable(w)])
    swapped = _FULL_TO_ABBR[words[i].lower().rstrip(".")]
    words[i] = _match_case(words[i], swapped) + rng.choice(["", "."])
    return attach(" ".join(words), rng.choice(SUFFIXES[fam]) if fam else "")


def v_generic_word(base, fam, rng):
    """'Acme Holdings Inc' <-> 'Acme Inc'."""
    words = base.split()
    present = [i for i, w in enumerate(words) if w.lower() in _GENERIC_LOWER]
    if present and len(words) > 1:
        del words[rng.choice(present)]
    else:
        words.append(_match_case(words[-1], rng.choice(GENERIC_WORDS)))
    return attach(" ".join(words), rng.choice(SUFFIXES[fam]) if fam else "")


def v_typo(base, fam, rng):
    chars = list(base)
    letters = [i for i, c in enumerate(chars) if c.isalpha()]
    i = rng.choice(letters)
    op = rng.choice(["sub", "del", "ins", "swap"])
    if op == "sub":
        chars[i] = rng.choice(string.ascii_lowercase)
    elif op == "del":
        del chars[i]
    elif op == "ins":
        chars.insert(i, rng.choice(string.ascii_lowercase))
    elif i + 1 < len(chars):
        chars[i], chars[i + 1] = chars[i + 1], chars[i]
    return attach("".join(chars), rng.choice(SUFFIXES[fam]) if fam else "")


def v_spacing(base, fam, rng):
    if " " in base and rng.random() < 0.5:
        i = rng.choice([m.start() for m in re.finditer(" ", base)])
        base = base[:i] + base[i + 1:]
    else:
        words = base.split()
        i = max(range(len(words)), key=lambda k: len(words[k]))
        w = words[i]
        if len(w) > 5:
            words[i] = w[: len(w) // 2] + " " + w[len(w) // 2:]
        base = "  ".join(words)
    return attach(base, rng.choice(SUFFIXES[fam]) if fam else "")


def v_word_order(base, fam, rng):
    words = base.split()
    if len(words) >= 2:
        i = rng.randrange(len(words) - 1)
        words[i], words[i + 1] = words[i + 1], words[i]
    return attach(" ".join(words), rng.choice(SUFFIXES[fam]) if fam else "")


SINGLE_VARIANTS: Dict[str, Callable] = {
    "suffix dropped/added": v_suffix_dropped,
    "suffix reformatted": v_suffix_reformatted,
    "suffix type changed": v_suffix_type_changed,
    "upper/lower case": v_case,
    "punctuation": v_punctuation,
    "& vs and": v_ampersand,
    "'The' added/removed": v_the,
    "abbreviation": v_abbreviation,
    "generic word added/removed": v_generic_word,
    "one typo": v_typo,
    "spacing": v_spacing,
    "word order swapped": v_word_order,
}
# Cheap, common variations used to build the "combined" category
_COMBINABLE = ["suffix dropped/added", "suffix reformatted", "upper/lower case",
               "punctuation", "& vs and", "'The' added/removed", "abbreviation", "one typo"]


def v_combined(base, fam, rng):
    """2-3 variations at once, e.g. typo + suffix dropped + upper case."""
    picks = rng.sample(_COMBINABLE, rng.randint(2, 3))
    name = attach(base, rng.choice(SUFFIXES[fam]) if fam else "")
    for p in picks:
        b, f = split_suffix(name)
        if APPLIES_TO.get(p, lambda base: True)(b):
            name = SINGLE_VARIANTS[p](b, f, rng)
    return name


VARIANTS = {**SINGLE_VARIANTS, "2-3 combined": v_combined}

# Variations that only make sense for some names
APPLIES_TO = {
    "abbreviation": lambda base: any(_abbreviable(w) for w in base.split()),
    "word order swapped": lambda base: len(base.split()) >= 2,
    "spacing": lambda base: " " in base or any(len(w) > 5 for w in base.split()),
}


def build_queries(master: pd.DataFrame, per_variant: int, n_unmatched: int,
                  rng: random.Random, existing: set) -> pd.DataFrame:
    rows = []
    for vname, fn in VARIANTS.items():
        applies = APPLIES_TO.get(vname, lambda base: True)
        eligible = [i for i, b in enumerate(master["base"]) if applies(b)]
        if not eligible:
            continue
        for _ in range(per_variant):
            r = master.iloc[rng.choice(eligible)]
            rows.append({"name": fn(r["base"], r["family"], rng),
                         "truth": r["company_id"], "variation": vname,
                         "original": r["company"], "base": r["base"]})
    added = 0
    while added < n_unmatched:
        base = base_name(rng)
        if base.lower() in existing:
            continue
        existing.add(base.lower())
        fam = random_suffix_family(rng)
        rows.append({"name": attach(base, rng.choice(SUFFIXES[fam]) if fam else ""),
                     "truth": None, "variation": "NOT in master list", "original": "",
                     "base": base})
        added += 1
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Evaluation
# --------------------------------------------------------------------------- #
def evaluate(queries: pd.DataFrame, master: pd.DataFrame, settings: WeightSettings,
             match_kwargs: dict) -> pd.DataFrame:
    kw = dict(match_kwargs)
    kw.update(left_on="name", right_on="company", top_n=1, min_score=0,
              keep_left=None, keep_right=["company_id"], include_unmatched=True,
              block_on=None)
    out = match_dataframes(queries, master, settings=settings, show_progress=False, **kw)
    best = (out.groupby("left_index")
               .agg(score=("match_score", "max"),
                    predicted=("right_company_id", lambda s: set(s.dropna())),
                    predicted_name=("right_company", "first")))
    res = queries.join(best)
    res["score"] = res["score"].fillna(0.0)
    res["correct"] = [t in p if isinstance(t, str) else False
                      for t, p in zip(res.truth, res.predicted)]
    return res


def report(res: pd.DataFrame, title: str, thresholds=(60, 70, 75, 80, 85, 90, 95)) -> None:
    pos = res[res.truth.notna()]
    neg = res[res.truth.isna()]
    print(f"\n=== {title} ===")
    print(f"{len(pos):,} messy variants of known companies, {len(neg):,} companies NOT in the list\n")

    rows = []
    for var, g in res.groupby("variation", sort=False):
        if var == "NOT in master list":
            continue
        wrong = g[~g.correct]
        rows.append({
            "variation": var,
            "top match correct": f"{g.correct.mean():.1%}",
            "median score (correct)": f"{g[g.correct].score.median():.1f}",
            "low 5% score (correct)": f"{g[g.correct].score.quantile(0.05):.1f}",
            "median score (wrong)": f"{wrong.score.median():.1f}" if len(wrong) else "-",
        })
    rows.append({
        "variation": "ALL variants",
        "top match correct": f"{pos.correct.mean():.1%}",
        "median score (correct)": f"{pos[pos.correct].score.median():.1f}",
        "low 5% score (correct)": f"{pos[pos.correct].score.quantile(0.05):.1f}",
        "median score (wrong)": f"{pos[~pos.correct].score.median():.1f}" if (~pos.correct).any() else "-",
    })
    print(pd.DataFrame(rows).to_string(index=False))
    short = pos[pos.base.str.replace(r"\W", "", regex=True).str.len() <= 4]
    if len(short):
        print(f"\nShort names (<= 4 letters, e.g. 'IBM'): {len(short)} variants, top match "
              f"correct {short.correct.mean():.1%}, low 5% score (correct) "
              f"{short[short.correct].score.quantile(0.05):.1f}")
    print(f"\nNot-in-list companies: best (false) score median {neg.score.median():.1f}, "
          f"95th pct {neg.score.quantile(0.95):.1f}, max {neg.score.max():.1f}")

    print("\nIf you accept the top match when score >= MIN_SCORE:")
    trows = []
    for t in thresholds:
        accepted = res[res.score >= t]
        right = accepted.correct.sum()
        wrong_known = ((pos.score >= t) & ~pos.correct).sum()
        false_new = (neg.score >= t).sum()
        trows.append({
            "MIN_SCORE": t,
            "found (recall)": f"{right / len(pos):.1%}",
            "accepted matches that are right (precision)": f"{right / max(1, len(accepted)):.1%}",
            "wrong company accepted": int(wrong_known),
            "not-in-list matched to something": int(false_new),
        })
    print(pd.DataFrame(trows).to_string(index=False))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(ROOT / "config.py"))
    ap.add_argument("--n-master", type=int, default=5000, help="size of generated master list")
    ap.add_argument("--per-variant", type=int, default=300, help="queries per variation type")
    ap.add_argument("--n-unmatched", type=int, default=1000, help="queries NOT in the master list")
    ap.add_argument("--lookalikes", type=float, default=0.3,
                    help="share of master companies that get a look-alike different company")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--right-file", help="use your own company list as the master list")
    ap.add_argument("--right-column", help="column holding company names in --right-file")
    ap.add_argument("--compare-baseline", action="store_true",
                    help="also run with no weights/clean-up (plain lower-cased edit distance)")
    ap.add_argument("--show-errors", type=int, default=15, help="print this many wrong matches")
    args = ap.parse_args(argv)

    rng = random.Random(args.seed)
    if args.right_file:
        if not args.right_column:
            ap.error("--right-column is required with --right-file")
        raw = read_table(args.right_file)[args.right_column].dropna().astype(str)
        raw = raw[raw.str.strip() != ""].drop_duplicates().reset_index(drop=True)
        parts = [split_suffix(n) for n in raw]
        master = pd.DataFrame({"company_id": [f"R{i:06d}" for i in range(len(raw))],
                               "base": [b for b, _ in parts], "family": [f for _, f in parts],
                               "company": raw})
        print(f"Using {len(master):,} names from {args.right_file} as the master list")
    else:
        master = build_master(args.n_master, rng, args.lookalikes)
    existing = set(master.base.str.lower())
    queries = build_queries(master, args.per_variant, args.n_unmatched, rng, existing)

    cfg = load_config(args.config)
    res = evaluate(queries, master, settings_from_config(cfg), match_kwargs_from_config(cfg))
    report(res, f"Your settings ({Path(args.config).name})")

    if args.compare_baseline:
        base = evaluate(queries, master, WeightSettings(), match_kwargs_from_config(cfg))
        report(base, "Baseline: no weights, no replacements")

    errors = res[res.truth.notna() & ~res.correct]
    if args.show_errors and len(errors):
        print(f"\nSample wrong top matches ({len(errors)} total):")
        sample = errors.sample(min(args.show_errors, len(errors)), random_state=0)
        for r in sample.itertuples():
            print(f"  [{r.variation}] {r.name!r}\n      truth: {r.original!r}\n"
                  f"      got:   {r.predicted_name!r} ({r.score:.1f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
