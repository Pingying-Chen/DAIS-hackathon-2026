from __future__ import annotations

import pandas as pd

from src.agent import tools


def _facility_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "unique_id": "facility-1",
                "name": "Sunrise Surgical Hospital",
                "address_city": "Nagpur",
                "address_stateOrRegion": "Maharashtra",
                "address_zipOrPostcode": "440001",
                "address_country": "India",
                "specialties": "Maternal health",
                "procedure": "Surgery",
                "equipment": "NICU",
                "capability": "Emergency obstetrics",
                "description": "High-acuity women's hospital.",
                "source_urls": '["https://sunrise.example.org"]',
                "distinct_social_media_presence_count": 3,
                "affiliated_staff_presence": 1,
                "custom_logo_presence": 1,
                "numberDoctors": 20,
                "capacity": 120,
                "recency_of_page_update": "2026-05-01",
                "latitude": 21.145,
                "longitude": 79.088,
            },
            {
                "unique_id": "facility-2",
                "name": "Sunrise Surgical Centre",
                "address_city": "Nagpur",
                "address_stateOrRegion": "Maharashtra",
                "address_zipOrPostcode": "440001",
                "address_country": "India",
                "specialties": "Maternal health",
                "procedure": "Surgery",
                "equipment": "NICU",
                "capability": "Emergency obstetrics",
                "description": "Duplicate-style row for the same hospital.",
                "source_urls": '["https://sunrise.example.org/about"]',
                "distinct_social_media_presence_count": 2,
                "affiliated_staff_presence": 1,
                "custom_logo_presence": 1,
                "numberDoctors": 18,
                "capacity": 100,
                "recency_of_page_update": "2026-04-01",
                "latitude": 21.146,
                "longitude": 79.089,
            },
            {
                "unique_id": "facility-3",
                "name": "Regional Access Clinic",
                "address_city": "Aurangabad",
                "address_stateOrRegion": "Maharashtra",
                "address_zipOrPostcode": "431001",
                "address_country": "India",
                "specialties": "General access",
                "procedure": "",
                "equipment": "Basic diagnostics",
                "capability": "Referral support",
                "description": "Small clinic.",
                "source_urls": "",
                "distinct_social_media_presence_count": 0,
                "affiliated_staff_presence": 0,
                "custom_logo_presence": 0,
                "numberDoctors": 3,
                "capacity": 15,
                "recency_of_page_update": "",
                "latitude": 19.879,
                "longitude": 75.338,
            },
        ]
    )


def test_resolve_facility_entities_clusters_duplicate_rows() -> None:
    cleaned = tools._clean_facility_candidates(_facility_rows())
    resolved = tools.resolve_facility_entities(cleaned)

    first_entity = resolved.iloc[0]["resolved_entity_id"]
    second_entity = resolved.iloc[1]["resolved_entity_id"]

    assert first_entity == second_entity
    assert int(resolved.iloc[0]["entity_record_count"]) == 2
    assert "shared website domain" in resolved.iloc[0]["entity_match_reasons"]


def test_source_urls_keeps_commas_inside_single_url() -> None:
    urls = tools._source_urls("https://en.wikipedia.org/wiki/Holy_Family_Hospital,_Mumbai")

    assert urls == ["https://en.wikipedia.org/wiki/Holy_Family_Hospital,_Mumbai"]


def test_resolve_facility_entities_ignores_generic_listing_domain_for_different_names() -> None:
    raw = pd.DataFrame(
        [
            {
                "unique_id": "facility-a",
                "name": "North Surgical Hospital",
                "address_city": "Nashik",
                "address_stateOrRegion": "Maharashtra",
                "address_zipOrPostcode": "422001",
                "address_country": "India",
                "source_urls": '["https://www.justdial.com/nashik/north"]',
                "latitude": 19.991,
                "longitude": 73.782,
            },
            {
                "unique_id": "facility-b",
                "name": "South Eye Centre",
                "address_city": "Nashik",
                "address_stateOrRegion": "Maharashtra",
                "address_zipOrPostcode": "422001",
                "address_country": "India",
                "source_urls": '["https://www.justdial.com/nashik/south"]',
                "latitude": 19.992,
                "longitude": 73.783,
            },
        ]
    )
    cleaned = tools._clean_facility_candidates(raw)
    resolved = tools.resolve_facility_entities(cleaned)

    assert resolved.iloc[0]["resolved_entity_id"] != resolved.iloc[1]["resolved_entity_id"]
    assert int(resolved.iloc[0]["entity_record_count"]) == 1


def test_resolve_facility_entities_requires_distinctive_name_match() -> None:
    raw = pd.DataFrame(
        [
            {
                "unique_id": "facility-a",
                "name": "Sigma Hospitals",
                "address_city": "Hyderabad",
                "address_stateOrRegion": "Andhra Pradesh",
                "address_zipOrPostcode": "500055",
                "address_country": "India",
                "source_urls": '["https://www.medicineindia.org/hospitals-in-city/hyderabad-andhra-pradesh"]',
                "latitude": 17.5,
                "longitude": 78.4,
            },
            {
                "unique_id": "facility-b",
                "name": "Spark Hospitals",
                "address_city": "Hyderabad",
                "address_stateOrRegion": "Andhra Pradesh",
                "address_zipOrPostcode": "500039",
                "address_country": "India",
                "source_urls": '["https://www.medicineindia.org/hospitals-in-city/hyderabad-andhra-pradesh"]',
                "latitude": 17.501,
                "longitude": 78.401,
            },
        ]
    )
    cleaned = tools._clean_facility_candidates(raw)
    resolved = tools.resolve_facility_entities(cleaned)

    assert resolved.iloc[0]["resolved_entity_id"] != resolved.iloc[1]["resolved_entity_id"]
    assert int(resolved.iloc[0]["entity_record_count"]) == 1


def test_search_facility_sources_prefers_dataset_url(monkeypatch) -> None:
    cleaned = tools._clean_facility_candidates(_facility_rows().head(1))
    resolved = tools.resolve_facility_entities(cleaned)
    called = {"count": 0}

    def fake_search_public_web(query: str, limit: int = 5) -> pd.DataFrame:
        called["count"] += 1
        return pd.DataFrame()

    monkeypatch.setattr(tools, "search_public_web", fake_search_public_web)

    search_results = tools.search_facility_sources(resolved)

    assert called["count"] == 0
    assert search_results.iloc[0]["selection_source"] == "dataset_url"
    assert bool(search_results.iloc[0]["selected"]) is True


def test_search_facility_sources_returns_unavailable_row_when_search_fails(monkeypatch) -> None:
    cleaned = tools._clean_facility_candidates(_facility_rows().tail(1))
    resolved = tools.resolve_facility_entities(cleaned)

    def fake_search_public_web(query: str, limit: int = 5) -> pd.DataFrame:
        raise ConnectionError("search unavailable")

    monkeypatch.setattr(tools, "search_public_web", fake_search_public_web)

    search_results = tools.search_facility_sources(resolved)

    assert list(search_results.columns) == tools.SEARCH_RESULT_COLUMNS
    assert search_results.iloc[0]["selection_source"] == "search_unavailable"
    assert bool(search_results.iloc[0]["selected"]) is False


def test_collect_website_signals_returns_typed_row_when_scrape_fails(monkeypatch) -> None:
    cleaned = tools._clean_facility_candidates(_facility_rows().head(1))
    resolved = tools.resolve_facility_entities(cleaned)
    search_results = tools.search_facility_sources(resolved, allow_search=False)

    def fake_scrape_public_page(url: str) -> dict[str, object]:
        return {
            "url": url,
            "domain": "sunrise.example.org",
            "status": "unavailable",
            "page_title": "",
            "meta_description": "",
            "text_excerpt": "",
            "social_links": 0,
            "contact_signals": 0,
        }

    monkeypatch.setattr(tools, "scrape_public_page", fake_scrape_public_page)

    signals = tools.collect_website_signals(resolved, search_results, allow_web_enrichment=True)

    assert list(signals.columns) == tools.WEBSITE_SIGNAL_COLUMNS
    assert signals.iloc[0]["page_status"] == "unavailable"
    assert int(signals.iloc[0]["social_link_count"]) == 0


def test_collect_website_signals_returns_unavailable_row_when_scraper_raises(monkeypatch) -> None:
    cleaned = tools._clean_facility_candidates(_facility_rows().head(1))
    resolved = tools.resolve_facility_entities(cleaned)
    search_results = tools.search_facility_sources(resolved, allow_search=False)

    def fake_scrape_public_page(url: str) -> dict[str, object]:
        raise TimeoutError("scrape timed out")

    monkeypatch.setattr(tools, "scrape_public_page", fake_scrape_public_page)

    signals = tools.collect_website_signals(resolved, search_results, allow_web_enrichment=True)

    assert list(signals.columns) == tools.WEBSITE_SIGNAL_COLUMNS
    assert signals.iloc[0]["page_status"] == "unavailable"
    assert signals.iloc[0]["website_excerpt"] == ""


def test_build_trust_reviews_prefers_high_signal_facility() -> None:
    cleaned = tools._clean_facility_candidates(_facility_rows())
    resolved = tools.resolve_facility_entities(cleaned)
    search_results = pd.DataFrame(
        [
            {
                "resolved_entity_id": resolved.iloc[0]["resolved_entity_id"],
                "facility_id": "facility-1",
                "facility_name": "Sunrise Surgical Hospital",
                "query": "Sunrise Surgical Hospital Nagpur India hospital",
                "selection_source": "dataset_url",
                "result_rank": 0,
                "selected": True,
                "result_title": "Sunrise Surgical Hospital",
                "result_url": "https://sunrise.example.org",
                "result_domain": "sunrise.example.org",
                "match_confidence": 1.0,
            },
            {
                "resolved_entity_id": resolved.iloc[2]["resolved_entity_id"],
                "facility_id": "facility-3",
                "facility_name": "Regional Access Clinic",
                "query": "Regional Access Clinic Aurangabad India hospital",
                "selection_source": "search",
                "result_rank": 1,
                "selected": True,
                "result_title": "Regional Access Clinic",
                "result_url": "https://regional.example.org",
                "result_domain": "regional.example.org",
                "match_confidence": 0.62,
            },
        ],
        columns=tools.SEARCH_RESULT_COLUMNS,
    )
    website_signals = pd.DataFrame(
        [
            {
                "resolved_entity_id": resolved.iloc[0]["resolved_entity_id"],
                "facility_id": "facility-1",
                "primary_url": "https://sunrise.example.org",
                "primary_domain": "sunrise.example.org",
                "verification_source": "dataset_url",
                "page_status": "ok",
                "page_title": "Sunrise Surgical Hospital",
                "meta_description": "Hospital website",
                "website_excerpt": "Emergency obstetrics and NICU services.",
                "social_link_count": 3,
                "contact_signal_count": 2,
                "capability_mentions": 4,
                "name_match_score": 0.92,
                "domain_matches_dataset": True,
            },
            {
                "resolved_entity_id": resolved.iloc[2]["resolved_entity_id"],
                "facility_id": "facility-3",
                "primary_url": "https://regional.example.org",
                "primary_domain": "regional.example.org",
                "verification_source": "search",
                "page_status": "ok",
                "page_title": "Regional Access Clinic",
                "meta_description": "Clinic website",
                "website_excerpt": "Referral support only.",
                "social_link_count": 0,
                "contact_signal_count": 1,
                "capability_mentions": 1,
                "name_match_score": 0.55,
                "domain_matches_dataset": False,
            },
        ],
        columns=tools.WEBSITE_SIGNAL_COLUMNS,
    )

    trust_reviews = tools.build_trust_reviews(resolved, search_results, website_signals, source="live")
    sunrise_score = float(trust_reviews.loc[trust_reviews["facility_id"] == "facility-1", "trust_score_v2"].iloc[0])
    regional_score = float(trust_reviews.loc[trust_reviews["facility_id"] == "facility-3", "trust_score_v2"].iloc[0])

    assert sunrise_score > regional_score
    assert trust_reviews.loc[trust_reviews["facility_id"] == "facility-1", "website_verification_status"].iloc[0] == "verified"


def test_build_facility_review_frame_returns_one_row_per_resolved_entity() -> None:
    frame = tools._build_facility_review_frame(
        _facility_rows().head(2),
        source="fallback",
        confidence_threshold=0.25,
        allow_web_enrichment=False,
    )

    assert len(frame) == 1
    assert frame.iloc[0]["resolved_entity_id"] == "entity-01"
    assert int(frame.iloc[0]["entity_record_count"]) == 2


def test_build_facility_review_frame_uses_cached_entity_mapping(monkeypatch) -> None:
    cached = _facility_rows().head(2).copy()
    cached["resolved_entity_id"] = "entity-cache-1"
    cached["canonical_name"] = "Sunrise Surgical Hospital"
    cached["entity_record_count"] = 2
    cached["entity_match_confidence"] = 0.96
    cached["entity_match_reasons"] = "precomputed entity index"
    cached["duplicate_review_required"] = False

    def fail_runtime_resolution(*args: object, **kwargs: object) -> pd.DataFrame:
        raise AssertionError("cached entity mapping should skip runtime resolution")

    monkeypatch.setattr(tools, "resolve_facility_entities", fail_runtime_resolution)

    frame = tools._build_facility_review_frame(
        cached,
        source="live",
        confidence_threshold=0.25,
        allow_web_enrichment=False,
    )

    assert len(frame) == 1
    assert frame.attrs["entity_index_source"] == "cached"
    assert frame.iloc[0]["resolved_entity_id"] == "entity-cache-1"
    assert int(frame.iloc[0]["entity_record_count"]) == 2


def test_build_facility_review_frame_uses_runtime_when_cache_is_incomplete(monkeypatch) -> None:
    cached = _facility_rows().head(1).copy()
    cached["resolved_entity_id"] = ""
    cached["canonical_name"] = ""
    cached["entity_record_count"] = 0
    cached["entity_match_confidence"] = 0.0
    cached["entity_match_reasons"] = ""
    cached["duplicate_review_required"] = False

    def runtime_resolution(df: pd.DataFrame, *args: object, **kwargs: object) -> pd.DataFrame:
        resolved = df.copy()
        resolved["resolved_entity_id"] = "entity-runtime-1"
        resolved["canonical_name"] = resolved["name"]
        resolved["entity_record_count"] = 1
        resolved["entity_match_confidence"] = 1.0
        resolved["entity_match_reasons"] = "single row candidate"
        resolved["duplicate_review_required"] = False
        return resolved

    monkeypatch.setattr(tools, "resolve_facility_entities", runtime_resolution)

    frame = tools._build_facility_review_frame(
        cached,
        source="live",
        confidence_threshold=0.25,
        allow_web_enrichment=False,
    )

    assert frame.attrs["entity_index_source"] == "runtime"
    assert frame.iloc[0]["resolved_entity_id"] == "entity-runtime-1"


def test_resolve_entity_frame_partially_uses_cache_for_mixed_rows(monkeypatch) -> None:
    mixed = _facility_rows().head(2).copy()
    mixed.loc[mixed.index[0], "resolved_entity_id"] = "entity-cache-1"
    mixed.loc[mixed.index[0], "canonical_name"] = "Sunrise Surgical Hospital"
    mixed.loc[mixed.index[0], "entity_record_count"] = 1
    mixed.loc[mixed.index[0], "entity_match_confidence"] = 1.0
    mixed.loc[mixed.index[0], "entity_match_reasons"] = "precomputed entity index"
    mixed.loc[mixed.index[0], "duplicate_review_required"] = False
    mixed.loc[mixed.index[1], "resolved_entity_id"] = ""
    mixed.loc[mixed.index[1], "canonical_name"] = ""
    mixed.loc[mixed.index[1], "entity_record_count"] = 0
    mixed.loc[mixed.index[1], "entity_match_confidence"] = 0.0
    mixed.loc[mixed.index[1], "entity_match_reasons"] = ""
    mixed.loc[mixed.index[1], "duplicate_review_required"] = False

    def runtime_resolution(df: pd.DataFrame, *args: object, **kwargs: object) -> pd.DataFrame:
        assert list(df["unique_id"]) == ["facility-2"]
        resolved = df.copy()
        resolved["resolved_entity_id"] = "entity-runtime-1"
        resolved["canonical_name"] = resolved["name"]
        resolved["entity_record_count"] = 1
        resolved["entity_match_confidence"] = 1.0
        resolved["entity_match_reasons"] = "single row candidate"
        resolved["duplicate_review_required"] = False
        return resolved

    monkeypatch.setattr(tools, "resolve_facility_entities", runtime_resolution)

    resolved, source = tools._resolve_entity_frame(mixed)

    assert source == "partial"
    assert list(resolved["resolved_entity_id"]) == ["entity-cache-1", "entity-runtime-1"]


def test_build_entity_index_frame_is_search_ready() -> None:
    index = tools.build_entity_index_frame(_facility_rows())

    sunrise = index[index["facility_id"].isin(["facility-1", "facility-2"])]

    assert list(index.columns) == tools.ENTITY_INDEX_COLUMNS
    assert sunrise["resolved_entity_id"].nunique() == 1
    assert sunrise.iloc[0]["resolved_entity_id"].startswith("entity-")
    assert "Emergency obstetrics" in sunrise.iloc[0]["entity_search_text"]
    assert sunrise.iloc[0]["source_row_fingerprint"]
    assert len(sunrise.iloc[0]["source_row_fingerprint"]) == 40
    assert set(sunrise["primary_source_url"]) == {
        "https://sunrise.example.org",
        "https://sunrise.example.org/about",
    }


def test_source_row_fingerprint_changes_when_source_identity_changes() -> None:
    base = _facility_rows().head(1)
    changed = base.copy()
    changed.loc[changed.index[0], "name"] = "Sunrise Surgical Annex"

    base_fingerprint = tools.build_entity_index_frame(base).iloc[0]["source_row_fingerprint"]
    changed_fingerprint = tools.build_entity_index_frame(changed).iloc[0]["source_row_fingerprint"]

    assert base_fingerprint != changed_fingerprint


def test_build_entity_index_frame_keeps_non_unique_ids_by_fingerprint() -> None:
    raw = _facility_rows().head(1)
    duplicate_id_variant = raw.copy()
    duplicate_id_variant.loc[duplicate_id_variant.index[0], "description"] = "Updated source description."
    combined = pd.concat([raw, duplicate_id_variant], ignore_index=True)

    index = tools.build_entity_index_frame(combined)

    assert len(index) == 2
    assert index["facility_id"].nunique() == 1
    assert index["source_row_fingerprint"].nunique() == 2
    assert index["resolved_entity_id"].nunique() == 1
