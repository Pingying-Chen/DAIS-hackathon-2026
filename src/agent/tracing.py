from __future__ import annotations

from collections.abc import Callable
from functools import wraps
import os
from typing import Any, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

try:
    import mlflow
    from mlflow.entities import SpanType
except ImportError:  # pragma: no cover - local dev may not have mlflow installed
    mlflow = None
    SpanType = None


def tracing_status() -> dict[str, object]:
    available = mlflow is not None
    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI", "")
    experiment_id = os.environ.get("MLFLOW_EXPERIMENT_ID", "")
    return {
        "provider": "mlflow",
        "available": available,
        "configured": bool(tracking_uri and experiment_id),
        "tracking_uri": tracking_uri,
        "experiment_id": experiment_id,
    }


def _trace_inputs(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    names = ["mission_type", "mission_label", "state_filter", "district_filter", "confidence_threshold", "run_id"]
    values = {name: value for name, value in zip(names, args, strict=False)}
    values.update({name: kwargs[name] for name in names if name in kwargs})
    return values


def _trace_outputs(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {"result_type": type(result).__name__}
    packet = result.get("mission_packet", {})
    trace = result.get("mission_control_trace", [])
    districts = result.get("districts")
    facilities = result.get("facilities")
    citations = result.get("citations")
    return {
        "packet_action": packet.get("action_state", ""),
        "packet_confidence": packet.get("confidence", ""),
        "gate_sequence": [item.get("gate", "") for item in trace if isinstance(item, dict)],
        "warning_count": len(result.get("warnings", [])),
        "district_rows": int(len(districts)) if districts is not None else 0,
        "facility_rows": int(len(facilities)) if facilities is not None else 0,
        "citation_rows": int(len(citations)) if citations is not None else 0,
        "summary_source": result.get("summary_source", ""),
        "provenance": result.get("provenance", ""),
    }


def trace_agent_run(name: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorator(function: Callable[P, R]) -> Callable[P, R]:
        @wraps(function)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            if mlflow is None or SpanType is None or not tracing_status()["configured"]:
                return function(*args, **kwargs)

            span_type = getattr(SpanType, "AGENT", "AGENT")
            try:
                span_context = mlflow.start_span(name=name, span_type=span_type)
            except Exception:
                return function(*args, **kwargs)

            with span_context as span:
                span.set_inputs(_trace_inputs(args, kwargs))
                result = function(*args, **kwargs)
                span.set_outputs(_trace_outputs(result))
                return result

        return wrapper

    return decorator
