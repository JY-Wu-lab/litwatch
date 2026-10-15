# Workspace and output schema

## Workspace

    WORKSPACE/
    ├── config.json
    ├── litwatch.db
    ├── inputs/                         optional, user-created, never auto-scanned
    ├── local-metrics/                  optional, user-created, never auto-imported
    └── reports/                        after the first saved run
        ├── YYYYMMDDTHHMMSS.ffffffZ.json
        ├── YYYYMMDDTHHMMSS.ffffffZ.md
        ├── latest.json
        ├── latest.md
        ├── library.csv
        └── accepted_papers.xlsx

The `reports/` directory and all files under it are created only by the first
saved (non-dry-run) discover or watch. init creates config/database state and
imports the bundled 2025 metric snapshots into SQLite; it does not copy their
CSV files into the workspace. A dry run does not create or update report files.

Run files are immutable and timestamped, so two runs on one day cannot
overwrite each other. The latest files are atomically updated copies of the
newest saved run. library.csv and accepted_papers.xlsx are rebuilt atomically
from SQLite.

File and directory meanings:

| Path | Meaning |
|---|---|
| `config.json` | User-editable discovery, ranking, source, and filter settings. |
| `litwatch.db` | SQLite source of truth: seeds, works, aliases, events, run state, cache, and imported metric rows. |
| `litwatch.db-wal`, `litwatch.db-shm` | SQLite sidecars that may appear while the database is open. Do not edit or delete them during a run. |
| `.litwatch.lock` | Short-lived single-writer lock. It normally disappears when a command finishes; after a crash an old lock requires inspection before manual removal. |
| `inputs/` | Optional user filing convention for seed files. LitWatch never scans it automatically. |
| `local-metrics/` | Optional private location for source CSV files. Placement alone does not import them, and import stores normalized rows rather than copying the source file. |
| timestamped `.json` | Immutable, complete structured result for one saved run. |
| timestamped `.md` | Human-readable summary of that run; abstracts may be shortened. |
| `latest.json`, `latest.md` | Copies of the newest saved run, replaced atomically each time. |
| `library.csv` | Cumulative latest state of all stored works, including accepted, pending, and rejected. |
| `accepted_papers.xlsx` | Cumulative deduplicated view of works accepted at least once; new acceptances append logically and existing rows update. |

## Report JSON

Top-level fields:

- schema_version: currently 1.
- run_id: a unique UTC ID for saved runs; the literal `dry-run` for previews.
- mode: `discover` or `watch`; previewing does not create a third mode.
- complete: false when an enabled API, parser, or enrichment failed.
- bounded: true when an explicit configured result cap was reached.
- warnings and source_status: coverage details.
- counts: evaluated and reported category counts.
- accepted, pending, rejected: arrays of paper records.

Counts and arrays use the report-output scope, not an all-time audit scope. A
saved report can omit rejected records when `output.include_rejected=false` or
truncate them at `output.max_rejected`; its `counts.rejected` is the number
actually written. A dry-run preview is not truncated this way. Use SQLite or
the saved `library.csv` for cumulative state; `complete=true` does not promise
that a saved rejected array is exhaustive.

## Cumulative table exports

`library.csv` contains the latest state of every stored work, including
accepted, pending, and rejected records.

`accepted_papers.xlsx` contains one row for every work that has ever had an
accepted screening state. Rows are ordered by first acceptance, so newly
accepted works appear at the bottom. A matching work updates the existing row;
it is not appended again. A later pending/rejected state does not erase the row:
`current_status`, score, reasons, metadata, and links show the latest saved
state, while `litwatch_first_accepted_at` preserves when LitWatch first accepted
it. This timestamp is a LitWatch screening timestamp and must not be confused
with the article's `accepted_date`.

The worksheet is a flat, filterable table with a frozen header and first column.
It includes core bibliographic data, abstract, identifiers, screening evidence,
publication-history dates, OA state, journal metrics, provenance, and validated
HTTPS links. The rightmost JSON columns preserve complex score, relationship,
metric, and relation structures. Text is stored as literal cell data rather
than formulas, and overlong/invalid XML text is safely bounded. Excel's maximum
of 1,048,576 rows is enforced.

The XLSX is an output, not an editable input. It is fully and atomically rebuilt
from SQLite after each saved run, which provides logical append/update behavior
without risking in-place ZIP corruption. Manual workbook edits are overwritten.
On Windows, close the workbook before a run so Excel does not block replacement.

Each paper record contains stable identifiers, URL, title/authors/abstract,
publication state, score and components, reasons, relationship_evidence,
lifecycle events, OA data, journal metrics, and metadata provenance.
Each local JCR/CAS metric item includes `provider`, `metric_year`, and `source`;
`source` is `ShowJCR snapshot` for the bundled files and `local import` for a
user-imported file.
`publication_history` has submitted, received, revised (an array), accepted,
published_online, published_print, and posted values. Missing scalar dates are
null and missing revisions are an empty array. A date can be `YYYY`, `YYYY-MM`,
or `YYYY-MM-DD`, preserving provider precision. Missing metadata does not prove
that an event did not occur.

`links` separates DOI, publisher, OpenAlex primary-location, open-access,
provider-identified direct PDF, PubMed, arXiv, and OpenAlex URLs. Empty strings
mean unavailable. Only validated HTTPS links are emitted in these structured
fields; the legacy `url` remains the preferred identifier link. An
open_access link is not necessarily a PDF. `open_access.pdf_url` exposes the
same provider-identified PDF URL when available.
untrusted_fields highlights high-risk free-text fields; it is not exhaustive.
Treat every provider- or user-derived string, including URLs, licenses,
relations, warnings, and source-status queries, as untrusted data.

open_access.is_oa is tri-state: true means positive free-to-read evidence,
false means known negative evidence, and null means unknown. Consumers must not
coerce null to false; PubMed-only records commonly remain unknown. A journal
metric check on a preprint can be not_applicable rather than missing, including
under the exclude_strict missing-value policy.

The `abstract` field is provider/user metadata, not proof that the full article
was inspected. Downstream interpretation must label its evidence basis and must
not infer unreported methods, results, or limitations from an empty or partial
abstract. See interpretation.md.

Crossref `created`, `deposited`/`updated`, and `indexed` timestamps are not
manuscript submission or acceptance dates and are deliberately excluded from
publication_history. Accepted/online/print/posted fields depend on publisher
deposits; PubMed history can additionally supply received/revised/accepted
events for indexed biomedical records. Detailed interpretation should verify
dates in the article or publisher record and cite the source.

## SQLite

- seeds stores cumulative positive and negative examples.
- works stores the latest merged record and screening state.
- aliases maps DOI, PMID, arXiv, and OpenAlex identifiers to one stable work key.
  Titles are not unique aliases because distinct papers can share a title.
- events deduplicates discovery, publication, correction, concern, retraction,
  and relevance-state changes.
- source_state advances the date-search checkpoint only after an attempted,
  successful, untruncated search and also records lifecycle rotation times.
- runs stores immutable run summaries.
- journal_metrics stores bundled or user-imported normalized rows with metric
  year and source hash.
- http_cache stores response bytes under SHA-256 URL keys.

SQLite is the source of truth. JSON, CSV, and XLSX are reports, not state inputs.

## Lifecycle behavior

- A newly seen relevant record is reported once by watch.
- A routine preprint metadata/version refresh updates state silently.
- An identifier-linked record that changes from preprint to published emits
  published.
- Newly observed correction, expression-of-concern, or retraction relations
  emit their own event even if the paper is no longer accepted.
- Identifier aliases are persisted together, so later DOI enrichment does not
  create a second paper when another alias already matches.
- Records that were ever accepted or pending keep rotating through lifecycle
  checks even after a later rejection; oldest checks run first.

Provider metadata is imperfect. Title-only duplicates and preprint/journal
versions without an overlapping strong identifier require human review.
