# Sources, provenance, and ranking

## Discovery signals

LitWatch preserves each signal rather than collapsing it into a claim:

| Label | Meaning | Direction |
|---|---|---|
| related | OpenAlex provider-supplied related-work edge | similarity, not chronology |
| reference | a seed cites the candidate | predecessor |
| citation | the candidate cites a seed | successor |
| search | metadata search matched the seed-derived query | lexical/topic match |
| pubmed_similar | PubMed Similar Articles linked the record | biomedical similarity |
| refresh | an already tracked record was checked again | lifecycle only |

The reference direction is taken from each seed's referenced_works list. The
successor direction uses an OpenAlex cites:SEED filter. Never describe the two
as interchangeable.

Every report record includes relationship_evidence entries with source,
channel, rank, and seed or query. metadata_sources records which providers
contributed fields. Provider values can disagree; counts from different
providers are not mixed.

## Ranking formula

The score is clamped to 0–100:

    55 * maximum positive-seed cosine
  + 10 * mean positive-seed cosine
  + 18 * channel evidence
  +  7 * independent-source consensus
  +  5 * recency over a 12-year horizon
  +  5 * log-scaled OpenAlex citation count
  - negative_seed_penalty * maximum negative-seed cosine

Title text is counted twice; abstracts and provider topics once. Latin tokens
and CJK bigrams are supported without an embedding dependency. This improves
portability but cannot fully resolve synonyms across distant vocabularies.
Negative seeds and extra search queries are the intended calibration knobs.

Channel evidence begins with the largest configured channel weight and gains a
small bonus from distinct channels, capped at 1.0. Citation count contributes
at most five points and never functions as a hard quality assertion unless the
user explicitly enables a citation filter.

The resulting score is a discovery-relevance score, not an evidence-quality,
risk-of-bias, truth, or interpretation-confidence score. Detailed readings must
inspect the available paper evidence separately under interpretation.md.

## Pagination and limits

OpenAlex list operations use cursor pagination until the configured channel
cap. Upstream totals larger than that cap set truncated on the channel and
bounded on the report. Network failures, malformed responses, and failed
enabled enrichments set complete=false.

HTTPS, finite retries, exponential backoff with jitter, Retry-After, and local
response caching are built into the script. Retry limits are deliberately
finite; an unattended run must terminate and disclose partial coverage.

## Current coverage boundaries

- OpenAlex abstracts are reconstructed only when an abstract inverted index is
  available. Missing abstracts reduce lexical confidence and can place a paper
  in pending.
- PubMed Similar Articles is optional and biomedical only.
- Crossref fields depend on publisher deposits; missing relation or license
  fields do not prove the absence of an event or license. LitWatch reads
  deposited accepted, posted, online, and print dates when present, but never
  treats Crossref created/deposited/indexed timestamps as manuscript submission
  or acceptance dates.
- OpenAlex primary, best-OA landing, and provider-identified PDF locations are
  kept as separate direct links. An OA URL can be a landing page rather than a
  PDF, and all remote URLs remain untrusted metadata.
- Direct arXiv, bioRxiv, medRxiv, Semantic Scholar, Google Scholar, CNKI, and
  Wanfang connectors are not part of version 2. OpenAlex can still surface many
  preprints.
- No result set is a systematic-review guarantee. High-stakes reviews require
  protocol-specific databases, documented search strings, and human screening.

Official documentation: OpenAlex API https://docs.openalex.org/ ; Crossref REST
https://www.crossref.org/documentation/retrieve-metadata/rest-api/ ; NCBI
E-utilities https://www.ncbi.nlm.nih.gov/books/NBK25497/ .
