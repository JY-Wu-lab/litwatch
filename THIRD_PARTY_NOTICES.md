# Third-party services and data

LitWatch code is MIT licensed. No paper full text or ShowJCR program code is
included. Two journal-metric CSV snapshots are bundled separately under
`bundled-metrics/` so a new workspace works without manual data setup:

- `JCR2025-UTF8.csv`: JCR 2025 quartiles and impact factors.
- `FQBJCR2025-UTF8.csv`: historical CAS 2025 partitions.

Both files came from the public [hitfyd/ShowJCR repository](https://github.com/hitfyd/ShowJCR),
whose repository license is GPL-3.0. The files retain those upstream terms;
the license text is in `bundled-metrics/COPYING.GPL-3.0`, and exact hashes and
source-row counts are recorded in `bundled-metrics/README.md`.

Live discovery can contact OpenAlex, Crossref, and optionally PubMed and
Semantic Scholar. Their data and APIs remain governed by their own terms.
Users are responsible for rate limits, attribution, privacy, and downstream
rights.

`init` verifies the bundled files, then stores normalized rows in the user's
workspace database. A ShowJCR snapshot is not an official export or an
authenticity certificate. Formal evaluation should be checked against the
original provider. User-supplied editions are not copied into the package or
workspace and remain governed by the user's own access terms.

The original publishers are Clarivate for Journal Citation Reports and the
Chinese Academy of Sciences National Science Library for its historical Journal
Partition Table. The latter announced that it stopped updating and publishing
the table from 2026; 2025 is the final official historical CAS edition. Its
official notice is available at:
https://www.cssar.cas.cn/library/dtxx/202604/t20260409_8183275.html

JCR access, export, API use, and downstream reuse remain subject to Clarivate's
current subscription and usage terms. Official product and download guidance:
https://clarivate.com/academia-government/scientific-and-academic-research/research-funding-analytics/journal-citation-reports/
https://journalcitationreports.zendesk.com/hc/en-gb/articles/28351328522257-Downloading-Information

The upstream repository's GPL-3.0 notice and public availability do not change
any separate rights or access conditions asserted by Clarivate or the historical
CAS platform. Republishing a fork should retain this notice and the bundled-data
README and should be reviewed under the publisher's applicable terms.

PDF parsing is optional and uses a separately installed `pypdf` package under
that package's license. No `pypdf` code is vendored here.
