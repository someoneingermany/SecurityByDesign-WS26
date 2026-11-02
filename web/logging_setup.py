"""
Strukturiertes JSON-Logging nach STDOUT (Feld 4: Logging & Betrieb).

Jede Logzeile ist ein eigenständiges JSON-Objekt ("JSON Lines"), damit
Monitoring-Werkzeuge (Loki, ELK, Datadog …) die Felder ohne Parser-Regeln
auswerten können. Das Auswerteskript scripts/analyze_logs.py nutzt genau
dieses Format, um Verfügbarkeit und Fehlerquote zu bestimmen.
"""
import json
import logging
import sys
import time
from datetime import datetime, timezone

SERVICE = "notizen-api"


class JsonFormatter(logging.Formatter):
    """Formatiert einen LogRecord als eine Zeile JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "service": SERVICE,
            "msg": record.getMessage(),
        }
        # Zusätzliche Felder, die über logger.info(..., extra={"fields": {...}})
        # mitgegeben wurden, flach in die Ausgabe übernehmen.
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    # Uvicorns eigene Access-Logs stummschalten – wir loggen Requests selbst
    # strukturiert, doppelte Zeilen in zwei Formaten wären nur Rauschen.
    logging.getLogger("uvicorn.access").handlers.clear()
    logging.getLogger("uvicorn.access").propagate = False


log = logging.getLogger("notizen")


def log_event(event: str, level: int = logging.INFO, **fields: object) -> None:
    """Ein benanntes Ereignis mit beliebigen Zusatzfeldern loggen."""
    log.log(level, event, extra={"fields": {"event": event, **fields}})


class RequestTimer:
    """Kontexthilfe, um die Dauer eines Requests in Millisekunden zu messen."""

    def __enter__(self) -> "RequestTimer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc: object) -> None:
        self.duration_ms = round((time.perf_counter() - self._start) * 1000, 2)
