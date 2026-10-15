# Third-party services and data

LitWatch code is MIT licensed. It does not bundle journal rankings, impact
factors, paper full text, or code copied from the reference repository.

Live discovery can contact OpenAlex, Crossref, and optionally PubMed. Their
data and APIs remain governed by their own terms. Users are responsible for
rate limits, attribution, privacy, and downstream rights.

JCR and Chinese Academy of Sciences (CAS) journal partition data are not
included. The local importer stores normalized rows in the user's workspace
only; it does not grant a license to obtain, copy, publish, or redistribute the
source data.

The original publishers are Clarivate for Journal Citation Reports and the
Chinese Academy of Sciences National Science Library for its historical Journal
Partition Table. The latter announced that it stopped updating and publishing
the table from 2026; 2025 is the final official historical CAS edition:
https://cssar.cas.cn/library/dtxx/202604/t20260409_8183275.html

Clarivate's published JCR usage guidance states that wholesale sharing outside
a subscriber's institution is prohibited and that some publication uses require
permission:
https://clarivate.com/academia-government/blog/a-quick-refresher-on-journal-citation-reports-use-cases-branding-and-terms-of-use/

Compatibility with the common ShowJCR-style CSV layout is parser behavior only.
The ShowJCR code license does not by itself grant rights to redistribute the
underlying Clarivate JCR or CAS partition datasets.

PDF parsing is optional and uses a separately installed `pypdf` package under
that package's license. No `pypdf` code is vendored here.
