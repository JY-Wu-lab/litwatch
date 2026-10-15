# Workspace and output schema

## Workspace

    WORKSPACE/
      config.json
      litwatch.db
      reports/
        YYYYMMDDTHHMMSS.ffffffZ.json
        YYYYMMDDTHHMMSS.ffffffZ.md
        latest.json
        latest.md
        library.csv

The `reports/` directory and all files under it are created only by the first
saved (non-dry-run) discover or watch. init creates only config/database state;
a dry run does not create or update report files.

Run files are immutable and timestamped, so two runs on one day cannot
overwrite each other. latest files are atomic pointers by content. library.csv
is rebuilt atomically from SQLite.

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

Each paper record contains stable identifiers, URL, title/authors/abstract,
publication state, score and components, reasons, relationship_evidence,
lifecycle events, OA data, journal metrics, and metadata provenance.
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
- journal_metrics stores locally imported authorized rows with metric year and
  source hash.
- http_cache stores response bytes under SHA-256 URL keys.

SQLite is the source of truth. JSON and CSV are reports, not state inputs.

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
