# scopus-slr-tools

A small set of Python scripts for working with **Scopus** CSV exports, built for systematic literature reviews (SLR) and bibliometric research:

1. **`merge_csv.py`** — merges multiple CSV files with the same structure into one, removing duplicates.
2. **`download_oa_articles.py`** — filters records by your chosen criteria, then downloads legally available Open Access full texts (PDF) by DOI, with optional abstract fetching.

This project was built for researchers who want to quickly assemble a local library of Open Access full texts for further analysis (e.g. SLR screening), without manually clicking through dozens of links.

## Table of contents

- [Requirements](#requirements)
- [Installation](#installation)
- [1. Merging CSV files](#1-merging-csv-files)
- [2. Downloading Open Access articles](#2-downloading-open-access-articles)
  - [Filtering options](#filtering-options)
  - [Full example](#full-example)
  - [Output files](#output-files)
- [Data sources (APIs)](#data-sources-apis)
- [Limitations and notes](#limitations-and-notes)
- [License](#license)

## Requirements

- Python 3.9+
- Libraries: `pandas`, `requests` (see [`requirements.txt`](requirements.txt))
- CSV files exported from Scopus (Search Results → Export → CSV), containing the standard columns, e.g.: `Authors`, `Title`, `Year`, `Source title`, `Document Type`, `Cited by`, `DOI`, `Open Access`

## Installation

```bash
git clone https://github.com/YOUR-USERNAME/scopus-slr-tools.git
cd scopus-slr-tools
pip install -r requirements.txt
```

## 1. Merging CSV files

If you exported your Scopus search results in batches (Scopus exports a maximum of 2000 records at a time), `merge_csv.py` will combine all the files in a folder into one and remove duplicates.

```bash
python scripts/merge_csv.py --folder ./data --output merged.csv
```

**Arguments:**

| Argument | Description | Default |
|---|---|---|
| `--folder` | Folder containing the `.csv` files to merge (required) | — |
| `--output` | Output file name | `merged.csv` |
| `--encoding` | Encoding of input/output files | `utf-8` |
| `--sep` | Column separator | `,` |

At the end, the script prints: total records read, duplicates found, and records removed.

## 2. Downloading Open Access articles

`download_oa_articles.py` reads CSV files (it merges every file in the given folder itself and removes duplicates by DOI), selects records marked as Open Access, filters them by your criteria, and then:

- queries [Unpaywall](https://unpaywall.org) for a legal PDF link based on the DOI,
- downloads the file, naming it as `CitationCount_Year_Title_Authors.pdf` (makes it easy to sort by scholarly impact),
- optionally fetches an abstract from [CrossRef](https://www.crossref.org/) or, as a fallback, [Semantic Scholar](https://www.semanticscholar.org/product/api).

```bash
python scripts/download_oa_articles.py \
  --folder ./data \
  --output-dir ./downloaded_pdfs \
  --email you@email.com
```

> **An email address is required by Unpaywall** (the "polite pool") — this is a standard, free requirement of the API and does not involve any account registration.

### Filtering options

| Argument | Description | Example |
|---|---|---|
| `--year-from` / `--year-to` | Publication year range (`Year` column) | `--year-from 2019 --year-to 2024` |
| `--doc-types` | Allowed document types, exact match (`Document Type` column) | `--doc-types "Article,Review"` |
| `--min-citations` | Minimum citation count (`Cited by` column) | `--min-citations 5` |
| `--oa-types` | Allowed Open Access type, partial match (`Open Access` column) | `--oa-types "Gold"` |
| `--exclude-sources` | Excluded journals/sources, partial match (`Source title` column) | `--exclude-sources "Journal X"` |
| `--include-keywords` | Keep the record if the title **or** abstract contains any of the given words (OR logic) | `--include-keywords "misinformation,fake news"` |
| `--exclude-keywords` | Drop the record if the title **or** abstract contains any of the given words | `--exclude-keywords "protocol,editorial"` |
| `--abstracts` | Save fetched abstracts to a separate `abstracts.csv` file | — |

All filters are optional and can be combined freely. Metadata-based filters (year, document type, citations, OA type, sources) are applied first — before the script downloads anything from the internet. If you use `--include-keywords` or `--exclude-keywords`, the script will automatically fetch abstracts (even without `--abstracts`) so it can search them.

### Full example

```bash
python scripts/download_oa_articles.py \
  --folder ./data \
  --output-dir ./downloaded_pdfs \
  --email you@email.com \
  --year-from 2019 --year-to 2024 \
  --doc-types "Article,Review" \
  --min-citations 3 \
  --oa-types "Gold" \
  --exclude-keywords "protocol,editorial" \
  --abstracts
```

At the end, the script prints a full summary: total records, Open Access records, records remaining after each filter, PDFs downloaded, errors, and (if applicable) abstracts found/missing.

### Output files

Inside the folder given by `--output-dir` you'll find:

- downloaded `*.pdf` files, named as `CitationCount_Year_Title_Authors.pdf`,
- `download_log.csv` — a detailed log for every record (status: downloaded / no_pdf / download_error / rejected_keywords),
- `abstracts.csv` — if `--abstracts` was used (DOI, title, year, authors, abstract, abstract source).

## Data sources (APIs)

| Service | Purpose | Requires API key? |
|---|---|---|
| [Unpaywall](https://unpaywall.org/products/api) | Finding legal, open PDF versions by DOI | No (requires an email) |
| [CrossRef](https://api.crossref.org) | Fetching abstracts | No |
| [Semantic Scholar API](https://www.semanticscholar.org/product/api) | Fetching abstracts (fallback when not in CrossRef) | No |

## Limitations and notes

- The script downloads **only** content marked as Open Access and found by Unpaywall to be legally available — it does not bypass any paywalls.
- Not every article marked Open Access in Scopus (e.g. Hybrid Gold) will have a version indexed in Unpaywall — such cases are logged with status `no_pdf`, and the publisher's page link is always available in the original `Link` column of the CSV.
- The script pauses between requests (`REQUEST_DELAY_SEC` in the code) to avoid overloading the free APIs — for large datasets (hundreds/thousands of records), downloading may take a while.
- Filenames are stripped of characters not allowed in filesystems, but accented/diacritic characters (e.g. ó, ñ, í) are preserved.

## License

This project is available under the [MIT License](LICENSE).
