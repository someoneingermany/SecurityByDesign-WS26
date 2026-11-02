# Positivtests der Sicherheitswerkzeuge (Feld 2: Code Security)

Ein Positivtest zeigt, dass ein Werkzeug ein echtes Problem **erkennt** und der Lauf dann **fehlschlägt**. Dazu liegt im Ordner `security_examples/` bewusst fehlerhafter Code:

- `insecure_demo.py` enthält Secrets im Klartext, Shell-Injection und `eval`.
- `type_error_demo.py` enthält Typfehler.

Dieser Code gehört nicht zur Anwendung. Er ist vom regulären SAST-Lauf (`exclude_dirs` in `pyproject.toml`) und vom regulären Secret-Scan (Allowlist in `.gitleaks.toml`) ausgenommen. Nur die Positivtests prüfen ihn gezielt.

## Automatisierung in der CI

`.github/workflows/ci.yml` läuft bei jedem Push auf `main`/`develop` und bei jedem Pull Request. Jeder Fund lässt den Job fehlschlagen:

| Schritt | Werkzeug | Befehl |
|---|---|---|
| Typprüfung | mypy | `mypy` (Dateien aus `pyproject.toml`) |
| SAST | bandit | `bandit -c pyproject.toml -r web/app.py web/logging_setup.py` |
| Tests | pytest | `pytest -q` |
| Secret Scanning | gitleaks | `gitleaks/gitleaks-action` über die gesamte Git-Historie |

## Ausführen

```bash
python -m venv .venv && source .venv/bin/activate
pip install --require-hashes -r requirements.txt
pip install -r web/requirements-dev.txt
brew install gitleaks            # oder Release von github.com/gitleaks/gitleaks
./security_examples/run_positive_tests.sh
```

Schlägt ein Werkzeug **nicht** an, endet das Skript mit Exit-Code 1. Der Positivtest ist damit selbst überprüfbar.

## Ergebnis eines echten Laufs (2026-11-02)

```text
== Positivtest 1: mypy (Type Checker) muss Typfehler melden ==
  OK: mypy meldet Fehler und schlägt fehl (Exit != 0)
    security_examples/type_error_demo.py:12: error: Argument 1 to "add_days" has incompatible type "str"; expected "int"  [arg-type]
    security_examples/type_error_demo.py:16: error: Incompatible return value type (got "int", expected "str")  [return-value]
    Found 2 errors in 1 file (checked 1 source file)
== Positivtest 2: bandit (SAST) muss im Demo-Code Funde melden ==
  OK: bandit meldet Funde und schlägt fehl (Exit != 0)
    >> Issue: [B404:blacklist] Consider possible security implications associated with the subprocess module.
    >> Issue: [B105:hardcoded_password_string] Possible hardcoded password: 'nt_A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0U1v2'
    >> Issue: [B105:hardcoded_password_string] Possible hardcoded password: 'SuperGeheim123!'
    >> Issue: [B602:subprocess_popen_with_shell_equals_true] subprocess call with shell=True identified, security issue.
    >> Issue: [B307:blacklist] Use of possibly insecure function - consider using safer ast.literal_eval.
== Positivtest 3: gitleaks (Secret Scanning) muss Secrets finden ==
  OK: gitleaks schlägt fehl (Exit != 0), Funde:
     notizen-api-token security_examples/insecure_demo.py:19
     stripe-access-token security_examples/insecure_demo.py:21
     github-pat security_examples/insecure_demo.py:20
== Positivtest 4: Fail Fast – ungültige Eingabe wird früh mit 422 abgewiesen ==
    leerer Titel      -> 422 (abgewiesen, kein 500)
    ungültiger Nutzer -> 422 (abgewiesen, kein 500)
  OK

Alle Positivtests erfolgreich: die Werkzeuge erkennen die Probleme.
```

## Zusammenfassung

| Werkzeug | Problem im Demo-Code | Fund | Ergebnis |
|---|---|---|---|
| mypy | `str` statt `int` als Argument | `arg-type` | Exit ≠ 0 |
| mypy | `int` statt `str` als Rückgabe | `return-value` | Exit ≠ 0 |
| bandit | `subprocess.call(cmd, shell=True)` | B602, Severity High | Exit ≠ 0 |
| bandit | `eval(expr)` | B307, Severity Medium | Exit ≠ 0 |
| bandit | hartkodiertes Passwort | B105 | Exit ≠ 0 |
| gitleaks | GitHub-PAT im Klartext | `github-pat` | Exit ≠ 0 |
| gitleaks | Stripe-Token im Klartext | `stripe-access-token` | Exit ≠ 0 |
| gitleaks | API-Token mit Präfix `nt_` | eigene Regel `notizen-api-token` | Exit ≠ 0 |
| Fail Fast (Pydantic) | leerer Notiztitel | HTTP 422 statt 500 | früh abgewiesen |
| Fail Fast (Pydantic) | ungültiger Benutzername, zu kurzes Passwort | HTTP 422 statt 500 | früh abgewiesen |

## Gegenprobe

Auf dem produktiven Code melden dieselben Werkzeuge **keine** Funde. Sie färben also nicht pauschal alles rot, sondern treffen gezielt die echten Probleme:

```text
$ mypy
Success: no issues found in 2 source files
$ bandit -c pyproject.toml -r web/app.py web/logging_setup.py
        High: 0   Medium: 0   Low: 0
$ gitleaks detect --no-git --source . --config .gitleaks.toml
INF no leaks found
$ pytest -q
...........                                                              [100%]
```
