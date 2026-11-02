#!/usr/bin/env bash
# Positivtests für Feld 2 (Code Security).
#
# Zeigt, dass jedes Werkzeug reale Probleme im bewusst fehlerhaften Demo-Code
# erkennt. Jedes Werkzeug MUSS hier anschlagen; tut es das nicht, endet das
# Skript mit Exit 1 – der Positivtest ist damit selbst überprüfbar.
#
# Nutzung:  security_examples/run_positive_tests.sh   (aus beliebigem Verzeichnis)
# Voraussetzung: pip install -r web/requirements-dev.txt  und  gitleaks im PATH
set -u
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"
GITLEAKS="${GITLEAKS:-gitleaks}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fail=0

echo "== Positivtest 1: mypy (Type Checker) muss Typfehler melden =="
if "$PY" -m mypy --config-file pyproject.toml security_examples/type_error_demo.py >"$TMP/mypy.txt" 2>&1; then
    echo "  FEHLGESCHLAGEN: mypy meldete KEINE Fehler (erwartet: Fehler)"; fail=1
else
    echo "  OK: mypy meldet Fehler und schlägt fehl (Exit != 0)"
    grep -E "error" "$TMP/mypy.txt" | sed 's/^/    /'
fi

echo "== Positivtest 2: bandit (SAST) muss im Demo-Code Funde melden =="
if "$PY" -m bandit -r security_examples/insecure_demo.py >"$TMP/bandit.txt" 2>&1; then
    echo "  FEHLGESCHLAGEN: bandit meldete KEINE Funde (erwartet: Funde)"; fail=1
else
    echo "  OK: bandit meldet Funde und schlägt fehl (Exit != 0)"
    grep -E "Issue:" "$TMP/bandit.txt" | sed 's/^/    /'
fi

echo "== Positivtest 3: gitleaks (Secret Scanning) muss Secrets finden =="
# Config ohne den security_examples-Ausschluss, damit der Demo-Ordner geprüft wird
grep -v "security_examples" .gitleaks.toml >"$TMP/gl.toml"
if "$GITLEAKS" detect --no-git --source security_examples/insecure_demo.py --config "$TMP/gl.toml" \
        --report-path "$TMP/gl.json" --report-format json --no-banner >/dev/null 2>&1; then
    echo "  FEHLGESCHLAGEN: gitleaks fand KEINE Secrets (erwartet: Funde)"; fail=1
else
    echo "  OK: gitleaks schlägt fehl (Exit != 0), Funde:"
    "$PY" -c "import json,sys;[print('    ',f['RuleID'],f['File']+':'+str(f['StartLine'])) for f in json.load(open(sys.argv[1]))]" "$TMP/gl.json"
fi

echo "== Positivtest 4: Fail Fast – ungültige Eingabe wird früh mit 422 abgewiesen =="
(cd web && ADMIN_PASSWORD="positivtest-passwort-123" NOTES_DB="$TMP/notes.db" "$PY" - <<'PY'
from fastapi.testclient import TestClient
import app
with TestClient(app.app) as c:
    r = c.post("/auth/login", json={"username": "admin", "password": "positivtest-passwort-123"})
    tok = {"Authorization": f"Bearer {r.json()['access_token']}"}
    bad = c.post("/notes", headers=tok, json={"title": ""})
    assert bad.status_code == 422, f"erwartet 422, bekommen {bad.status_code}"
    print("    leerer Titel      ->", bad.status_code, "(abgewiesen, kein 500)")
    bad = c.post("/admin/users", headers=tok, json={"username": "x'; DROP", "password": "kurz"})
    assert bad.status_code == 422, f"erwartet 422, bekommen {bad.status_code}"
    print("    ungültiger Nutzer ->", bad.status_code, "(abgewiesen, kein 500)")
PY
) 2>&1 | grep -v '^{"ts"'
[ "${PIPESTATUS[0]}" -ne 0 ] && { echo "  FEHLGESCHLAGEN: Fail-Fast-Validierung griff nicht"; fail=1; } || echo "  OK"

echo ""
if [ "$fail" -eq 0 ]; then
    echo "Alle Positivtests erfolgreich: die Werkzeuge erkennen die Probleme."
else
    echo "Mindestens ein Positivtest ist fehlgeschlagen."
fi
exit "$fail"
