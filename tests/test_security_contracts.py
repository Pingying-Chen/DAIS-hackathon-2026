from __future__ import annotations

import pandas as pd

from src.agent import tools


def test_district_query_uses_parameters_for_user_filters(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_sql(statement: str, timeout_seconds: int = 20, parameters: dict[str, object] | None = None) -> pd.DataFrame:
        captured["statement"] = statement
        captured["parameters"] = parameters
        return pd.DataFrame()

    monkeypatch.setattr(tools, "run_sql", fake_run_sql)

    tools.get_district_priorities(
        mission_type="maternal_health",
        state_filter="Maharashtra' or 1=1 --",
        district_filter="Nagpur",
        confidence_threshold=0.25,
    )

    assert "Maharashtra' or 1=1 --" not in str(captured["statement"])
    assert ":state_filter" in str(captured["statement"])
    assert captured["parameters"] == {"state_filter": "%Maharashtra' or 1=1 --%"}


def test_district_query_tolerates_string_nfhs_numeric_fields(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_sql(statement: str, timeout_seconds: int = 20, parameters: dict[str, object] | None = None) -> pd.DataFrame:
        captured["statement"] = statement
        captured["parameters"] = parameters
        return pd.DataFrame()

    monkeypatch.setattr(tools, "run_sql", fake_run_sql)

    tools.get_district_priorities(
        mission_type="maternal_health",
        state_filter="Maharashtra",
        district_filter="",
        confidence_threshold=0.25,
    )

    statement = str(captured["statement"])
    assert "try_cast(trim(cast(child_u5_who_are_underweight_weight_for_age_18_pct as string)) as double)" in statement
    assert "try_cast(trim(cast(hh_member_covered_health_insurance_pct as string)) as double)" in statement
    assert captured["parameters"] == {
        "state_filter": "%Maharashtra%",
        "state_filter_alias_1": "%Maharastra%",
    }


def test_facility_query_uses_parameters_for_user_filters(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_sql(statement: str, timeout_seconds: int = 20, parameters: dict[str, object] | None = None) -> pd.DataFrame:
        captured["statement"] = statement
        captured["parameters"] = parameters
        return pd.DataFrame()

    monkeypatch.setattr(tools, "run_sql", fake_run_sql)

    tools.get_facility_candidates(
        mission_type="surgery",
        state_filter="Maharashtra' or 1=1 --",
        district_filter="Nagpur%' or 'a'='a",
        confidence_threshold=0.25,
    )

    statement = str(captured["statement"])
    assert "Maharashtra' or 1=1 --" not in statement
    assert "Nagpur%' or 'a'='a" not in statement
    assert ":state_filter" in statement
    assert ":district_filter" in statement
    assert captured["parameters"] == {
        "state_filter": "%Maharashtra' or 1=1 --%",
        "district_filter": "%Nagpur%' or 'a'='a%",
    }
