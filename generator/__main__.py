"""Usage: python -m generator --seed 1 [--out data/generated]"""
import argparse
from pathlib import Path

from .build import build
from .dataset import write_csv
from .stats import first_digit_mad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out", default="data/generated")
    args = ap.parse_args()
    ds = build(args.seed)
    out = Path(args.out) / f"seed{args.seed}"
    write_csv(ds, out)
    print(f"seed {args.seed}: wrote {out}")
    for name, rows in ds.tables.items():
        print(f"  {name:16s} {len(rows):>7,} rows")


if __name__ == "__main__":
    main()
