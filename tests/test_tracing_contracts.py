from __future__ import annotations

from src.agent.tracing import tracing_status


def test_tracing_status_is_typed_without_runtime_configuration() -> None:
    status = tracing_status()

    assert status["provider"] == "mlflow"
    assert isinstance(status["available"], bool)
    assert isinstance(status["configured"], bool)
    assert isinstance(status["tracking_uri"], str)
    assert isinstance(status["experiment_id"], str)
