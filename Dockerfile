# syntax=docker/dockerfile:1

# ─── Build-Stufe: Abhängigkeiten in ein venv, hash-verifiziert ─────────────────
# Basis-Image mit Tag gepinnt. Für die Immer-Pflicht aus Feld 3 den Digest
# ergänzen – einmalig mit dem echten Wert eurer Registry ermitteln:
#   docker pull python:3.12-slim
#   docker inspect --format='{{index .RepoDigests 0}}' python:3.12-slim
# und dann als  python:3.12-slim@sha256:<DIGEST>  eintragen (hier und unten).
FROM python:3.12-slim AS build

WORKDIR /app
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# Nur die gepinnte Anforderungsliste kopieren (bessere Layer-Caches)
COPY requirements.txt .

# Virtuelle Umgebung aufbauen und AUSSCHLIESSLICH gepinnte, per Hash
# verifizierte Pakete installieren. --require-hashes bricht bei Abweichung ab.
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --require-hashes -r requirements.txt

# ─── Laufzeit-Stufe: schlankes Image ohne Build-Werkzeuge ──────────────────────
# Denselben Digest wie oben eintragen.
FROM python:3.12-slim

# curl für den Container-Health-Check; danach Paketlisten aufräumen
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Nicht als root laufen (sichere Defaults)
RUN useradd --create-home --uid 10001 appuser
WORKDIR /app

COPY --from=build /opt/venv /opt/venv
COPY web/app.py ./

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    NOTES_DB=/data/notes.db \
    LOG_LEVEL=INFO

# Datenverzeichnis als Volume, dem unprivilegierten Nutzer gehörend
RUN mkdir -p /data && chown appuser:appuser /data
VOLUME ["/data"]
USER appuser

EXPOSE 8000

# Container-Health-Check nutzt denselben /health-Endpunkt wie das Skript
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

# ADMIN_PASSWORD wird zur Laufzeit als Secret übergeben, nie im Image gebacken
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
