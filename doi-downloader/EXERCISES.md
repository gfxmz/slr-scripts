# Class Exercises

Work in your own fork or branch. Commit after each exercise with a clear message,
e.g. `Exercise 3: add progress bar`.

Before you start, make sure the setup works:

```bash
pip install -r requirements-dev.txt
pytest
python doi_downloader.py example_dois.csv --email you@university.edu
```

---

## Part 1 - Understand the code (warm-up)

**1.1** Run the script on `example_dois.csv`. Open `downloads/report.csv`.
Which articles were downloaded, and from which source? Which one failed, and why?

**1.2** Open `https://api.unpaywall.org/v2/10.7717/peerj.4375?email=you@university.edu`
in your browser. Find the fields `is_oa`, `best_oa_location` and `url_for_pdf`.
Explain how `candidates_unpaywall()` uses them.

**1.3** Why does `try_download()` check whether the file starts with `%PDF` instead of
trusting the `Content-Type` header? Find (or think of) a case where the header lies.

**1.4** Create your own CSV with at least 10 DOIs from your field of study
(use Google Scholar, PubMed or the journal websites). Use a semicolon as the delimiter
and name the column `Identifier`. Run the script. What percentage was downloaded?

---

## Part 2 - Small improvements

**2.1 Better file names.**
Add an option `--name-by title` that names files after the article title instead of the DOI
(e.g. `Array_programming_with_NumPy.pdf`). The title can be taken from the Crossref response
(`message.title[0]`). Keep the DOI-based name as the default.

**2.2 Progress bar.**
Replace the `[i/n]` print with a progress bar using the `tqdm` library.
Remember to add it to `requirements.txt`.

**2.3 Retries.**
Network requests sometimes fail temporarily (timeouts, HTTP 429 or 503).
Add automatic retries with exponential backoff (e.g. wait 1 s, 2 s, 4 s).
Hint: look at `requests.adapters.HTTPAdapter` and `urllib3.util.Retry`.

**2.4 Richer report.**
Add the columns `title`, `year`, `is_oa` and `file_size_kb` to `report.csv`.

---

## Part 3 - Tests

**3.1** Write a test for `normalize_doi()` with at least three new edge cases
(e.g. a DOI in parentheses, a DOI with uppercase letters, a DOI inside a longer sentence).

**3.2** Write a test for `process()` **without using the internet**.
Hint: use `unittest.mock.patch` to replace `candidates_unpaywall`, `candidates_crossref`
and `try_download` with fake functions.

**3.3** Write a test that checks that a file which already exists is skipped
(status `skipped (exists)`) and is overwritten when `overwrite=True`.

---

## Part 4 - Bigger features (choose one)

**4.1 Parallel downloads.**
Use `concurrent.futures.ThreadPoolExecutor` to download several DOIs at once.
Add a `--workers` option (default 4). How much faster is it for 20 DOIs?
Why should the number of workers stay small?

**4.2 Metadata export.**
Add an option `--bibtex refs.bib` that saves a BibTeX entry for every DOI.
Hint: `https://doi.org/<DOI>` returns BibTeX when you send the header
`Accept: application/x-bibtex`.

**4.3 Resume.**
If the script is interrupted, running it again should continue where it stopped
and keep the results from the previous run in `report.csv`.

**4.4 Statistics.**
Write a separate script `stats.py` that reads `report.csv` and prints (or plots with
`matplotlib`) the share of open-access articles per year and per source.

---

## Discussion questions

- Why do Unpaywall and Crossref ask for your e-mail address?
- What is the difference between *free to read* and *open access* (e.g. CC BY licence)?
- Is it OK to share the PDFs you downloaded with classmates? What does it depend on?
- What could you add to this tool so it is useful for writing your thesis?
