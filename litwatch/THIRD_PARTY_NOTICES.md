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

Compatibility with the common ShowJCR-style CSV layout is parser behavior only.
The ShowJCR code license does not by itself grant rights to redistribute the
underlying Clarivate JCR or CAS partition datasets.

PDF parsing is optional and uses a separately installed `pypdf` package under
that package's license. No `pypdf` code is vendored here.
