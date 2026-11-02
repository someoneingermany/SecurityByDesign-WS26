#!/usr/bin/env bash
# Build-Skript (Feld 1: Building von Artefakten).
# Baut das Container-Image reproduzierbar und taggt es mit dem Git-Commit.
#
# Nutzung:
#   ./build.sh                 # baut Image  notizen-api:<kurzer-commit>  + :latest
#   ./build.sh --smoke         # baut und startet kurz zum Funktionstest
#   IMAGE=ghcr.io/org/notizen-api ./build.sh   # eigenen Namen/Registry setzen
set -euo pipefail

IMAGE="${IMAGE:-notizen-api}"
GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo dev)"
TAG="${IMAGE}:${GIT_SHA}"

echo ">> Baue ${TAG}"
docker build -t "${TAG}" -t "${IMAGE}:latest" .
echo ">> Fertig: ${TAG}  und  ${IMAGE}:latest"

if [ "${1:-}" = "--smoke" ]; then
    echo ">> Smoke-Test: Container starten und /health prüfen"
    cid="$(docker run -d -p 8000:8000 -e ADMIN_PASSWORD="smoke-test-passwort-123" "${TAG}")"
    trap 'docker rm -f "$cid" >/dev/null 2>&1 || true' EXIT
    for i in $(seq 1 10); do
        sleep 1
        if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
            echo ">> OK: /health antwortet, Image ist lauffähig"
            exit 0
        fi
    done
    echo ">> FEHLER: /health antwortete nicht rechtzeitig" >&2
    docker logs "$cid" >&2 || true
    exit 1
fi
