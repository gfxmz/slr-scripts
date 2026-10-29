#!/usr/bin/env python3
"""
merge_csv.py
------------
Part of the scopus-slr-tools project (https://github.com/YOUR-USERNAME/scopus-slr-tools)

Merges all CSV files in a folder (same column structure, e.g. Scopus exports
split into multiple files) into a single file, removing duplicate records.
Prints a summary at the end: total records read, duplicates found, and
records removed.

Usage:
    python merge_csv.py --folder ./data --output merged.csv

Optional:
    --encoding utf-8      (default: utf-8)
    --sep ,                (default column separator: comma)

License: MIT (see LICENSE in the repository)
"""

import argparse
import glob
import os
import sys

import pandas as pd


def main():
    parser = argparse.ArgumentParser(description="Merge CSV files and remove duplicates")
    parser.add_argument("--folder", required=True, help="Folder containing the CSV files")
    parser.add_argument("--output", default="merged.csv", help="Output file name")
    parser.add_argument("--encoding", default="utf-8", help="File encoding (default: utf-8)")
    parser.add_argument("--sep", default=",", help="Column separator (default: ',')")
    args = parser.parse_args()

    # Find all CSV files in the folder
    pattern = os.path.join(args.folder, "*.csv")
    files = sorted(glob.glob(pattern))

    if not files:
        print(f"No CSV files found in folder: {args.folder}")
        sys.exit(1)

    print(f"Found {len(files)} CSV file(s) to merge:")
    for f in files:
        print(f"  - {os.path.basename(f)}")

    # Read and concatenate all files
    frames = []
    for file in files:
        try:
            df = pd.read_csv(file, encoding=args.encoding, sep=args.sep)
            frames.append(df)
        except Exception as e:
            print(f"ERROR reading file {file}: {e}")
            sys.exit(1)

    merged = pd.concat(frames, ignore_index=True)

    total_records = len(merged)

    # Remove duplicates (comparing all columns)
    deduplicated = merged.drop_duplicates()

    records_after_dedup = len(deduplicated)
    duplicates_found = total_records - records_after_dedup

    # Save the result
    deduplicated.to_csv(args.output, index=False, encoding=args.encoding, sep=args.sep)

    # Summary
    print("\n--- SUMMARY ---")
    print(f"Total records read:           {total_records}")
    print(f"Duplicates found:             {duplicates_found}")
    print(f"Records removed:              {duplicates_found}")
    print(f"Records in output file:       {records_after_dedup}")
    print(f"\nOutput file saved as: {args.output}")


if __name__ == "__main__":
    main()
