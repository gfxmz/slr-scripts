#!/usr/bin/env python3
"""
download_oa_articles.py
------------------------
Part of the scopus-slr-tools project (https://github.com/YOUR-USERNAME/scopus-slr-tools)

Reads CSV files (Scopus export) from a folder, filters records according to
the criteria you specify (year, document type, citation count, Open Access
type, source, keywords), and then downloads the full text (PDF) of Open
Access articles using the Unpaywall service (https://unpaywall.org), which
legally finds free, open versions of publications based on DOI. Optionally
also fetches abstracts from CrossRef / Semantic Scholar.

IMPORTANT: Unpaywall requires an email address in requests (the "polite
pool") - this is a standard requirement of this free API and does not
involve any account registration.

Usage (full argument list: python download_oa_articles.py --help):
    python download_oa_articles.py --folder ./data --output-dir ./downloaded_pdfs --email you@email.com

Required libraries:
    pip install -r requirements.txt

License: MIT (see LICENSE in the repository)
"""

import argparse
import glob
import os
import re
import sys
import time

import pandas as pd
import requests

UNPAYWALL_URL = "https://api.unpaywall.org/v2/{doi}"
CROSSREF_URL = "https://api.crossref.org/works/{doi}"
SEMANTIC_SCHOLAR_URL = "https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}"
REQUEST_DELAY_SEC = 1.0  # delay between requests to be polite to the free APIs


def clean_abstract(text):
    """CrossRef often returns abstracts as JATS XML - strip the tags."""
    if not text:
        return None
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text if text else None


def fetch_abstract(doi, email, session):
    """Tries to fetch an abstract, first from CrossRef, then from Semantic Scholar."""
    # 1. CrossRef
    try:
        resp = session.get(
            CROSSREF_URL.format(doi=doi),
            params={"mailto": email},
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            abstract = data.get("message", {}).get("abstract")
            abstract = clean_abstract(abstract)
            if abstract:
                return abstract, "CrossRef"
    except Exception:
        pass

    # 2. Semantic Scholar (fallback)
    try:
        resp = session.get(
            SEMANTIC_SCHOLAR_URL.format(doi=doi),
            params={"fields": "abstract"},
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            abstract = clean_abstract(data.get("abstract"))
            if abstract:
                return abstract, "Semantic Scholar"
    except Exception:
        pass

    return None, None


def apply_filters(data, args):
    """Applies filters to the data one by one and returns (filtered_data, step_log)."""
    step_log = []
    df = data.copy()
    step_log.append(("Records before filtering", len(df)))

    # --- Year range ---
    if args.year_from is not None or args.year_to is not None:
        if "Year" not in df.columns:
            print("Warning: 'Year' column not found - skipping year range filter.")
        else:
            year_num = pd.to_numeric(df["Year"], errors="coerce")
            if args.year_from is not None:
                df = df[year_num >= args.year_from]
                year_num = pd.to_numeric(df["Year"], errors="coerce")
            if args.year_to is not None:
                df = df[year_num <= args.year_to]
            step_log.append((f"After year filter ({args.year_from or '-'}-{args.year_to or '-'})", len(df)))

    # --- Document type ---
    if args.doc_types:
        if "Document Type" not in df.columns:
            print("Warning: 'Document Type' column not found - skipping document type filter.")
        else:
            allowed = {t.strip().lower() for t in args.doc_types.split(",") if t.strip()}
            df = df[df["Document Type"].astype(str).str.strip().str.lower().isin(allowed)]
            step_log.append((f"After document type filter ({args.doc_types})", len(df)))

    # --- Minimum citation count ---
    if args.min_citations is not None:
        if "Cited by" not in df.columns:
            print("Warning: 'Cited by' column not found - skipping citation count filter.")
        else:
            citations_num = pd.to_numeric(df["Cited by"], errors="coerce").fillna(0)
            df = df[citations_num >= args.min_citations]
            step_log.append((f"After min. citations filter (>= {args.min_citations})", len(df)))

    # --- Open Access type ---
    if args.oa_types:
        if "Open Access" not in df.columns:
            print("Warning: 'Open Access' column not found - skipping Open Access type filter.")
        else:
            patterns = [t.strip().lower() for t in args.oa_types.split(",") if t.strip()]
            mask = df["Open Access"].astype(str).str.lower().apply(
                lambda text: any(pattern in text for pattern in patterns)
            )
            df = df[mask]
            step_log.append((f"After Open Access type filter ({args.oa_types})", len(df)))

    # --- Excluded sources/journals ---
    if args.exclude_sources:
        if "Source title" not in df.columns:
            print("Warning: 'Source title' column not found - skipping excluded sources filter.")
        else:
            excluded = [t.strip().lower() for t in args.exclude_sources.split(",") if t.strip()]
            mask = ~df["Source title"].astype(str).str.lower().apply(
                lambda text: any(w in text for w in excluded)
            )
            df = df[mask]
            step_log.append((f"After excluding sources ({args.exclude_sources})", len(df)))

    return df, step_log


def matches_keywords(title, abstract, keywords):
    text = f"{title} {abstract or ''}".lower()
    return any(k in text for k in keywords)


def safe_filename(text, limit=120):
    """Turns an article title/author string into a filesystem-safe name."""
    text = re.sub(r"[^\w\s-]", "", str(text)).strip()
    text = re.sub(r"[\s]+", "_", text)
    return text[:limit] if text else "article"


def read_data(folder):
    pattern = os.path.join(folder, "*.csv")
    files = sorted(glob.glob(pattern))
    if not files:
        print(f"No CSV files found in folder: {folder}")
        sys.exit(1)

    print(f"Found {len(files)} CSV file(s):")
    for f in files:
        print(f"  - {os.path.basename(f)}")

    frames = []
    for file in files:
        try:
            df = pd.read_csv(file, encoding="utf-8")
            frames.append(df)
        except Exception as e:
            print(f"ERROR reading file {file}: {e}")
            sys.exit(1)

    data = pd.concat(frames, ignore_index=True)
    data = data.drop_duplicates(subset=["DOI"]) if "DOI" in data.columns else data.drop_duplicates()
    return data


def get_pdf_url_from_unpaywall(doi, email, session):
    """Returns a PDF URL if Unpaywall finds a legal open version."""
    try:
        resp = session.get(UNPAYWALL_URL.format(doi=doi), params={"email": email}, timeout=15)
        if resp.status_code != 200:
            return None, f"HTTP {resp.status_code}"
        data = resp.json()
        location = data.get("best_oa_location")
        if location and location.get("url_for_pdf"):
            return location["url_for_pdf"], None
        if location and location.get("url"):
            return location["url"], None
        return None, "No OA version available in Unpaywall"
    except Exception as e:
        return None, str(e)


def download_file(url, path, session):
    try:
        resp = session.get(url, timeout=30, stream=True)
        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code}"
        content_type = resp.headers.get("Content-Type", "")
        with open(path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return True, content_type
    except Exception as e:
        return False, str(e)


def main():
    parser = argparse.ArgumentParser(description="Download Open Access articles by DOI (Scopus CSV export)")
    parser.add_argument("--folder", required=True, help="Folder containing the CSV files")
    parser.add_argument("--output-dir", default="./downloaded_pdfs", help="Destination folder for downloaded files")
    parser.add_argument("--email", required=True, help="Email address required by the Unpaywall API")
    parser.add_argument("--abstracts", action="store_true", help="Save fetched abstracts to a separate abstracts.csv file")

    # --- Filtering ---
    parser.add_argument("--year-from", type=int, default=None, help="Only articles published from this year (inclusive)")
    parser.add_argument("--year-to", type=int, default=None, help="Only articles published up to this year (inclusive)")
    parser.add_argument("--doc-types", type=str, default=None,
                         help="Comma-separated list of allowed document types, e.g. 'Article,Review'")
    parser.add_argument("--min-citations", type=int, default=None, help="Minimum citation count (Cited by)")
    parser.add_argument("--oa-types", type=str, default=None,
                         help="Comma-separated list of allowed Open Access types, e.g. 'Gold' or 'Gold,Green'")
    parser.add_argument("--exclude-sources", type=str, default=None,
                         help="Comma-separated list of excluded journals/sources (partial, case-insensitive match)")
    parser.add_argument("--include-keywords", type=str, default=None,
                         help="Comma-separated keywords - keep the record if the title OR abstract contains ANY of them")
    parser.add_argument("--exclude-keywords", type=str, default=None,
                         help="Comma-separated keywords - drop the record if the title OR abstract contains ANY of them")

    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    data = read_data(args.folder)

    if "Open Access" not in data.columns or "DOI" not in data.columns:
        print("CSV files must contain the 'Open Access' and 'DOI' columns.")
        sys.exit(1)

    oa_data = data[data["Open Access"].notna() & (data["Open Access"].str.strip() != "")]
    oa_data = oa_data[oa_data["DOI"].notna() & (oa_data["DOI"].astype(str).str.strip() != "")]

    total_records = len(data)
    total_oa = len(oa_data)

    print(f"\nTotal unique records: {total_records}")
    print(f"Records marked Open Access with a DOI: {total_oa}")

    # --- Metadata-based filters (year, document type, citations, OA type, sources) ---
    oa_data, filter_log = apply_filters(oa_data, args)
    if len(filter_log) > 1:
        print("\nFiltering steps:")
        for label, count in filter_log:
            print(f"  {label}: {count}")

    # Do we need to fetch abstracts before further processing? (the keyword filter
    # checks the title AND the abstract)
    keywords_needed = bool(args.include_keywords or args.exclude_keywords)
    fetch_abstracts = args.abstracts or keywords_needed

    total_after_metadata = len(oa_data)
    print(f"\nRecords after metadata filters: {total_after_metadata}\n")

    downloaded = 0
    no_pdf = 0
    download_errors = 0
    abstracts_found = 0
    abstracts_missing = 0
    rejected_by_keywords = 0

    log_rows = []
    abstract_rows = []
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; OA-downloader/1.0)"})

    include_keywords = [s.strip().lower() for s in args.include_keywords.split(",")] if args.include_keywords else None
    exclude_keywords = [s.strip().lower() for s in args.exclude_keywords.split(",")] if args.exclude_keywords else None

    for i, (_, row) in enumerate(oa_data.iterrows(), start=1):
        doi = str(row["DOI"]).strip()
        title = row.get("Title", f"article_{i}")
        year = row.get("Year", "")
        authors = row.get("Authors", "")
        citations = row.get("Cited by", None)

        print(f"[{i}/{total_after_metadata}] {title[:80]}... (DOI: {doi})")

        abstract, source = (None, None)
        if fetch_abstracts:
            abstract, source = fetch_abstract(doi, args.email, session)
            time.sleep(REQUEST_DELAY_SEC)
            if abstract:
                abstracts_found += 1
                print(f"    -> Abstract found ({source})")
            else:
                abstracts_missing += 1
                print("    -> Abstract unavailable")
            if args.abstracts:
                abstract_rows.append({
                    "DOI": doi,
                    "Title": title,
                    "Year": year,
                    "Authors": authors,
                    "Abstract": abstract or "",
                    "Source": source or "",
                })

        # --- Keyword filter (title + abstract) ---
        if include_keywords and not matches_keywords(title, abstract, include_keywords):
            print("    -> Rejected: missing required keywords")
            rejected_by_keywords += 1
            log_rows.append({"DOI": doi, "Title": title, "Status": "rejected_keywords", "Details": "no matching include keywords"})
            continue
        if exclude_keywords and matches_keywords(title, abstract, exclude_keywords):
            print("    -> Rejected: contains an excluded keyword")
            rejected_by_keywords += 1
            log_rows.append({"DOI": doi, "Title": title, "Status": "rejected_keywords", "Details": "matched an exclude keyword"})
            continue

        pdf_url, error = get_pdf_url_from_unpaywall(doi, args.email, session)
        time.sleep(REQUEST_DELAY_SEC)

        if not pdf_url:
            print(f"    -> Skipped: {error}")
            no_pdf += 1
            log_rows.append({"DOI": doi, "Title": title, "Status": "no_pdf", "Details": error})
            continue

        try:
            citation_count = int(float(citations)) if pd.notna(citations) else 0
        except (ValueError, TypeError):
            citation_count = 0

        citations_part = f"{citation_count:05d}"
        year_part = str(year).strip() if pd.notna(year) and str(year).strip() else "no_year"
        title_part = safe_filename(title, limit=100)
        authors_part = safe_filename(authors, limit=60)
        filename = f"{citations_part}_{year_part}_{title_part}_{authors_part}.pdf"
        path = os.path.join(args.output_dir, filename)

        # If a file with this name already exists (two different articles with a
        # similar title), append a counter so we don't overwrite a previous download
        if os.path.exists(path):
            base, ext = os.path.splitext(filename)
            counter = 2
            while os.path.exists(path):
                filename = f"{base}_{counter}{ext}"
                path = os.path.join(args.output_dir, filename)
                counter += 1

        success, info = download_file(pdf_url, path, session)
        time.sleep(REQUEST_DELAY_SEC)

        if success:
            print(f"    -> Downloaded: {filename}")
            downloaded += 1
            log_rows.append({"DOI": doi, "Title": title, "Status": "downloaded", "Details": path})
        else:
            print(f"    -> Download error: {info}")
            download_errors += 1
            log_rows.append({"DOI": doi, "Title": title, "Status": "download_error", "Details": info})

    # Save log
    log_path = os.path.join(args.output_dir, "download_log.csv")
    pd.DataFrame(log_rows).to_csv(log_path, index=False, encoding="utf-8")

    abstracts_path = None
    if args.abstracts:
        abstracts_path = os.path.join(args.output_dir, "abstracts.csv")
        pd.DataFrame(abstract_rows).to_csv(abstracts_path, index=False, encoding="utf-8")

    print("\n--- SUMMARY ---")
    print(f"Total unique records in CSV:            {total_records}")
    print(f"Records marked as Open Access:          {total_oa}")
    print(f"Records after metadata filters:         {total_after_metadata}")
    if include_keywords or exclude_keywords:
        print(f"Rejected by keyword filter:             {rejected_by_keywords}")
    print(f"Successfully downloaded PDFs:           {downloaded}")
    print(f"No OA version available (Unpaywall):    {no_pdf}")
    print(f"Errors while downloading:               {download_errors}")
    if fetch_abstracts:
        print(f"Abstracts found:                        {abstracts_found}")
        print(f"Abstracts missing:                      {abstracts_missing}")
    print(f"\nDetailed log saved to: {log_path}")
    if abstracts_path:
        print(f"Abstracts saved to: {abstracts_path}")
    print(f"Downloaded files are located in: {args.output_dir}")


if __name__ == "__main__":
    main()

