"""OpenTelemetry tracing and log export for Forge backend services."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

_configured = False
_logger = logging.getLogger(__name__)


class _TraceContextFormatter(logging.Formatter):
    """Append trace/span ids when LoggingInstrumentor has enriched the record."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        trace_id = getattr(record, "otelTraceID", None)
        span_id = getattr(record, "otelSpanID", None)
        if trace_id and trace_id != "0":
            return f"{base} trace_id={trace_id} span_id={span_id or '0'}"
        return base


def _sdk_disabled() -> bool:
    return os.getenv("OTEL_SDK_DISABLED", "").lower() in ("true", "1", "yes")


def _logs_exporter_enabled() -> bool:
    exporter = os.getenv("OTEL_LOGS_EXPORTER", "otlp").strip().lower()
    return exporter not in ("", "none", "false", "0")


def _traces_exporter_enabled() -> bool:
    exporter = os.getenv("OTEL_TRACES_EXPORTER", "otlp").strip().lower()
    return exporter not in ("", "none", "false", "0")


def _parse_resource_attributes() -> dict[str, str]:
    attrs: dict[str, str] = {}
    raw = os.getenv("OTEL_RESOURCE_ATTRIBUTES", "").strip()
    if not raw:
        return attrs
    for part in raw.split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, value = part.split("=", 1)
        attrs[key.strip()] = value.strip()
    return attrs


def _service_name(service_name: str | None) -> str:
    return (service_name or os.getenv("OTEL_SERVICE_NAME") or "forge-backend").strip()


def _build_resource(service_name: str | None = None):
    from opentelemetry.sdk.resources import Resource

    resource_attrs = _parse_resource_attributes()
    resource_attrs.setdefault("service.name", _service_name(service_name))
    return Resource.create(resource_attrs)


def _otlp_endpoint() -> str:
    return os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")


def _setup_stdout_logging() -> None:
    root = logging.getLogger()
    if any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(
        _TraceContextFormatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )
    root.addHandler(handler)
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    root.setLevel(getattr(logging, level, logging.INFO))


def _setup_otlp_logging(resource, endpoint: str) -> None:
    from opentelemetry._logs import set_logger_provider
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

    root = logging.getLogger()
    if any(isinstance(h, LoggingHandler) for h in root.handlers):
        return

    logger_provider = LoggerProvider(resource=resource)
    set_logger_provider(logger_provider)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint, insecure=True))
    )
    root.addHandler(LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider))


def configure_telemetry(service_name: str | None = None) -> None:
    """Initialize OTLP traces/logs and httpx instrumentation (idempotent).

    Order: Resource → TracerProvider → LoggingInstrumentor → OTLP logs → httpx.
    Call at process start before FastAPI middleware; use instrument_fastapi on the app.
    """
    global _configured
    _setup_stdout_logging()
    if _configured:
        return
    _configured = True

    name = _service_name(service_name)
    if _sdk_disabled():
        _logger.info(
            "telemetry configured service=%s traces=off logs=off",
            name,
        )
        return

    traces_on = _traces_exporter_enabled()
    logs_on = _logs_exporter_enabled()
    if not traces_on and not logs_on:
        _logger.info(
            "telemetry configured service=%s traces=off logs=off",
            name,
        )
        return

    resource = _build_resource(service_name)
    endpoint = _otlp_endpoint()

    from opentelemetry import trace
    from opentelemetry.baggage.propagation import W3CBaggagePropagator
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.propagate import set_global_textmap
    from opentelemetry.propagators.composite import CompositePropagator
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

    if traces_on:
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

    try:
        from opentelemetry.instrumentation.logging import LoggingInstrumentor

        LoggingInstrumentor().instrument(set_logging_format=False)
    except Exception:  # noqa: BLE001
        pass

    if logs_on:
        _setup_otlp_logging(resource, endpoint)

    propagators = [
        p.strip()
        for p in os.getenv("OTEL_PROPAGATORS", "tracecontext,baggage").split(",")
        if p.strip()
    ]
    text_map_propagators = []
    for key in propagators:
        if key == "tracecontext":
            text_map_propagators.append(TraceContextTextMapPropagator())
        elif key == "baggage":
            text_map_propagators.append(W3CBaggagePropagator())
    if traces_on and text_map_propagators:
        set_global_textmap(CompositePropagator(text_map_propagators))

    if traces_on:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()

    _logger.info(
        "telemetry configured service=%s traces=%s logs=%s",
        name,
        "on" if traces_on else "off",
        "on" if logs_on else "off",
    )


def configure_tracing(service_name: str | None = None) -> None:
    """Alias for configure_telemetry (backward compatible)."""
    configure_telemetry(service_name)


def configure_logging(service_name: str | None = None) -> None:
    """Alias for configure_telemetry (backward compatible)."""
    configure_telemetry(service_name)


def instrument_fastapi(app: FastAPI) -> None:
    """Attach FastAPI request/response spans to an application instance."""
    if _sdk_disabled() or not _traces_exporter_enabled():
        return
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)
