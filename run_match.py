#!/usr/bin/env python
"""
Run a fuzzy match using the settings in config.py (or another config file).

    python run_match.py                          # uses config.py
    python run_match.py --config my_config.py    # uses your own copy
    python run_match.py --try "Acme, Inc." "ACME INC"   # test one pair
"""

import argparse
import sys
from pathlib import Path

from fuzzy_match import explain, match_dataframes
from fuzzy_match.config_loader import (
    load_config,
    match_kwargs_from_config,
    read_table,
    resolve_path,
    settings_from_config,
    write_table,
)

DEFAULT_CONFIG = Path(__file__).resolve().parent / "config.py"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="path to a config .py file")
    parser.add_argument(
        "--try", nargs=2, metavar=("A", "B"), dest="try_pair",
        help="score a single pair of strings with the config's weights and exit",
    )
    parser.add_argument("--quiet", action="store_true", help="don't print progress")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    settings = settings_from_config(cfg)

    if args.try_pair:
        print(explain(args.try_pair[0], args.try_pair[1], settings))
        return 0

    left_path = resolve_path(cfg, cfg.LEFT_FILE)
    right_path = resolve_path(cfg, cfg.RIGHT_FILE)
    out_path = resolve_path(cfg, cfg.OUTPUT_FILE)

    print(f"Reading left:  {left_path}", file=sys.stderr)
    left = read_table(left_path, getattr(cfg, "LEFT_READ_OPTIONS", None))
    print(f"Reading right: {right_path}", file=sys.stderr)
    right = read_table(right_path, getattr(cfg, "RIGHT_READ_OPTIONS", None))
    print(f"  {len(left):,} left rows, {len(right):,} right rows", file=sys.stderr)

    result = match_dataframes(
        left, right, settings=settings, show_progress=not args.quiet,
        **match_kwargs_from_config(cfg),
    )

    write_table(result, out_path)
    print(f"Wrote {len(result):,} rows to {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
