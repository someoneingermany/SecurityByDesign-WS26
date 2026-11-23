# ─── Build-Stufe: Abhängigkeiten in ein venv, hash-verifiziert ─────────────────
# Basis-Image mit Tag UND Digest gepinnt (Feld 3, Immer-Pflicht). Maßgeblich ist
# der Digest: Er ändert sich nie, ein Tag schon. Dependabot hält ihn aktuell.
FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b AS build

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
# Derselbe Digest wie oben. Kein apt-get: curl wäre ein ungepinntes Paket,
# der Health Check unten nutzt deshalb Python.
FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b

# Nicht als root laufen (sichere Defaults)
RUN useradd --create-home --uid 10001 appuser
WORKDIR /app

COPY --from=build /opt/venv /opt/venv
COPY web/app.py web/logging_setup.py ./

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
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"]

# ADMIN_PASSWORD wird zur Laufzeit als Secret übergeben, nie im Image gebacken
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
