# Sources, provenance, and ranking

## Discovery signals

LitWatch preserves each signal rather than collapsing it into a claim:

| Label | Meaning | Direction |
|---|---|---|
| related | OpenAlex provider-supplied related-work edge | similarity, not chronology |
| reference | a seed cites the candidate; supplied by OpenAlex, high-confidence Crossref deposits, or PubMed/PMC when available | predecessor |
| citation | the candidate cites a seed; supplied by OpenAlex or PubMed's open citation links when available | successor |
| search | metadata search matched the seed-derived query | lexical/topic match |
| pubmed_similar | PubMed Similar Articles linked the record | biomedical similarity |
| semantic_scholar_recommended | Semantic Scholar recommended the record from an identifier seed | provider-ranked similarity |
| refresh | an already tracked record was checked again | lifecycle only |

The reference direction is taken from a seed's deposited/provider reference
list. The successor direction uses an OpenAlex `cites:SEED` filter or PubMed's
`pubmed_pubmed_citedin` link. Never describe the two as interchangeable.
Crossref's ordinary REST API does not return a general citing-paper list: it
returns deposited backward references and `is-referenced-by-count`. LitWatch
therefore never labels a Crossref count as a set of citing papers. To keep noisy
deposits out, a Crossref reference becomes a candidate only when both DOI and
title are present.

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
A negative seed should represent an unwanted concept, not a recommendation,
commentary, correction, or duplicate whose text repeats a positive seed. Such a
near-duplicate can penalize the desired vocabulary globally; use document-type
or literal title exclusions for that record class instead.

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

## OpenAlex 429 and fallback behavior

OpenAlex can return 429 for a short per-second limit or an exhausted daily
budget. LitWatch retries only a finite number of times. If the response says the
remaining budget is zero, it stops immediately; after a terminal 429 it avoids
more requests to the same host during that run. The report remains
`complete=false`, retains the warning, and continues every alternative already
enabled in `config.json`:

1. Crossref deposited DOI references are available by default when
   `crossref.enabled=true` and `discovery.references=true`.
2. PubMed Similar Articles, references, and citing links run when
   `pubmed.enabled=true`, the seed has a PMID, and `NCBI_EMAIL` is set. The
   default per-channel cap is 100, not a guarantee that every seed has 100
   usable links.
3. Semantic Scholar recommendations run only when
   `semantic_scholar.enabled=true`. `SEMANTIC_SCHOLAR_API_KEY` is optional but
   strongly recommended because anonymous traffic shares a throttled pool.

Fallback results do not retroactively make the failed OpenAlex coverage
complete. `complete=false` means “partial run”, not “no relevant papers”. The
OpenAlex website uses the same API and budget, so changing from CLI to the
website is not a fallback. Connected Papers and Litmaps are manual exploration
tools: export or copy permitted DOI/BibTeX/RIS identifiers and add them with
`seed add`; LitWatch does not scrape those sites or pretend their graph order is
its deterministic score.

## Current coverage boundaries

- OpenAlex abstracts are reconstructed only when an abstract inverted index is
  available. Missing abstracts reduce lexical confidence and can place a paper
  in pending.
- PubMed Similar Articles is optional and biomedical only.
- PubMed reference links generally require that the seed is also represented in
  PMC, and its citing links are limited to the NIH Open Citation Collection;
  absence is not proof of no references or citations.
- Crossref fields depend on publisher deposits; missing relation or license
  fields do not prove the absence of an event or license. LitWatch reads
  deposited accepted, posted, online, and print dates when present, but never
  treats Crossref created/deposited/indexed timestamps as manuscript submission
  or acceptance dates.
- OpenAlex primary, best-OA landing, and provider-identified PDF locations are
  kept as separate direct links. An OA URL can be a landing page rather than a
  PDF, and all remote URLs remain untrusted metadata.
- Semantic Scholar is an optional recommendation source and can itself return
  429; a failure is disclosed and never silently replaced with fabricated
  recommendations. Direct arXiv, bioRxiv, medRxiv, Google Scholar, CNKI, and
  Wanfang connectors are not included. OpenAlex can still surface many preprints.
- No result set is a systematic-review guarantee. High-stakes reviews require
  protocol-specific databases, documented search strings, and human screening.

Official documentation: OpenAlex API and limits
https://help.openalex.org/api/authentication/ ; Crossref REST
https://www.crossref.org/documentation/retrieve-metadata/rest-api/ ; NCBI
E-utilities https://www.ncbi.nlm.nih.gov/books/NBK25497/ ; PubMed citation links
https://pmc.ncbi.nlm.nih.gov/tools/cites-citedby/ ; Semantic Scholar API
https://www.semanticscholar.org/product/api .
