from __future__ import annotations

import argparse
import io
import importlib.util
import json
import os
import sqlite3
import tempfile
import unittest
import zipfile
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
import xml.etree.ElementTree as ET


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "litwatch.py"
SPEC = importlib.util.spec_from_file_location("litwatch_module", SCRIPT)
assert SPEC and SPEC.loader
lw = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lw)


def work(**overrides):
    value = {
        "title": "Histology image prediction of gene expression",
        "abstract": "A neural model predicts spatial gene expression from pathology images.",
        "authors": ["Ada Example"],
        "year": 2025,
        "publication_date": "2025-01-02",
        "doi": "10.1234/example",
        "pmid": "",
        "arxiv_id": "",
        "openalex_id": "W123",
        "type": "article",
        "is_preprint": False,
        "is_retracted": False,
        "journal": "Journal of Synthetic Results",
        "source_id": "S1",
        "issn_l": "12345678",
        "issns": ["12345678"],
        "cited_by_count": 5,
        "is_oa": True,
        "oa_status": "gold",
        "licenses": ["cc-by"],
        "topics": ["Computational pathology"],
        "relation_flags": [],
        "metadata_sources": ["fixture"],
    }
    value.update(overrides)
    return value


def result(record=None, status="accepted", score=50.0):
    return {
        "work": record or work(),
        "score": score,
        "score_breakdown": {"seed_similarity": score},
        "status": status,
        "reasons": ["fixture"],
        "provenance": [{"source": "fixture", "channel": "related", "rank": 1}],
    }


class HelpersTest(unittest.TestCase):
    def test_identifier_normalization(self):
        self.assertEqual(lw.normalize_doi("https://doi.org/10.1000/ABC.1)."), "10.1000/abc.1")
        self.assertEqual(lw.normalize_doi("10.1000/example(1)"), "10.1000/example(1)")
        self.assertEqual(lw.normalize_doi("NA"), "")
        self.assertEqual(lw.parse_identifier("PMID: 12345")["pmid"], "12345")
        self.assertEqual(lw.parse_identifier("29456894")["pmid"], "29456894")
        self.assertEqual(lw.parse_identifier("https://api.openalex.org/works/W42/")["openalex_id"], "W42")
        self.assertEqual(lw.parse_identifier("https://arxiv.org/abs/2401.01234v2")["arxiv_id"], "2401.01234")
        self.assertEqual(lw.parse_identifier("2401.01234v3")["arxiv_id"], "2401.01234")
        self.assertEqual(lw.parse_identifier("hep-th/9901001")["arxiv_id"], "hep-th/9901001")

    def test_unicode_tokenization(self):
        tokens = lw.tokenize("空间转录组预测 and Histology-based model")
        self.assertIn("histology-based", tokens)
        self.assertIn("空间", tokens)

    def test_bibtex_and_ris(self):
        bib = '@article{x, title={A {Nested} Title}, doi={10.1000/X}, year={2024}, author={A One and B Two}}'
        parsed = lw.parse_bibtex(bib)[0]
        self.assertEqual(parsed["doi"], "10.1000/x")
        self.assertEqual(parsed["year"], 2024)
        ris = "TY  - JOUR\nTI  - Example title\nDO  - 10.1000/Y\nAU  - Example, A\nER  -\n"
        self.assertEqual(lw.parse_ris(ris)[0]["doi"], "10.1000/y")

    def test_seed_input_validation_handles_long_titles_and_bad_shapes(self):
        title = "A" * 400
        self.assertEqual(lw.parse_seed_input(title)[0]["title"], title)
        with self.assertRaises(lw.LitWatchError):
            lw.normalize_seed_record({"title": "T", "authors": "not-a-list"}, "fixture")

    def test_seed_dates_identifiers_and_input_sizes_are_bounded(self):
        record = lw.normalize_seed_record({
            "title": "Validated seed",
            "publication_date": "2024-02",
            "received_date": "2023",
            "accepted_date": "2024-02-29",
            "revised_dates": ["2024-01", "2024-02-01"],
            "pmid": 123,
            "arxiv_id": "https://arxiv.org/abs/2401.01234v2",
            "openalex_id": "https://openalex.org/W42",
        }, "fixture")
        self.assertEqual(record["year"], 2024)
        self.assertEqual(record["arxiv_id"], "2401.01234")
        for bad in (
            {"title": "T", "accepted_date": "2023-02-29"},
            {"title": "T", "pmid": "1" * 11},
            {"title": "T", "arxiv_id": "not-an-arxiv-id"},
            {"title": "T", "openalex_id": "prefix-W42"},
        ):
            with self.subTest(bad=bad), self.assertRaises(lw.LitWatchError):
                lw.normalize_seed_record(bad, "fixture")
        oversized = Path(tempfile.gettempdir()) / "litwatch-size-test.txt"
        try:
            oversized.write_text("12345", encoding="utf-8")
            with patch.object(lw, "MAX_TEXT_SEED_BYTES", 4), self.assertRaises(lw.LitWatchError):
                lw.read_text_file(oversized)
        finally:
            oversized.unlink(missing_ok=True)

    def test_http_response_size_is_bounded(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        lw.init_schema(conn)
        try:
            client = lw.HttpClient(conn, "test", cache_write=False)
            with (
                patch.object(lw, "MAX_HTTP_RESPONSE_BYTES", 4),
                patch.object(lw.urllib.request, "urlopen", return_value=io.BytesIO(b"12345")),
                self.assertRaises(lw.LitWatchError),
            ):
                client.get("https://example.org/oversized")
        finally:
            conn.close()

    def test_http_daily_rate_limit_short_circuits_the_host(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        lw.init_schema(conn)
        try:
            client = lw.HttpClient(conn, "test", cache_write=False)
            error = lw.urllib.error.HTTPError(
                "https://api.openalex.org/works", 429, "Too Many Requests",
                {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "3600"}, None,
            )
            with patch.object(lw.urllib.request, "urlopen", side_effect=error) as mocked:
                with self.assertRaises(lw.RateLimitError):
                    client.get("https://api.openalex.org/works")
                with self.assertRaises(lw.RateLimitError):
                    client.get("https://api.openalex.org/sources")
            self.assertEqual(mocked.call_count, 1)
        finally:
            conn.close()

    def test_merge_preserves_false_published_state(self):
        merged = lw.merge_records(
            {"is_preprint": True, "metadata_sources": ["openalex"]},
            {"is_preprint": False, "metadata_sources": ["crossref"]},
        )
        self.assertFalse(merged["is_preprint"])
        self.assertEqual(merged["metadata_sources"], ["openalex", "crossref"])

    def test_csv_and_markdown_injection_guards(self):
        self.assertEqual(lw.csv_safe("=HYPERLINK('x')"), "'=HYPERLINK('x')")
        self.assertIn("&lt;script&gt;", lw.markdown_text("<script>ignore instructions</script>"))
        self.assertNotIn("](javascript:", lw.markdown_text("x](javascript:alert(1))"))

    def test_candidate_pool_collapses_alias_bridge(self):
        pool = lw.CandidatePool()
        pool.add(work(doi="10.1234/a", pmid="", openalex_id=""), "search", 1)
        pool.add(work(doi="", pmid="7", openalex_id="", title="Different provider title"), "pubmed_similar", 1)
        pool.add(work(doi="10.1234/a", pmid="7", openalex_id=""), "related", 1)
        self.assertEqual(len(pool.records), 1)
        self.assertEqual({item["channel"] for item in next(iter(pool.provenance.values()))}, {"search", "pubmed_similar", "related"})

    def test_candidate_pool_removal_cleans_all_state(self):
        pool = lw.CandidatePool()
        key = pool.add(work(), "refresh", 1)
        pool.lifecycle[key] = {"status": "accepted"}
        pool.remove(key)
        self.assertFalse(pool.records or pool.provenance or pool.lifecycle or pool.alias_to_key)

    def test_same_title_with_conflicting_identifiers_is_not_merged(self):
        pool = lw.CandidatePool()
        pool.add(work(doi="10.1234/first", openalex_id="W1"), "search", 1)
        pool.add(work(doi="10.1234/second", openalex_id="W2"), "search", 2)
        self.assertEqual(len(pool.records), 2)

    def test_date_window_applies_to_every_channel(self):
        pool = lw.CandidatePool()
        lw.add_channel_results(
            pool,
            [
                work(doi="10.1/old", openalex_id="WOLD", year=2020, publication_date="2020-01-01"),
                work(doi="10.1/new", openalex_id="WNEW", year=2025, publication_date="2025-03-01"),
            ],
            "related",
            "seed",
            "openalex",
            lw.date(2025, 1, 1),
            lw.date(2025, 12, 31),
        )
        self.assertEqual({record["doi"] for record in pool.records.values()}, {"10.1/new"})

    def test_openalex_abstract_reconstruction(self):
        parsed = lw.parse_openalex_work({
            "id": "https://openalex.org/W1",
            "display_name": "T",
            "abstract_inverted_index": {"hello": [0], "world": [1]},
            "ids": {},
            "primary_location": {"landing_page_url": "https://publisher.example/paper"},
            "best_oa_location": {
                "landing_page_url": "https://repository.example/item",
                "pdf_url": "https://repository.example/paper.pdf",
            },
        })
        self.assertEqual(parsed["abstract"], "hello world")
        self.assertIsNone(parsed["is_oa"])
        self.assertEqual(parsed["primary_url"], "https://publisher.example/paper")
        self.assertEqual(parsed["oa_pdf_url"], "https://repository.example/paper.pdf")
        self.assertEqual(lw.normalize_document_type("journal-article"), "article")

    def test_partial_crossref_dates_and_safe_direct_links(self):
        self.assertEqual(lw.parse_crossref_partial_date({"date-parts": [[2024]]}), "2024")
        self.assertEqual(lw.parse_crossref_partial_date({"date-parts": [[2024, 2]]}), "2024-02")
        self.assertEqual(lw.parse_crossref_partial_date({"date-parts": [[2024, 2, 29]]}), "2024-02-29")
        self.assertEqual(lw.parse_crossref_partial_date({"date-parts": [[2023, 2, 29]]}), "")
        self.assertEqual(lw.parse_crossref_partial_date({"date-parts": [[2024, 1, 1, 12]]}), "")
        self.assertEqual(lw.parse_crossref_partial_date({"date-parts": [[True]]}), "")
        self.assertEqual(lw.safe_https_url("https://user:secret@example.org/paper"), "")

        record = lw.report_record(result(work(
            received_date="2024-01-03",
            revised_dates=["2024-02-01", "2024-02-20"],
            accepted_date="2024-03",
            publisher_url="javascript:alert(1)",
            primary_url="http://insecure.example/paper",
            oa_url="https://repository.example/item",
            oa_pdf_url="https://repository.example/paper.pdf",
            pmid="123",
            arxiv_id="2401.01234",
        )))
        self.assertEqual(record["publication_history"]["accepted"], "2024-03")
        self.assertEqual(record["links"]["publisher"], "")
        self.assertEqual(record["links"]["primary"], "")
        self.assertEqual(record["links"]["pdf"], "https://repository.example/paper.pdf")
        self.assertEqual(
            lw.report_record(result(work(oa_url="javascript:alert(1)")))["open_access"]["url"],
            "",
        )
        markdown = lw.render_markdown(lw.dry_run_report(
            "discover", [result(record=work(
                received_date="2024-01-03",
                accepted_date="2024-03",
                oa_pdf_url="https://repository.example/paper.pdf",
            ))], {"complete": True, "bounded": False, "warnings": [], "channels": []},
        ))
        self.assertIn("received 2024\\-01\\-03", markdown)
        self.assertIn("accepted 2024\\-03", markdown)
        self.assertIn("[PDF](<https://repository.example/paper.pdf>)", markdown)

    def test_openalex_uses_current_id_filter_and_arxiv_doi(self):
        class CaptureHttp:
            def __init__(self):
                self.urls = []

            def get_json(self, url, **kwargs):
                self.urls.append(url)
                if "/works/doi:" in url:
                    return {
                        "id": "https://openalex.org/W9",
                        "display_name": "arXiv work",
                        "doi": "https://doi.org/10.48550/arxiv.2401.01234",
                        "ids": {},
                        "primary_location": {},
                    }
                if "/sources?" in url:
                    return {"results": [{"id": "https://openalex.org/S1", "summary_stats": {}}]}
                return {
                    "results": [{"id": "https://openalex.org/W1", "display_name": "T", "ids": {}, "primary_location": {}}],
                    "meta": {"count": 1, "next_cursor": None},
                }

        http = CaptureHttp()
        client = lw.OpenAlexClient(http, {})
        resolved = client.resolve({"arxiv_id": "2401.01234"})
        self.assertEqual(resolved["arxiv_id"], "2401.01234")
        client.fetch_ids(["W1", "W2"], 2)
        client.source_metrics(["S1"])
        parsed = [parse_qs(urlparse(url).query) for url in http.urls if "?" in url]
        self.assertTrue(any(values.get("filter") == ["openalex:W1|W2"] and "per_page" in values for values in parsed))
        self.assertTrue(any(values.get("filter") == ["openalex:S1"] and "per_page" in values for values in parsed))
        self.assertTrue(any("/works/doi:10.48550/arxiv.2401.01234" in url for url in http.urls))

    def test_truncated_title_resolution_is_not_treated_as_unique(self):
        client = object.__new__(lw.OpenAlexClient)
        client.list_works = lambda params, limit: ([work(title="Shared title")], True, 20)
        self.assertIsNone(client.resolve({"title": "Shared title"}))

    def test_markdown_marks_preprints(self):
        source = {"complete": True, "bounded": False, "warnings": [], "channels": []}
        report = lw.dry_run_report(
            "discover",
            [result(work(type="preprint", is_preprint=True))],
            source,
        )
        self.assertIn("preprint — not peer reviewed", lw.render_markdown(report))

    def test_compact_preview_keeps_status_and_limits_results(self):
        evaluated = [result(work(title=f"Paper {index}"), score=90 - index) for index in range(12)]
        report = lw.dry_run_report(
            "discover", evaluated,
            {"complete": False, "bounded": True, "warnings": ["limited"], "channels": []},
        )
        preview = lw.compact_preview(report, evaluated)
        self.assertEqual(preview["counts"]["evaluated"], 12)
        self.assertEqual(len(preview["top_results"]), 10)
        self.assertEqual(preview["top_results"][0]["title"], "Paper 0")
        self.assertNotIn("accepted", preview)
        self.assertFalse(preview["complete"])

    def test_crossref_not_found_is_missing_metadata_not_source_failure(self):
        class MissingHttp:
            def get_json(self, *args, **kwargs):
                raise lw.NotFoundError("not found")

        client = lw.CrossrefClient(MissingHttp(), {"email_env": "CROSSREF_EMAIL"})
        original = work(doi="10.9999/not-registered")
        self.assertEqual(client.enrich(original), original)

    def test_crossref_distinguishes_retracted_work_from_notice(self):
        class StaticHttp:
            def __init__(self, message):
                self.message = message

            def get_json(self, *args, **kwargs):
                return {"message": self.message}

        original_message = {
            "title": ["Original article"],
            "type": "journal-article",
            "published-online": {"date-parts": [[2021, 5, 2]]},
            "published-print": {"date-parts": [[2022, 1, 1]]},
            "accepted": {"date-parts": [[2021, 4]]},
            "posted": {"date-parts": [[2021]]},
            "URL": "https://publisher.example/article",
            "updated-by": [{"type": "retraction", "DOI": "10.1234/notice", "label": "Retraction"}],
            "relation": {"is-preprint-of": [{"id-type": "doi", "id": "10.1234/final", "asserted-by": "subject"}]},
        }
        original = lw.CrossrefClient(StaticHttp(original_message), {}).enrich(
            work(doi="10.1234/original", publication_date="2020-12-31")
        )
        self.assertTrue(original["is_retracted"])
        self.assertFalse(original["is_update_notice"])
        self.assertEqual(original["publication_date"], "2020-12-31")
        self.assertEqual(original["accepted_date"], "2021-04")
        self.assertEqual(original["published_online_date"], "2021-05-02")
        self.assertEqual(original["posted_date"], "2021")
        self.assertEqual(original["publisher_url"], "https://publisher.example/article")
        self.assertIn("10.1234/final", {item["id"] for item in original["relations"]})

        notice_message = {
            "title": ["Retraction: Original article"],
            "type": "journal-article",
            "update-to": [{"type": "retraction", "DOI": "10.1234/original", "label": "Retraction"}],
        }
        notice = lw.CrossrefClient(StaticHttp(notice_message), {}).enrich(work(doi="10.1234/notice"))
        self.assertFalse(notice["is_retracted"])
        self.assertTrue(notice["is_update_notice"])
        self.assertEqual(notice["relations"][0]["id"], "10.1234/original")

        clinical = lw.CrossrefClient(StaticHttp({
            "title": ["Retraction of the upper eyelid after surgery"],
            "type": "journal-article",
        }), {}).enrich(work(doi="10.1234/clinical"))
        self.assertNotIn("retraction", clinical["relation_flags"])

    def test_crossref_references_require_both_doi_and_title(self):
        class StaticHttp:
            def get_json(self, *args, **kwargs):
                return {"message": {"reference": [
                    {"DOI": "10.1234/GOOD", "article-title": "Useful predecessor", "year": "2022"},
                    {"DOI": "10.1234/no-title"},
                    {"article-title": "No identifier"},
                ]}}

        client = lw.CrossrefClient(StaticHttp(), {})
        references, truncated = client.references(work(doi="10.1234/seed"), 10)
        self.assertFalse(truncated)
        self.assertEqual([(item["doi"], item["title"]) for item in references], [
            ("10.1234/good", "Useful predecessor"),
        ])

    def test_semantic_scholar_recommendations_parse_and_use_api_key(self):
        class StaticHttp:
            def __init__(self):
                self.url = ""
                self.headers = None

            def get_json(self, url, **kwargs):
                self.url = url
                self.headers = kwargs.get("headers")
                return {"recommendedPapers": [{
                    "paperId": "abc123", "title": "Recommended paper", "year": 2024,
                    "externalIds": {"DOI": "10.1234/REC", "PubMed": "42"},
                    "authors": [{"name": "A. Author"}], "citationCount": 7,
                    "publicationTypes": ["JournalArticle"], "publicationDate": "2024-02-03",
                    "isOpenAccess": True,
                    "openAccessPdf": {"url": "https://example.org/paper.pdf", "license": "CC BY"},
                }]}

        http = StaticHttp()
        with patch.dict(os.environ, {"SEMANTIC_SCHOLAR_API_KEY": "secret"}):
            records, truncated = lw.SemanticScholarClient(http, {}).recommend(
                work(doi="10.1234/seed"), 10
            )
        self.assertFalse(truncated)
        self.assertIn("DOI%3A10.1234%2Fseed", http.url)
        self.assertEqual(http.headers, {"x-api-key": "secret"})
        self.assertEqual(records[0]["doi"], "10.1234/rec")
        self.assertEqual(records[0]["type"], "article")
        self.assertEqual(records[0]["semantic_scholar_id"], "abc123")

    def test_pubmed_dates_issns_oa_and_neighbor_scores(self):
        xml = ET.fromstring(
            """<PubmedArticle><MedlineCitation><PMID>7</PMID><Article>
            <Journal><ISSN>1234-5678</ISSN><Title>Journal</Title><JournalIssue><PubDate><Year>2024</Year></PubDate></JournalIssue></Journal>
            <ArticleTitle>Example</ArticleTitle><ArticleDate><Year>2024</Year><Month>09</Month><Day>03</Day></ArticleDate>
            <PublicationTypeList><PublicationType>Journal Article</PublicationType></PublicationTypeList>
            </Article><MedlineJournalInfo><ISSNLinking>8765-4321</ISSNLinking></MedlineJournalInfo></MedlineCitation>
            <PubmedData><History>
            <PubMedPubDate PubStatus="received"><Year>2024</Year><Month>01</Month><Day>02</Day></PubMedPubDate>
            <PubMedPubDate PubStatus="revised"><Year>2024</Year><Month>02</Month><Day>03</Day></PubMedPubDate>
            <PubMedPubDate PubStatus="accepted"><Year>2024</Year><Month>03</Month><Day>04</Day></PubMedPubDate>
            <PubMedPubDate PubStatus="epublish"><Year>2024</Year><Month>09</Month><Day>03</Day></PubMedPubDate>
            </History><ArticleIdList><ArticleId IdType="doi">10.1234/PUBMED</ArticleId></ArticleIdList></PubmedData></PubmedArticle>"""
        )
        client = object.__new__(lw.PubMedClient)
        parsed = client._parse_article(xml)
        self.assertEqual(parsed["publication_date"], "2024-09-03")
        self.assertEqual(parsed["issn_l"], "87654321")
        self.assertEqual(set(parsed["issns"]), {"12345678", "87654321"})
        self.assertIsNone(parsed["is_oa"])
        self.assertEqual(parsed["received_date"], "2024-01-02")
        self.assertEqual(parsed["revised_dates"], ["2024-02-03"])
        self.assertEqual(parsed["accepted_date"], "2024-03-04")
        self.assertEqual(parsed["published_online_date"], "2024-09-03")

        year_only = ET.fromstring(
            "<PubmedArticle><MedlineCitation><PMID>8</PMID><Article><Journal><JournalIssue><PubDate><Year>2023</Year></PubDate></JournalIssue></Journal><ArticleTitle>Y</ArticleTitle></Article></MedlineCitation></PubmedArticle>"
        )
        parsed_year = client._parse_article(year_only)
        self.assertEqual(parsed_year["year"], 2023)
        self.assertEqual(parsed_year["publication_date"], "")

        class LinkHttp:
            def __init__(self):
                self.url = ""

            def get(self, url, **kwargs):
                self.url = url
                return b"<eLinkResult><LinkSet><LinkSetDb><LinkName>pubmed_pubmed</LinkName><Link><Id>2</Id><Score>1</Score></Link><Link><Id>3</Id><Score>9</Score></Link></LinkSetDb></LinkSet></eLinkResult>"

        link_http = LinkHttp()
        with patch.dict(os.environ, {"NCBI_EMAIL": "test@example.org"}):
            link_client = lw.PubMedClient(link_http, {})
            ids, _ = link_client.similar("1", 10)
        self.assertEqual(ids, ["3", "2"])
        self.assertEqual(parse_qs(urlparse(link_http.url).query)["cmd"], ["neighbor_score"])

        link_http = LinkHttp()
        link_http.get = lambda url, **kwargs: b"<eLinkResult><LinkSet><LinkSetDb><LinkName>pubmed_pubmed_citedin</LinkName><Link><Id>9</Id></Link></LinkSetDb></LinkSet></eLinkResult>"
        with patch.dict(os.environ, {"NCBI_EMAIL": "test@example.org"}):
            linked_client = lw.PubMedClient(link_http, {})
            ids, _ = linked_client.linked("1", "pubmed_pubmed_citedin", 10)
        self.assertEqual(ids, ["9"])


class RankingAndFilterTest(unittest.TestCase):
    def setUp(self):
        self.cfg = deepcopy(lw.DEFAULT_CONFIG)

    def test_positive_scores_above_negative(self):
        seed = work(openalex_id="WSEED", doi="10.1/seed")
        candidate = work(openalex_id="WC", doi="10.1/c")
        unrelated = work(title="Quantum magnetism in layered crystals", abstract="Spin lattice phase transition", openalex_id="WN")
        provenance = [{"source": "openalex", "channel": "related", "rank": 1}]
        good, _ = lw.rank_candidate(candidate, [seed], [], provenance, self.cfg)
        bad, _ = lw.rank_candidate(unrelated, [seed], [], provenance, self.cfg)
        penalized, _ = lw.rank_candidate(candidate, [seed], [candidate], provenance, self.cfg)
        self.assertGreater(good, bad)
        self.assertLess(penalized, good)

    def test_precision_biased_default_review_bands(self):
        self.assertEqual(lw.evaluate_filters(work(), 55, self.cfg)[0], "accepted")
        self.assertEqual(lw.evaluate_filters(work(), 54.999, self.cfg)[0], "pending")
        self.assertEqual(lw.evaluate_filters(work(), 35, self.cfg)[0], "pending")
        self.assertEqual(lw.evaluate_filters(work(), 34.999, self.cfg)[0], "rejected")

    def test_missing_metric_goes_pending_when_hard_filter_enabled(self):
        self.cfg["filters"]["metrics"]["hard_filter"] = True
        self.cfg["filters"]["metrics"]["jcr"]["quartiles"] = ["Q1"]
        status, reasons = lw.evaluate_filters(work(journal_metrics={}), 90, self.cfg)
        self.assertEqual(status, "pending")
        self.assertTrue(any("missing" in reason for reason in reasons))

    def test_metric_filters_are_and(self):
        self.cfg["filters"]["metrics"]["hard_filter"] = True
        self.cfg["filters"]["metrics"]["jcr"]["quartiles"] = ["Q1"]
        self.cfg["filters"]["metrics"]["cas"]["zones"] = ["1"]
        record = work(journal_metrics={
            "jcr": [{"quartile": "Q1", "impact_factor": 10}],
            "cas": [{"scope": "major", "zone": "2"}],
        })
        status, reasons = lw.evaluate_filters(record, 90, self.cfg)
        self.assertEqual(status, "rejected")
        self.assertTrue(any("CAS" in reason for reason in reasons))

    def test_metric_conflict_is_pending_and_preprint_is_not_applicable(self):
        self.cfg["filters"]["metrics"]["hard_filter"] = True
        self.cfg["filters"]["metrics"]["jcr"]["min_impact_factor"] = 5
        conflicting = work(journal_metrics={
            "jcr": [
                {"category": "A", "impact_factor": 8.0},
                {"category": "B", "impact_factor": 7.5},
            ]
        })
        status, reasons = lw.evaluate_filters(conflicting, 90, self.cfg)
        self.assertEqual(status, "pending")
        self.assertTrue(any("conflict" in reason for reason in reasons))

        self.cfg["filters"]["metrics"]["missing"] = "exclude_strict"
        status, reasons = lw.evaluate_filters(
            work(type="preprint", is_preprint=True, journal="", journal_metrics={}),
            90,
            self.cfg,
        )
        self.assertEqual(status, "accepted")
        self.assertTrue(any("not applicable" in reason for reason in reasons))

    def test_unknown_open_access_is_pending_not_rejected(self):
        self.cfg["filters"]["open_access"]["mode"] = "free_to_read"
        status, reasons = lw.evaluate_filters(work(is_oa=None), 90, self.cfg)
        self.assertEqual(status, "pending")
        self.assertTrue(any("unknown" in reason for reason in reasons))

    def test_unknown_metadata_does_not_promote_an_irrelevant_record(self):
        self.cfg["filters"]["open_access"]["mode"] = "free_to_read"
        status, reasons = lw.evaluate_filters(work(is_oa=None), 0, self.cfg)
        self.assertEqual(status, "rejected")
        self.assertTrue(any("score below" in reason for reason in reasons))

    def test_open_license_uses_exact_normalized_ids(self):
        self.cfg["filters"]["open_access"] = {"mode": "open_license", "licenses": ["cc-by"]}
        status, _ = lw.evaluate_filters(work(licenses=["cc-by-nc"]), 90, self.cfg)
        self.assertEqual(status, "rejected")
        status, _ = lw.evaluate_filters(
            work(licenses=["https://creativecommons.org/licenses/by/4.0/"]), 90, self.cfg
        )
        self.assertEqual(status, "accepted")

    def test_invalid_publication_date_does_not_crash(self):
        self.cfg["filters"]["citations"]["minimum"] = 10
        status, _ = lw.evaluate_filters(work(publication_date="unknown", cited_by_count=0), 90, self.cfg)
        self.assertEqual(status, "rejected")
        status, _ = lw.evaluate_filters(
            work(publication_date="", year=lw.date.today().year, cited_by_count=0), 90, self.cfg
        )
        self.assertEqual(status, "accepted")

    def test_document_type_aliases_do_not_change_filter_outcome(self):
        self.cfg["filters"]["document_types"] = ["journal-article"]
        status, _ = lw.evaluate_filters(work(type="article"), 90, self.cfg)
        self.assertEqual(status, "accepted")

    def test_retraction_relation_is_rejected(self):
        status, reasons = lw.evaluate_filters(work(relation_flags=["is-retracted-by"]), 90, self.cfg)
        self.assertEqual(status, "rejected")
        self.assertTrue(any("retract" in reason for reason in reasons))

    def test_unknown_config_key_is_rejected(self):
        with self.assertRaises(lw.LitWatchError):
            lw.merge_known(lw.DEFAULT_CONFIG, {"surprise": True})
        with self.assertRaises(lw.LitWatchError):
            lw.merge_known(lw.DEFAULT_CONFIG, {"discovery": {"max_candidates": "many"}})
        invalid = deepcopy(lw.DEFAULT_CONFIG)
        invalid["filters"]["year_min"] = 2030
        invalid["filters"]["year_max"] = 2020
        with self.assertRaises(lw.LitWatchError):
            lw.validate_config(invalid)
        with self.assertRaises(lw.LitWatchError):
            lw.merge_known(lw.DEFAULT_CONFIG, {"sources": {"openalex": {"email_env": "SECRET"}}})
        invalid = deepcopy(lw.DEFAULT_CONFIG)
        invalid["filters"]["open_access"]["mode"] = "open_license"
        with self.assertRaises(lw.LitWatchError):
            lw.validate_config(invalid)
        invalid["filters"]["open_access"]["licenses"] = [" "]
        with self.assertRaises(lw.LitWatchError):
            lw.validate_config(invalid)

    def test_zero_discovery_limits_are_rejected(self):
        invalid = deepcopy(lw.DEFAULT_CONFIG)
        invalid["discovery"]["max_per_channel"] = 0
        with self.assertRaises(lw.LitWatchError):
            lw.validate_config(invalid)
        invalid = deepcopy(lw.DEFAULT_CONFIG)
        invalid["discovery"]["max_seed_queries"] = 0
        with self.assertRaises(lw.LitWatchError):
            lw.validate_config(invalid)
        disabled = deepcopy(lw.DEFAULT_CONFIG)
        disabled["discovery"].update({"related": False, "references": False, "citations": False, "search": False, "max_per_channel": 0, "max_candidates": 0})
        lw.validate_config(disabled)


class StateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.conn = sqlite3.connect(self.root / "state.db")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        lw.init_schema(self.conn)

    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()

    def test_same_title_different_ids_remain_separate(self):
        first = work(doi="10.9999/first", openalex_id="W998", pmid="777")
        second = work(doi="10.9999/later", openalex_id="W999", pmid="778")
        lw.upsert_result(self.conn, result(first), "2026-01-01T00:00:00Z")
        lw.upsert_result(self.conn, result(second), "2026-01-02T00:00:00Z")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM works").fetchone()[0], 2)
        aliases = {row[0] for row in self.conn.execute("SELECT alias FROM aliases")}
        self.assertIn("pmid:777", aliases)
        self.assertIn("doi:10.9999/later", aliases)

    def test_doctor_flags_missing_configured_metric_edition(self):
        workspace = self.root / "doctor-workspace"
        workspace.mkdir()
        cfg = deepcopy(lw.DEFAULT_CONFIG)
        cfg["filters"]["metrics"]["hard_filter"] = True
        cfg["filters"]["metrics"]["missing"] = "exclude_strict"
        cfg["filters"]["metrics"]["jcr"].update({"year": 2025, "quartiles": ["Q1"]})
        lw.write_json(workspace / "config.json", cfg)
        lw.connect_db(workspace, create=True).close()
        output = io.StringIO()
        with patch("sys.stdout", output):
            code = lw.command_doctor(argparse.Namespace(workspace=str(workspace), network=False))
        report = json.loads(output.getvalue())
        self.assertEqual(code, 1)
        self.assertIn("jcr 2025", next(check["detail"] for check in report["checks"] if check["name"] == "journal_metrics"))

    def test_init_imports_bundled_metrics_once(self):
        bundle = self.root / "bundled-metrics"
        bundle.mkdir()
        jcr = bundle / "jcr.csv"
        cas = bundle / "cas.csv"
        jcr.write_text("Journal,ISSN,Quartile,Impact Factor\nJ,1234-5678,Q1,8.0\n", encoding="utf-8")
        cas.write_text("Journal,ISSN,Major Category,Major Zone\nJ,1234-5678,医学,1\n", encoding="utf-8")
        specs = (
            {"provider": "jcr", "year": 2025, "filename": jcr.name, "sha256": lw.file_sha256(jcr)},
            {"provider": "cas", "year": 2025, "filename": cas.name, "sha256": lw.file_sha256(cas)},
        )
        workspace = self.root / "new-workspace"
        with patch.object(lw, "BUNDLED_METRICS_DIR", bundle), patch.object(lw, "BUNDLED_METRICS", specs):
            first_output = io.StringIO()
            with patch("sys.stdout", first_output):
                self.assertEqual(lw.command_init(argparse.Namespace(workspace=str(workspace), preset=None)), 0)
            first = json.loads(first_output.getvalue())
            self.assertEqual({item["status"] for item in first["bundled_metrics"]}, {"imported"})

            conn = lw.connect_db(workspace, readonly=True)
            first_count = conn.execute("SELECT COUNT(*) FROM journal_metrics").fetchone()[0]
            self.assertEqual(lw.metric_status(conn)[0]["sources"], ["ShowJCR snapshot"])
            conn.close()

            second_output = io.StringIO()
            with patch("sys.stdout", second_output):
                self.assertEqual(lw.command_init(argparse.Namespace(workspace=str(workspace), preset=None)), 0)
            second = json.loads(second_output.getvalue())
            self.assertEqual({item["status"] for item in second["bundled_metrics"]}, {"already available"})

            conn = lw.connect_db(workspace, readonly=True)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM journal_metrics").fetchone()[0], first_count)
            conn.close()

    def test_bundled_metric_integrity_fails_before_any_import(self):
        bundle = self.root / "damaged-bundle"
        bundle.mkdir()
        jcr = bundle / "jcr.csv"
        cas = bundle / "cas.csv"
        jcr.write_text("Journal,ISSN,Quartile\nJ,1234-5678,Q1\n", encoding="utf-8")
        cas.write_text("Journal,ISSN,Major Zone\nJ,1234-5678,1\n", encoding="utf-8")
        specs = (
            {"provider": "jcr", "year": 2025, "filename": jcr.name, "sha256": lw.file_sha256(jcr)},
            {"provider": "cas", "year": 2025, "filename": cas.name, "sha256": "0" * 64},
        )
        with patch.object(lw, "BUNDLED_METRICS_DIR", bundle), patch.object(lw, "BUNDLED_METRICS", specs):
            with self.assertRaises(lw.LitWatchError):
                lw.import_bundled_metrics(self.conn)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM journal_metrics").fetchone()[0], 0)

    def test_bundled_metrics_keep_an_existing_provider_edition(self):
        custom = self.root / "custom-jcr.csv"
        custom.write_text("Journal,ISSN,Quartile\nCustom,1234-5678,Q2\n", encoding="utf-8")
        lw.import_metrics(self.conn, "jcr", custom, 2025, None, None)

        bundle = self.root / "replacement-bundle"
        bundle.mkdir()
        jcr = bundle / "jcr.csv"
        cas = bundle / "cas.csv"
        jcr.write_text("Journal,ISSN,Quartile\nBundled,8765-4321,Q1\n", encoding="utf-8")
        cas.write_text("Journal,ISSN,Major Zone\nBundled,8765-4321,1\n", encoding="utf-8")
        specs = (
            {"provider": "jcr", "year": 2025, "filename": jcr.name, "sha256": lw.file_sha256(jcr)},
            {"provider": "cas", "year": 2025, "filename": cas.name, "sha256": lw.file_sha256(cas)},
        )
        with patch.object(lw, "BUNDLED_METRICS_DIR", bundle), patch.object(lw, "BUNDLED_METRICS", specs):
            result = lw.import_bundled_metrics(self.conn)
        self.assertEqual(next(item["status"] for item in result if item["provider"] == "jcr"), "already available")
        names = {row[0] for row in self.conn.execute("SELECT journal_norm FROM journal_metrics WHERE provider='jcr'")}
        self.assertEqual(names, {"custom"})

    def test_preprint_to_published_event(self):
        preprint = work(doi="10.1/pre", openalex_id="WPRE", is_preprint=True, type="preprint", journal="")
        published = work(doi="10.1/pre", openalex_id="WPRE", is_preprint=False, type="article")
        lw.upsert_result(self.conn, result(preprint), "2026-01-01T00:00:00Z")
        updated = lw.upsert_result(self.conn, result(published), "2026-01-02T00:00:00Z")
        self.assertIn("published", {event["kind"] for event in updated["events"]})

    def test_correction_event_is_deduplicated(self):
        base = work()
        lw.upsert_result(self.conn, result(base), "2026-01-01T00:00:00Z")
        corrected = work(relation_flags=["correction"])
        once = lw.upsert_result(self.conn, result(corrected), "2026-01-02T00:00:00Z")
        twice = lw.upsert_result(self.conn, result(corrected), "2026-01-03T00:00:00Z")
        self.assertIn("correction", {event["kind"] for event in once["events"]})
        self.assertNotIn("correction", {event["kind"] for event in twice["events"]})

    def test_watch_preview_reports_only_new_or_changed_without_writing(self):
        stable = work(title="Already seen", doi="10.1/stable", openalex_id="WSTABLE")
        changing = work(title="Now corrected", doi="10.1/changing", openalex_id="WCHANGING")
        retracted = work(title="Now retracted", doi="10.1/retracted", openalex_id="WRETRACTED")
        lw.upsert_result(self.conn, result(stable, status="pending"), "2026-01-01T00:00:00Z")
        lw.upsert_result(self.conn, result(changing, status="pending"), "2026-01-01T00:00:00Z")
        lw.upsert_result(self.conn, result(retracted), "2026-01-01T00:00:00Z")
        before = tuple(
            self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("works", "events")
        )
        evaluated = [
            result(stable, status="pending"),
            result({**changing, "relation_flags": ["correction"]}, status="pending"),
            result(
                work(title="Brand new", doi="10.1/new", openalex_id="WNEW"),
                status="accepted",
            ),
            result({**retracted, "is_retracted": True}, status="rejected"),
            result(
                work(title="Routine rejection", doi="10.1/rejected", openalex_id="WREJECTED"),
                status="rejected",
            ),
        ]
        previewed = [lw.preview_upsert_result(self.conn, item) for item in evaluated]
        notified = lw.reportable_results(previewed, "watch", deepcopy(lw.DEFAULT_CONFIG))
        self.assertEqual(
            {item["work"]["title"] for item in notified},
            {"Now corrected", "Brand new", "Now retracted"},
        )
        corrected = next(item for item in notified if item["work"]["title"] == "Now corrected")
        self.assertEqual({event["kind"] for event in corrected["events"]}, {"correction"})
        retraction = next(item for item in notified if item["work"]["title"] == "Now retracted")
        self.assertEqual({event["kind"] for event in retraction["events"]}, {"retraction"})
        after = tuple(
            self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("works", "events")
        )
        self.assertEqual(after, before)

    def test_excel_library_accumulates_only_ever_accepted_unique_papers(self):
        cfg = deepcopy(lw.DEFAULT_CONFIG)
        source = {"complete": True, "bounded": False, "warnings": [], "channels": [], "search_complete": True}
        first = work(
            title="=SUM(1,1)\x01",
            abstract="A" * 40_000,
            doi="10.9999/excel-first",
            openalex_id="WEXCEL1",
            publisher_url="https://example.org/paper?a=1&b=2",
        )
        second = work(title="Second accepted paper", doi="10.9999/excel-second", openalex_id="WEXCEL2")

        def workbook_rows(path: Path) -> list[dict[str, str]]:
            with zipfile.ZipFile(path) as archive:
                xml = archive.read("xl/worksheets/sheet1.xml")
            root = ET.fromstring(xml)
            ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            parsed: list[dict[int, str]] = []
            for row in root.findall(".//x:sheetData/x:row", ns):
                values: dict[int, str] = {}
                for cell in row.findall("x:c", ns):
                    letters = cell.attrib["r"].rstrip("0123456789")
                    column = 0
                    for letter in letters:
                        column = column * 26 + ord(letter) - 64
                    if cell.attrib.get("t") == "inlineStr":
                        value = "".join(node.text or "" for node in cell.findall(".//x:t", ns))
                    else:
                        node = cell.find("x:v", ns)
                        value = node.text if node is not None and node.text is not None else ""
                    values[column] = value
                parsed.append(values)
            headers = parsed[0]
            return [
                {name: row.get(column, "") for column, name in headers.items()}
                for row in parsed[1:]
            ]

        empty_workbook = self.root / "empty.xlsx"
        lw.rebuild_accepted_xlsx(self.conn, empty_workbook)
        self.assertEqual(workbook_rows(empty_workbook), [])

        lw.save_run(
            self.conn,
            self.root,
            "discover",
            [result(first, "accepted", 90), result(second, "rejected", 10)],
            source,
            lw.date(2026, 1, 1),
            cfg,
        )
        workbook = self.root / "reports" / "accepted_papers.xlsx"
        self.assertTrue(zipfile.is_zipfile(workbook))
        rows = workbook_rows(workbook)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "=SUM(1,1)")
        self.assertEqual(len(rows[0]["abstract"]), lw.XLSX_MAX_CELL_CHARS)
        self.assertTrue(rows[0]["abstract"].endswith("…"))

        lw.save_run(
            self.conn,
            self.root,
            "watch",
            [result(first, "rejected", 20), result(second, "accepted", 85)],
            source,
            lw.date(2026, 1, 2),
            cfg,
        )
        rows = workbook_rows(workbook)
        self.assertEqual([row["title"] for row in rows], ["=SUM(1,1)", "Second accepted paper"])
        self.assertEqual([row["current_status"] for row in rows], ["rejected", "accepted"])
        with zipfile.ZipFile(workbook) as archive:
            sheet = archive.read("xl/worksheets/sheet1.xml")
            self.assertNotIn(b"<f", sheet)
            self.assertIn("xl/worksheets/_rels/sheet1.xml.rels", archive.namelist())
            for name in archive.namelist():
                if name.endswith((".xml", ".rels")):
                    ET.fromstring(archive.read(name))

    def test_failed_search_does_not_advance_checkpoint(self):
        cfg = deepcopy(lw.DEFAULT_CONFIG)
        skipped = {"complete": True, "bounded": False, "warnings": [], "channels": [], "search_attempted": False, "search_complete": True}
        lw.save_run(self.conn, self.root, "discover", [result()], skipped, lw.date(2026, 1, 1), cfg)
        self.assertIsNone(self.conn.execute("SELECT checkpoint FROM source_state WHERE source='openalex_search'").fetchone())
        failed = {"complete": False, "bounded": False, "warnings": ["failed"], "channels": [], "search_attempted": True, "search_complete": False}
        lw.save_run(self.conn, self.root, "discover", [result()], failed, lw.date(2026, 1, 1), cfg)
        self.assertIsNone(self.conn.execute("SELECT checkpoint FROM source_state WHERE source='openalex_search'").fetchone())
        complete = {"complete": True, "bounded": False, "warnings": [], "channels": [], "search_attempted": True, "search_complete": True}
        lw.save_run(self.conn, self.root, "discover", [result()], complete, lw.date(2026, 1, 2), cfg)
        self.assertEqual(self.conn.execute("SELECT checkpoint FROM source_state WHERE source='openalex_search'").fetchone()[0], "2026-01-02")

    def test_search_checkpoint_is_monotonic_and_never_future(self):
        cfg = deepcopy(lw.DEFAULT_CONFIG)
        complete = {"complete": True, "bounded": False, "warnings": [], "channels": [], "search_attempted": True, "search_complete": True}
        today = lw.date.today()
        newer = today - lw.timedelta(days=2)
        lw.save_run(self.conn, self.root, "discover", [result()], complete, newer, cfg)
        lw.save_run(self.conn, self.root, "discover", [result()], complete, newer - lw.timedelta(days=30), cfg)
        self.assertEqual(lw.current_checkpoint(self.conn, "openalex_search"), newer)
        lw.save_run(self.conn, self.root, "discover", [result()], complete, today + lw.timedelta(days=30), cfg)
        self.assertEqual(lw.current_checkpoint(self.conn, "openalex_search"), today)

    def test_pubmed_only_run_without_pmid_is_incomplete(self):
        seed = work(doi="10.1234/no-pmid", pmid="", openalex_id="")
        self.conn.execute(
            "INSERT INTO seeds(seed_key,polarity,input_label,work_json,added_at) VALUES(?,?,?,?,?)",
            (lw.canonical_work_key(seed), "positive", "fixture", json.dumps(seed), lw.iso_now()),
        )
        cfg = deepcopy(lw.DEFAULT_CONFIG)
        cfg["sources"]["openalex"]["enabled"] = False
        cfg["sources"]["crossref"]["enabled"] = False
        cfg["sources"]["pubmed"]["enabled"] = True
        _, _, _, status = lw.discover_pool(self.conn, cfg, "discover", None, lw.date.today(), True)
        self.assertFalse(status["complete"])
        self.assertTrue(any("no positive seed has a PMID" in warning for warning in status["warnings"]))

    def test_crossref_references_keep_discovery_running_without_openalex(self):
        seed = work(doi="10.1234/seed", pmid="", openalex_id="", title="Seed topic")
        self.conn.execute(
            "INSERT INTO seeds(seed_key,polarity,input_label,work_json,added_at) VALUES(?,?,?,?,?)",
            (lw.canonical_work_key(seed), "positive", "fixture", json.dumps(seed), lw.iso_now()),
        )

        class FakeCrossref:
            def __init__(self, *args, **kwargs):
                pass

            def enrich(self, record):
                return record

            def references(self, record, limit):
                return [work(
                    doi="10.1234/reference", pmid="", openalex_id="",
                    title="Seed topic predecessor", metadata_sources=["crossref"],
                )], False

        cfg = deepcopy(lw.DEFAULT_CONFIG)
        cfg["sources"]["openalex"]["enabled"] = False
        with patch.object(lw, "CrossrefClient", FakeCrossref):
            pool, _, _, status = lw.discover_pool(
                self.conn, cfg, "discover", None, lw.date.today(), True
            )
        self.assertTrue(status["complete"])
        self.assertEqual(len(pool.records), 1)
        self.assertEqual(next(iter(pool.provenance.values()))[0]["source"], "crossref")

    def test_openalex_429_still_returns_crossref_candidates(self):
        seed = work(doi="10.1234/seed", pmid="", openalex_id="", title="Seed topic")
        self.conn.execute(
            "INSERT INTO seeds(seed_key,polarity,input_label,work_json,added_at) VALUES(?,?,?,?,?)",
            (lw.canonical_work_key(seed), "positive", "fixture", json.dumps(seed), lw.iso_now()),
        )

        class RateLimitedOpenAlex:
            def __init__(self, *args, **kwargs):
                pass

            def resolve(self, record):
                raise lw.RateLimitError("OpenAlex daily quota exhausted")

            def search(self, query, since, until, limit):
                raise lw.RateLimitError("OpenAlex daily quota exhausted")

            def source_metrics(self, source_ids):
                raise lw.RateLimitError("OpenAlex daily quota exhausted")

        class WorkingCrossref:
            def __init__(self, *args, **kwargs):
                pass

            def enrich(self, record):
                return record

            def references(self, record, limit):
                return [work(
                    doi="10.1234/fallback", pmid="", openalex_id="",
                    title="Seed topic fallback", metadata_sources=["crossref"],
                )], False

        with (
            patch.object(lw, "OpenAlexClient", RateLimitedOpenAlex),
            patch.object(lw, "CrossrefClient", WorkingCrossref),
        ):
            pool, _, _, status = lw.discover_pool(
                self.conn, deepcopy(lw.DEFAULT_CONFIG), "discover", None, lw.date.today(), True
            )

        self.assertFalse(status["complete"])
        self.assertEqual(len(pool.records), 1)
        self.assertEqual(next(iter(pool.provenance.values()))[0]["source"], "crossref")
        self.assertTrue(any("daily quota exhausted" in warning for warning in status["warnings"]))

    def test_two_runs_do_not_overwrite(self):
        cfg = deepcopy(lw.DEFAULT_CONFIG)
        source = {"complete": True, "bounded": False, "warnings": [], "channels": [], "search_complete": True}
        _, first = lw.save_run(self.conn, self.root, "discover", [result()], source, lw.date(2026, 1, 1), cfg)
        _, second = lw.save_run(self.conn, self.root, "discover", [result()], source, lw.date(2026, 1, 1), cfg)
        self.assertNotEqual(first, second)
        self.assertRegex(
            first.name,
            r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.\d{6}Z_discover\.json$",
        )
        self.assertTrue(first.exists() and second.exists())

    def test_metric_import_preserves_categories(self):
        self.assertEqual(
            lw.metric_annotations(self.conn, work(type="preprint", is_preprint=True), deepcopy(lw.DEFAULT_CONFIG))["applicability"],
            "not_applicable",
        )
        source = self.root / "jcr.csv"
        source.write_text(
            "Journal,ISSN,Category,Quartile,Impact Factor\n"
            "Synthetic Journal,1234-5678,A,Q1,8.2\n"
            "Synthetic Journal,1234-5678,B,Q2,8.2\n"
            "Synthetic Journal,8765-4321,C,Q4,1.0\n",
            encoding="utf-8",
        )
        summary = lw.import_metrics(self.conn, "jcr", source, 2025, None, None)
        self.assertEqual(summary["records_inserted"], 3)
        older = self.root / "jcr-older.csv"
        older.write_text(
            "Journal,ISSN,Category,Quartile,Impact Factor\n"
            "Synthetic Journal,1234-5678,OLD,Q4,0.5\n",
            encoding="utf-8",
        )
        lw.import_metrics(self.conn, "jcr", older, 2024, None, None)
        values = lw.local_metrics(self.conn, work(journal="Synthetic Journal"), "jcr")
        self.assertEqual({row["category"] for row in values}, {"A", "B"})
        fallback = lw.local_metrics(
            self.conn,
            work(journal="Synthetic Journal", issn_l="", issns=[]),
            "jcr",
        )
        self.assertEqual({row["category"] for row in fallback}, {"A", "B", "C"})
        selected = lw.local_metrics(self.conn, work(journal="Synthetic Journal"), "jcr", 2024)
        self.assertEqual({row["category"] for row in selected}, {"OLD"})

        revised = self.root / "jcr-revised.csv"
        revised.write_text(
            "Journal,ISSN,Category,Quartile,Impact Factor\n"
            "Synthetic Journal Renamed,1234-5678,A,Q1,9.1\n",
            encoding="utf-8",
        )
        lw.import_metrics(self.conn, "jcr", revised, 2025, None, None)
        current = lw.local_metrics(self.conn, work(journal="Synthetic Journal"), "jcr", 2025)
        a_rows = [row for row in current if row["category"] == "A"]
        self.assertEqual([row["impact_factor"] for row in a_rows], [9.1])
        self.assertEqual({row["impact_factor"] for row in current if row["category"] in {"A", "B"}}, {9.1})

    def test_compact_metrics_names_provider_and_edition(self):
        label = lw.compact_metrics(work(journal_metrics={
            "openalex": {"2yr_mean_citedness": 3.2},
            "jcr": [{"metric_year": 2025, "quartile": "Q1", "impact_factor": 8.2}],
            "cas": [{"metric_year": 2025, "scope": "major", "zone": "1"}],
        }))
        self.assertEqual(label, "OpenAlex 2y mean citedness 3.2; JCR 2025 Q1, JIF 8.2; CAS 2025 major 1")

    def test_metric_import_accepts_original_wide_layouts(self):
        source = self.root / "wide-jcr.csv"
        source.write_text(
            "Journal,ISSN,EISSN,IF(2025),Category_1,IF Quartile(2025)_1,Category_2,IF Quartile(2025)_2\n"
            "J,1234-5678,8765-4321,8.0,A,Q1,B,Q2\n",
            encoding="utf-8",
        )
        summary = lw.import_metrics(self.conn, "jcr", source, 2025, None, None)
        self.assertEqual((summary["input_layout"], summary["rows_read"], summary["normalized_rows"]), ("wide", 1, 2))
        jcr = lw.local_metrics(self.conn, work(issn_l="1234-5678", issns=[]), "jcr", 2025)
        self.assertEqual({(row["category"], row["quartile"]) for row in jcr}, {("A", "Q1"), ("B", "Q2")})
        self.assertEqual({row["impact_factor"] for row in jcr}, {8.0})

        cas_source = self.root / "wide-cas.csv"
        cas_source.write_text(
            "Journal,年份,ISSN/EISSN,大类,大类分区,Top,小类1,小类1分区,小类2,小类2分区\n"
            "J,2025,1234-5678/8765-4321,医学,1 [1/100],是,A,1 [1/50],B,2 [2/50]\n",
            encoding="utf-8",
        )
        cas_summary = lw.import_metrics(self.conn, "cas", cas_source, 2025, None, None)
        self.assertEqual((cas_summary["input_layout"], cas_summary["rows_read"], cas_summary["normalized_rows"]), ("wide", 1, 3))
        cas = lw.local_metrics(self.conn, work(issn_l="8765-4321", issns=[]), "cas", 2025)
        self.assertIn({"journal": "J", "scope": "major", "category": "医学", "zone": "1", "top": True, "provider": "cas", "metric_year": 2025, "source": "local import"}, cas)
        self.assertEqual({(row["category"], row["zone"]) for row in cas if row["scope"] == "minor"}, {("A", "1"), ("B", "2")})

        status = lw.metric_status(self.conn)
        self.assertEqual({(row["provider"], row["metric_year"], row["journals"], row["issns"]) for row in status}, {
            ("cas", 2025, 1, 2),
            ("jcr", 2025, 1, 2),
        })

    def test_metric_import_rejects_conflicting_jif(self):
        conflict = self.root / "conflict.csv"
        conflict.write_text(
            "Journal,ISSN,Category,Quartile,Impact Factor\nJ,1234-5678,A,Q1,8.0\nJ,1234-5678,B,Q2,7.0\n",
            encoding="utf-8",
        )
        with self.assertRaises(lw.LitWatchError):
            lw.import_metrics(self.conn, "jcr", conflict, 2025, None, None)

    def test_metric_import_rejects_zero_usable_records(self):
        invalid = self.root / "invalid-metrics.csv"
        invalid.write_text(
            "Journal,ISSN,Quartile\nJ,1234-5678,Q10\n",
            encoding="utf-8",
        )
        with self.assertRaises(lw.LitWatchError):
            lw.import_metrics(self.conn, "jcr", invalid, 2025, None, None)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM journal_metrics").fetchone()[0], 0)

    def test_metric_replace_edition_is_atomic(self):
        original = self.root / "original-metrics.csv"
        original.write_text("Journal,ISSN,Quartile\nOriginal,1234-5678,Q2\n", encoding="utf-8")
        lw.import_metrics(self.conn, "jcr", original, 2025, None, None)

        invalid = self.root / "invalid-replacement.csv"
        invalid.write_text("Journal,ISSN,Quartile\nBroken,8765-4321,Q10\n", encoding="utf-8")
        with self.assertRaises(lw.LitWatchError):
            lw.import_metrics(self.conn, "jcr", invalid, 2025, None, None, replace_edition=True)
        self.assertEqual(
            {row[0] for row in self.conn.execute("SELECT journal_norm FROM journal_metrics WHERE provider='jcr'")},
            {"original"},
        )

        replacement = self.root / "replacement-metrics.csv"
        replacement.write_text("Journal,ISSN,Quartile\nReplacement,8765-4321,Q1\n", encoding="utf-8")
        lw.import_metrics(self.conn, "jcr", replacement, 2025, None, None, replace_edition=True)
        self.assertEqual(
            {row[0] for row in self.conn.execute("SELECT journal_norm FROM journal_metrics WHERE provider='jcr'")},
            {"replacement"},
        )

    def test_seed_and_metric_writes_respect_workspace_lock(self):
        workspace = self.root / "locked-workspace"
        workspace.mkdir()
        lw.write_json(workspace / "config.json", lw.DEFAULT_CONFIG)
        lw.connect_db(workspace, create=True).close()
        seed = self.root / "locked-seed.json"
        seed.write_text(json.dumps({"title": "Should not be written"}), encoding="utf-8")
        metrics = self.root / "locked-metrics.csv"
        metrics.write_text("Journal,ISSN,Quartile\nJ,1234-5678,Q1\n", encoding="utf-8")
        (workspace / ".litwatch.lock").write_text("fixture", encoding="utf-8")
        with self.assertRaises(lw.LitWatchError):
            lw.command_seed_add(argparse.Namespace(
                workspace=str(workspace), inputs=[str(seed)], negative=False, replace=False, offline=True,
            ))
        with self.assertRaises(lw.LitWatchError):
            lw.command_metrics_import(argparse.Namespace(
                workspace=str(workspace), provider="jcr", file=str(metrics), year=2025,
                mapping=None, encoding=None,
            ))
        conn = lw.connect_db(workspace, readonly=True)
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM seeds").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM journal_metrics").fetchone()[0], 0)
        finally:
            conn.close()

    def test_replace_seed_batch_is_atomic(self):
        workspace = self.root / "seed-workspace"
        workspace.mkdir()
        lw.write_json(workspace / "config.json", lw.DEFAULT_CONFIG)
        conn = lw.connect_db(workspace, create=True)
        original = work(title="Original seed", doi="10.1234/original", openalex_id="W700")
        conn.execute(
            "INSERT INTO seeds(seed_key,polarity,input_label,work_json,added_at) VALUES(?,?,?,?,?)",
            (lw.canonical_work_key(original), "positive", "original", json.dumps(original), lw.iso_now()),
        )
        conn.commit()
        conn.close()
        valid = self.root / "valid.json"
        valid.write_text(json.dumps({"title": "Replacement", "doi": "10.1234/replacement"}), encoding="utf-8")
        broken = self.root / "broken.json"
        broken.write_text("{", encoding="utf-8")
        args = argparse.Namespace(
            workspace=str(workspace),
            inputs=[str(valid), str(broken)],
            negative=False,
            replace=True,
            offline=True,
        )
        with self.assertRaises(lw.LitWatchError):
            lw.command_seed_add(args)
        conn = lw.connect_db(workspace, readonly=True)
        rows = conn.execute("SELECT work_json FROM seeds").fetchall()
        conn.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(json.loads(rows[0][0])["title"], "Original seed")

    def test_seed_batch_reports_unique_writes(self):
        workspace = self.root / "dedupe-seed-workspace"
        workspace.mkdir()
        lw.write_json(workspace / "config.json", lw.DEFAULT_CONFIG)
        lw.connect_db(workspace, create=True).close()
        first = self.root / "first-seed.json"
        second = self.root / "second-seed.json"
        first.write_text(json.dumps({"title": "First title", "doi": "10.1234/same"}), encoding="utf-8")
        second.write_text(json.dumps({"title": "Second title", "doi": "10.1234/same", "abstract": "More metadata"}), encoding="utf-8")
        output = io.StringIO()
        with patch("sys.stdout", output):
            lw.command_seed_add(argparse.Namespace(
                workspace=str(workspace), inputs=[str(first), str(second)], negative=False,
                replace=False, offline=True,
            ))
        summary = json.loads(output.getvalue())
        self.assertEqual((summary["inputs_parsed"], summary["duplicates_collapsed"], summary["added"]), (2, 1, 1))
        conn = lw.connect_db(workspace, readonly=True)
        try:
            stored = json.loads(conn.execute("SELECT work_json FROM seeds").fetchone()[0])
            self.assertEqual((stored["title"], stored["abstract"]), ("Second title", "More metadata"))
        finally:
            conn.close()

    def test_refresh_preserves_screening_and_rotation_includes_formerly_relevant(self):
        cfg = deepcopy(lw.DEFAULT_CONFIG)
        initial = result(work(openalex_id="W810", doi="10.1234/refresh"), status="accepted", score=61)
        stored = lw.upsert_result(self.conn, initial, "2026-01-01T00:00:00Z")
        state = lw.tracked_works(self.conn)[0]
        pool = lw.CandidatePool()
        key = pool.add(lw.merge_records(state["work"], work(openalex_id="W810", doi="10.1234/refresh", cited_by_count=99)), "refresh", 1)
        pool.lifecycle[key] = state
        refreshed = lw.evaluate_pool(self.conn, pool, [work()], [], cfg)[0]
        self.assertEqual((refreshed["status"], refreshed["score"]), ("accepted", 61.0))
        self.assertEqual(refreshed["provenance"], initial["provenance"])

        pool = lw.CandidatePool()
        key = pool.add(lw.merge_records(state["work"], {"is_retracted": True, "relation_flags": ["retraction"]}), "refresh", 1)
        pool.lifecycle[key] = state
        retracted = lw.evaluate_pool(self.conn, pool, [work()], [], cfg)[0]
        self.assertEqual(retracted["status"], "rejected")
        self.assertEqual(retracted["score"], 61.0)
        lw.upsert_result(self.conn, retracted, "2026-01-02T00:00:00Z")

        second = lw.upsert_result(
            self.conn,
            result(work(openalex_id="W811", doi="10.1234/second"), status="accepted"),
            "2026-01-01T00:00:00Z",
        )
        never_relevant = lw.upsert_result(
            self.conn,
            result(work(openalex_id="W812", doi="10.1234/never"), status="rejected", score=1),
            "2026-01-01T00:00:00Z",
        )
        self.conn.execute(
            "INSERT OR REPLACE INTO source_state(source,checkpoint,updated_at) VALUES(?,?,?)",
            ("lifecycle:" + second["work_key"], "2026-01-01", "2026-01-01T00:00:00Z"),
        )
        tracked = lw.tracked_works(self.conn)
        keys = {item["work_key"] for item in tracked}
        self.assertIn(stored["work_key"], keys)
        self.assertIn(second["work_key"], keys)
        self.assertNotIn(never_relevant["work_key"], keys)
        self.assertEqual(tracked[0]["work_key"], stored["work_key"])

    def test_refresh_keeps_identity_when_openalex_redirects(self):
        cfg = deepcopy(lw.DEFAULT_CONFIG)
        original = work(doi="", pmid="", arxiv_id="", openalex_id="WOLD")
        stored = lw.upsert_result(self.conn, result(original), "2026-01-01T00:00:00Z")
        state = lw.tracked_works(self.conn)[0]
        pool = lw.CandidatePool()
        key = pool.add(lw.merge_records(state["work"], work(doi="", pmid="", arxiv_id="", openalex_id="WNEW")), "refresh", 1)
        pool.lifecycle[key] = state
        refreshed = lw.evaluate_pool(self.conn, pool, [work()], [], cfg)[0]
        updated = lw.upsert_result(self.conn, refreshed, "2026-01-02T00:00:00Z")
        self.assertEqual(updated["work_key"], stored["work_key"])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM works").fetchone()[0], 1)
        aliases = dict(self.conn.execute("SELECT alias,work_key FROM aliases"))
        self.assertEqual(aliases["openalex:WOLD"], aliases["openalex:WNEW"])


if __name__ == "__main__":
    unittest.main()
