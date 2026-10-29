#!/usr/bin/env python3
"""
doi_downloader.py - download article PDFs for a list of DOIs stored in a CSV file.

Sources tried, in order:
  1. Unpaywall API   - legal open-access copies (requires an e-mail address),
  2. Crossref API    - full-text links registered by the publisher,
  3. DOI landing page (doi.org) - a direct PDF or the citation_pdf_url meta tag.

Paywalled articles are downloaded only if you already have access to them
(e.g. when running the script from a university network with a subscription).

Requirements:  pip install -r requirements.txt

Examples:
  python doi_downloader.py example_dois.csv --email you@university.edu
  python doi_downloader.py my_list.csv --email you@university.edu --column DOI --out pdfs
  python doi_downloader.py my_list.csv --email you@university.edu --delay 2 --overwrite
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, urljoin

import requests

DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"<>]+", re.IGNORECASE)
TIMEOUT = 30  # seconds per HTTP request


# ------------------------------------------------------------------ reading the CSV

def normalize_doi(raw: str) -> str | None:
    """Extract a DOI from text (also handles 'https://doi.org/...' and 'doi:...')."""
    if not raw:
        return None
    m = DOI_RE.search(raw.strip())
    return m.group(0).rstrip(".,;)]") if m else None


def read_dois(csv_path: Path, column: str | None = None) -> list[str]:
    """Return a list of unique DOIs, in the order they appear in the file.

    If `column` is given, only that column is read. Otherwise the first column
    whose header contains "doi" is used; if there is none, every cell is scanned.
    """
    text = csv_path.read_text(encoding="utf-8-sig", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(text.splitlines(), dialect))
    if not rows:
        return []

    header = [h.strip().lower() for h in rows[0]]
    col_idx = None
    if column:
        if column.lower() not in header:
            sys.exit(f"Error: column '{column}' not found. Available columns: {rows[0]}")
        col_idx = header.index(column.lower())
    else:
        for i, h in enumerate(header):
            if "doi" in h:
                col_idx = i
                break

    found: list[str] = []
    data_rows = rows[1:] if col_idx is not None else rows
    for row in data_rows:
        cells = [row[col_idx]] if col_idx is not None and col_idx < len(row) else row
        for cell in cells:
            doi = normalize_doi(cell)
            if doi:
                found.append(doi)

    # DOIs are case-insensitive, so deduplicate on the lowercase form
    seen, unique = set(), []
    for d in found:
        key = d.lower()
        if key not in seen:
            seen.add(key)
            unique.append(d)
    return unique


# ------------------------------------------------------------------ finding PDF links

class PdfLinkParser(HTMLParser):
    """Collect <meta name="citation_pdf_url"> values and <a> links ending in .pdf."""

    def __init__(self):
        super().__init__()
        self.meta_pdf: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and (a.get("name") or "").lower() == "citation_pdf_url" and a.get("content"):
            self.meta_pdf.append(a["content"])
        elif tag == "a" and (a.get("href") or "").lower().split("?")[0].endswith(".pdf"):
            self.links.append(a["href"])


def candidates_unpaywall(session, doi, email):
    """Ask Unpaywall for open-access locations of the article."""
    try:
        r = session.get(f"https://api.unpaywall.org/v2/{quote(doi)}",
                        params={"email": email}, timeout=TIMEOUT)
        if r.status_code != 200:
            return []
        data = r.json()
    except (requests.RequestException, ValueError):
        return []
    urls = []
    locations = [data.get("best_oa_location")] + (data.get("oa_locations") or [])
    for loc in locations:  # direct PDF links first
        if loc and loc.get("url_for_pdf"):
            urls.append(("unpaywall", loc["url_for_pdf"]))
    for loc in locations:  # then landing pages
        if loc and loc.get("url"):
            urls.append(("unpaywall-landing", loc["url"]))
    return urls


def candidates_crossref(session, doi):
    """Ask Crossref for full-text links registered by the publisher."""
    try:
        r = session.get(f"https://api.crossref.org/works/{quote(doi)}", timeout=TIMEOUT)
        if r.status_code != 200:
            return []
        links = r.json().get("message", {}).get("link") or []
    except (requests.RequestException, ValueError):
        return []
    pdf = [l["URL"] for l in links if "pdf" in (l.get("content-type") or "")]
    other = [l["URL"] for l in links if l.get("content-type") in (None, "unspecified")]
    return [("crossref", u) for u in pdf + other]


# ------------------------------------------------------------------ downloading

def safe_filename(doi: str) -> str:
    """Turn a DOI into a file name that is safe on every operating system."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", doi).strip("_")[:200] + ".pdf"


def try_download(session, url, target: Path, follow_html=True) -> str | None:
    """Fetch `url`. If it is a PDF, save it to `target` and return the final URL.
    If it is an HTML page, look inside it for a PDF link and try that (one level deep).
    """
    try:
        r = session.get(url, timeout=TIMEOUT, stream=True, allow_redirects=True)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        r.close()
        return None

    ctype = (r.headers.get("Content-Type") or "").lower()
    chunks = r.iter_content(chunk_size=65536)
    first = next(chunks, b"")

    # Only save real PDFs: every PDF file starts with the bytes "%PDF"
    if first.startswith(b"%PDF"):
        tmp = target.with_suffix(".part")
        with open(tmp, "wb") as f:
            f.write(first)
            for c in chunks:
                f.write(c)
        tmp.replace(target)
        return r.url

    if follow_html and "html" in ctype:
        html = (first + b"".join(chunks)).decode(r.encoding or "utf-8", errors="replace")
        parser = PdfLinkParser()
        try:
            parser.feed(html)
        except Exception:
            pass
        for link in parser.meta_pdf + parser.links[:3]:
            got = try_download(session, urljoin(r.url, link), target, follow_html=False)
            if got:
                return got
    r.close()
    return None


def process(session, doi, out_dir: Path, email, overwrite) -> dict:
    """Try every source for one DOI and return a result row for the report."""
    target = out_dir / safe_filename(doi)
    if target.exists() and not overwrite:
        return {"doi": doi, "status": "skipped (exists)", "source": "", "url": "", "file": str(target)}

    candidates = candidates_unpaywall(session, doi, email)
    candidates += candidates_crossref(session, doi)
    candidates.append(("doi.org", f"https://doi.org/{doi}"))

    tried = set()
    for source, url in candidates:
        if url in tried:
            continue
        tried.add(url)
        got = try_download(session, url, target)
        if got:
            return {"doi": doi, "status": "OK", "source": source, "url": got, "file": str(target)}
    return {"doi": doi, "status": "no PDF found", "source": "", "url": "", "file": ""}


# ------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser(description="Download article PDFs for DOIs listed in a CSV file.")
    ap.add_argument("csv", type=Path, help="CSV file containing DOIs")
    ap.add_argument("--email", required=True, help="your e-mail address (required by Unpaywall/Crossref)")
    ap.add_argument("--column", help="name of the DOI column (default: detected automatically)")
    ap.add_argument("--out", type=Path, default=Path("downloads"), help="output folder (default: downloads)")
    ap.add_argument("--delay", type=float, default=1.0, help="pause between DOIs in seconds (default: 1)")
    ap.add_argument("--overwrite", action="store_true", help="overwrite files that already exist")
    args = ap.parse_args()

    if not args.csv.exists():
        sys.exit(f"Error: file not found: {args.csv}")

    dois = read_dois(args.csv, args.column)
    if not dois:
        sys.exit("No DOIs found in the file.")
    args.out.mkdir(parents=True, exist_ok=True)
    print(f"Found {len(dois)} DOIs. Saving to: {args.out.resolve()}\n")

    session = requests.Session()
    session.headers.update({
        # Unpaywall and Crossref ask clients to identify themselves with a contact address
        "User-Agent": f"doi-downloader/1.0 (mailto:{args.email})",
        "Accept": "application/pdf,text/html;q=0.9,*/*;q=0.8",
    })

    results = []
    for i, doi in enumerate(dois, 1):
        res = process(session, doi, args.out, args.email, args.overwrite)
        results.append(res)
        print(f"[{i}/{len(dois)}] {doi}: {res['status']}" + (f" ({res['source']})" if res["source"] else ""))
        if i < len(dois):
            time.sleep(args.delay)  # be polite to the servers

    report = args.out / "report.csv"
    with open(report, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["doi", "status", "source", "url", "file"])
        w.writeheader()
        w.writerows(results)

    ok = sum(r["status"] == "OK" for r in results)
    skipped = sum(r["status"].startswith("skipped") for r in results)
    print(f"\nDownloaded: {ok}, skipped: {skipped}, no PDF: {len(results) - ok - skipped}")
    print(f"Report: {report}")


if __name__ == "__main__":
    main()
