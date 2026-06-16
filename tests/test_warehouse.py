from __future__ import annotations

from src.db import warehouse


def test_workspace_client_sets_plaintext_auth_storage_for_profile(monkeypatch) -> None:
    calls: list[dict[str, str]] = []

    class FakeWorkspaceClient:
        def __init__(self, profile: str | None = None) -> None:
            calls.append({"profile": profile or ""})

    monkeypatch.setenv("DATABRICKS_PROFILE", "free databricks")
    monkeypatch.delenv("DATABRICKS_CONFIG_PROFILE", raising=False)
    monkeypatch.delenv("DATABRICKS_AUTH_STORAGE", raising=False)
    monkeypatch.setattr(warehouse, "WorkspaceClient", FakeWorkspaceClient)

    warehouse._workspace_client()

    assert calls == [{"profile": "free databricks"}]
    assert warehouse.os.environ["DATABRICKS_AUTH_STORAGE"] == "plaintext"


def test_run_sql_preserves_execution_error(monkeypatch) -> None:
    class FakeStatementExecution:
        def execute_statement(self, *args: object, **kwargs: object) -> object:
            raise RuntimeError("warehouse unavailable")

    class FakeWorkspaceClient:
        statement_execution = FakeStatementExecution()

    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "warehouse-1")
    monkeypatch.delenv("DATABRICKS_PROFILE", raising=False)
    monkeypatch.delenv("DATABRICKS_CONFIG_PROFILE", raising=False)
    monkeypatch.setattr(warehouse, "WorkspaceClient", FakeWorkspaceClient)

    result = warehouse.run_sql("select 1")

    assert result.empty
    assert result.attrs["error"] == "warehouse unavailable"
