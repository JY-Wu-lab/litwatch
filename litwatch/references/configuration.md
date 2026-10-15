# Configuration

The workspace config is JSON and uses schema version 1. Unknown keys are
rejected so spelling mistakes cannot silently change a literature screen.
Run doctor after edits.

## Seed JSON contract

A seed JSON file contains one object or a non-empty array of objects. Each
object must have a non-empty title or a valid doi, pmid, arxiv_id, or
openalex_id. Text fields include title, abstract, the identifiers, journal,
publication_date, submitted_date, received_date, accepted_date,
published_online_date, published_print_date, posted_date, publisher_url,
primary_url, oa_url, oa_pdf_url, and type. authors, topics, licenses, issns, and
revised_dates are arrays of strings. year is a four-digit integer (a four-digit string is normalized), and
is_preprint, is_retracted, and is_oa are boolean or null. Example:

~~~json
{"title":"Example paper","doi":"10.1234/example.1","authors":["A. Researcher"],"year":2025}
~~~

Use `seed add --offline` for private/local JSON or whenever no network access is
intended. Without it, LitWatch may send supplied identifiers or titles to an
enabled metadata API for resolution.

## Sources

- OpenAlex is the default discovery graph and metadata source.
- Crossref is enabled for DOI metadata, license fields, version relations,
  corrections, and retractions. Limit enrichment with enrich_limit.
- PubMed is optional. When enabled, set NCBI_EMAIL to a real contact address;
  NCBI_API_KEY is optional.

API keys and email addresses belong in environment variables, never config.
Their fixed names are OPENALEX_API_KEY, OPENALEX_EMAIL, CROSSREF_EMAIL,
NCBI_EMAIL, and NCBI_API_KEY; config cannot rename them. LitWatch hashes cache
keys, so secrets in query strings are not stored.

## Discovery

related, references, citations, and search independently enable four OpenAlex
channels. max_per_channel and max_candidates are explicit safety bounds. A
report with bounded=true completed the configured search but more upstream
matches existed. A report with complete=false suffered an API, parsing, or
enrichment failure and must not be interpreted as “no relevant papers”.
Known publication dates from every discovery channel are checked against
--since/--until; `--until` cannot be later than today. Candidates with missing
dates remain reviewable.

initial_lookback_days is used by the first watch. Later watches start from the
successful openalex_search checkpoint minus overlap_days. A failed, truncated,
or skipped search does not advance that checkpoint; historical runs cannot move
it backward.

include_preprints controls screening, not retrieval. Preprints remain clearly
marked. lifecycle_recheck_limit bounds records that were ever accepted or
pending and are refreshed on each watch for publication, correction, concern,
and retraction events. Records rotate oldest-check first and remain monitored
after a later rejection. A recheck or Crossref enrichment cap is disclosed with
bounded=true and a warning.

## Ranking

Scores are deterministic and range from 0 to 100. They combine lexical cosine
similarity to positive seeds, discovery-channel evidence, independent-source
consensus, recency, and a small log-scaled citation signal. Similarity to
negative seeds subtracts a configurable penalty. See sources-and-ranking.md for
the exact weights.

accept_score and pending_score split the feed into accepted, pending, and
rejected. The precision-biased defaults are 55 and 35. Tune them with discover
--dry-run --explain against labeled relevant/irrelevant examples; filters can
demote an otherwise high-scoring record.

## General filters

- year_min and year_max are inclusive; null disables them.
- document_types is empty by default. Common provider aliases are normalized;
  useful canonical values include article, review, preprint,
  proceedings-article, book-chapter, and dataset.
- profile.exclude_title_terms is an optional literal case-insensitive title
  exclusion. Prefer negative seeds when a concept, rather than an exact phrase,
  is unwanted.
- open_access.mode can be off, free_to_read, or open_license. A free landing
  page is not automatically an open license. licenses is used only by
  open_license and must be a non-empty allow-list in that mode (for example,
  cc-by). Known Creative Commons URLs/versions are normalized, then license IDs
  are matched exactly: allowing cc-by does not allow cc-by-nc. OA evidence is
  tri-state: true passes free_to_read, false fails, and unknown/null becomes
  pending only when the record reaches pending_score. PubMed does not itself
  establish OA status, so PubMed-only records normally remain unknown.
- citations.minimum is disabled by null. grace_period_days protects recent
  papers from an inherently age-biased citation threshold.

## Journal metrics

The default is annotation only: metrics.hard_filter=false. This is deliberate;
journal metrics are venue-level proxies, not paper-quality scores.

When hard_filter is true, every configured criterion is combined with AND:

- OpenAlex min_2yr_mean_citedness: public OpenAlex source statistic. It is not
  Journal Impact Factor and must never be labeled JIF.
- JCR quartiles, minimum impact factor, and optional categories: use only local
  authorized imports. year selects an exact metric edition; null uses the
  latest dated import. aggregation is worst by default across matched category
  quartiles; best is available only when explicitly selected.
- CAS zones: choose major or minor scope and best/worst aggregation.
  year has the same exact-edition/null-latest behavior.

Missing can be pending (default), include, or exclude_strict. Journal metrics
are not applicable to preprints: those checks are marked not_applicable and do
not reject a preprint even under exclude_strict. Use include_preprints or
document_types when preprints themselves should be excluded.

Import examples:

    python scripts/litwatch.py metrics import --workspace WORKSPACE --provider jcr --file JCR.csv --year 2025
    python scripts/litwatch.py metrics import --workspace WORKSPACE --provider cas --file CAS.csv --year 2025
    python scripts/litwatch.py metrics status --workspace WORKSPACE

`--year` is required and identifies the metric edition, not a paper publication
year. Input may be long form, with one journal/category combination per row, or
a common wide layout. Wide JCR columns such as `Category_1` and
`IF Quartile(2025)_1`, and wide CAS columns such as `ISSN/EISSN`, `大类分区`,
and `小类1分区`, are expanded automatically. Repeat a journal-level JIF on each
long-form category row.

The importer detects common English and Chinese headers. For uncommon files,
pass a mapping JSON whose keys are canonical fields and values are exact CSV
headers. Supported keys are journal, issn, eissn, category, quartile,
impact_factor, cas_major_category, cas_major_zone, cas_minor_category, and
cas_minor_zone, and top. The input file is hashed but never copied.

`metrics status` reports which provider/year editions are actually loaded.
`doctor` also fails when a configured JCR/CAS hard filter has no matching local
edition. No import means no JCR/CAS annotation or truthful partition filter;
OpenAlex two-year mean citedness is a different statistic and is never used to
infer a partition.

Set filters.metrics.jcr.year and filters.metrics.cas.year to an imported year
for reproducible comparisons; null deliberately selects the latest dated import.
The year remains attached to every annotation. JIF is a journal-year value, not
a category value. Conflicting JIF values for one journal identifier/year inside
one file reject the import atomically. If matches from different identifiers or
prior data still disagree, LitWatch reports a data conflict and leaves that
filter pending. Aggregation applies to category quartiles, never to JIF.

JCR and CAS data are intentionally absent from this repository. Their official
terms restrict redistribution; possession of a third-party mirror does not
prove redistribution rights.

## Preset

pathology-molecular only adds three search queries and two obvious imaging
exclusions. It contains no papers, journal lists, or hidden thresholds. Seeds
remain the source of truth and the preset can be edited after init.
