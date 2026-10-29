# DOI Downloader

A small Python command-line tool that reads a list of DOIs from a CSV file and
downloads the full-text PDF of each article, using only legal sources.

This repository is used in class. See **[EXERCISES.md](EXERCISES.md)** for the tasks.

## What is a DOI?

A **DOI** (Digital Object Identifier) is a permanent identifier for a scholarly
publication, e.g. `10.1371/journal.pcbi.1003285`. Putting `https://doi.org/` in
front of it always leads to the article's page, even if the publisher's website changes.

## How it works

For every DOI the script tries these sources, in order, and stops at the first PDF it finds:

1. **[Unpaywall](https://unpaywall.org/products/api)** - a database of legal open-access copies
   (publisher sites, institutional repositories, preprint servers).
2. **[Crossref](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)** - full-text
   links registered by the publisher.
3. **The DOI landing page** - follows `https://doi.org/<DOI>`; if the page is HTML, it looks for a
   `citation_pdf_url` meta tag or a link ending in `.pdf`.

A file is saved only if it really is a PDF (it must start with the bytes `%PDF`).
At the end the script writes `report.csv` with the result for every DOI.

> **Note:** paywalled articles are downloaded only if you already have access to them,
> for example when running the script from a university network with a subscription.
> The tool does not bypass paywalls.

## Project structure

```
doi-downloader/
├── doi_downloader.py      # the script
├── example_dois.csv       # sample input
├── requirements.txt       # runtime dependencies
├── requirements-dev.txt   # + pytest for running tests
├── tests/
│   └── test_parsing.py    # offline unit tests
├── EXERCISES.md           # class exercises
├── LICENSE
└── README.md
```

## Setup

You need **Python 3.9 or newer**.

```bash
git clone <repository-url>
cd doi-downloader

python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements-dev.txt
```

## Usage

```bash
python doi_downloader.py example_dois.csv --email you@university.edu
```

Unpaywall requires a real e-mail address. It is used only to identify you to the API.

| Option        | Description                                                  | Default       |
|---------------|--------------------------------------------------------------|---------------|
| `csv`         | CSV file with DOIs (required)                                | -             |
| `--email`     | your e-mail address (required)                               | -             |
| `--column`    | name of the column with DOIs                                 | auto-detected |
| `--out`       | output folder                                                | `downloads`   |
| `--delay`     | pause between DOIs, in seconds                               | `1`           |
| `--overwrite` | download again even if the file already exists               | off           |

### Input format

- Any delimiter works: comma, semicolon, tab or `|`.
- The DOI column is detected automatically if its header contains the word `doi`
  (case-insensitive). Otherwise use `--column`, or every cell is scanned.
- DOIs can be written as `10.xxxx/...`, `doi:10.xxxx/...` or `https://doi.org/10.xxxx/...`.
- Duplicates and rows without a valid DOI are ignored.

### Example output

```
Found 5 DOIs. Saving to: /home/student/doi-downloader/downloads

[1/5] 10.1371/journal.pcbi.1003285: OK (unpaywall)
[2/5] 10.1038/s41586-020-2649-2: OK (unpaywall)
[3/5] 10.7717/peerj.4375: OK (unpaywall)
[4/5] 10.1038/sdata.2016.18: OK (unpaywall)
[5/5] 10.1038/nature14539: no PDF found

Downloaded: 4, skipped: 0, no PDF: 1
Report: downloads/report.csv
```

(Your results may differ depending on your network and on the publishers' servers.)

## Running the tests

```bash
pytest
```

The tests do not use the internet - they check DOI parsing, CSV reading,
file naming and HTML link extraction.

## Good practice

- Keep the default `--delay` or increase it; do not flood the servers with requests.
- Downloaded PDFs are ignored by Git (`.gitignore`) - **do not commit them**; many are
  copyrighted even when they are free to read.
- Respect the license of every article you download.

## License

The code is released under the [MIT License](LICENSE).
