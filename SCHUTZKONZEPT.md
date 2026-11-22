# Schutzkonzept – Notizen-API

Hier steht, welche Sicherheitsmaßnahmen umgesetzt sind, wo sie im Repository liegen und wie man sie nachprüft. Die Gliederung folgt den fünf Bewertungsfeldern.

**Vertiefungen:** Feld 2 (Code Security) und Feld 3 (Build & Supply Chain).

## Überblick

Die Notizen-API ist eine REST-API (Python 3.12, FastAPI, SQLite) zum Verwalten von Notizen. Jeder Benutzer hat eine von drei Rollen (`viewer`, `editor`, `admin`). Nach der Anmeldung mit Passwort gibt es ein Bearer-Token, daneben lassen sich API-Tokens mit eingeschränkten Rechten anlegen. Sicherheitsrelevante Vorgänge landen in einem Audit-Log.

- Bedienung, Endpunkte, Rollen: [README.md](README.md)
- Datenfluss mit allen Prüfstellen: [docs/datenfluss.md](docs/datenfluss.md)
- Ausgeliefert als Container-Image über die GitHub Container Registry

## Angriffsfläche (STRIDE)

| Bedrohung | Beispiel | Maßnahme | Restrisiko |
|---|---|---|---|
| Spoofing | Gestohlenes Passwort oder Token | scrypt-Hashes, Tokens nur als SHA-256 gespeichert, Ablaufzeit | Kein Rate-Limit beim Login. Ein gestohlenes Token kann neue Tokens mit bis zu 90 Tagen Laufzeit erzeugen |
| Tampering | Fremde Notiz ändern, SQL-Injection | Eigentümerprüfung, nur parametrisiertes SQL, SAST | Wer Dateizugriff auf die DB hat, kann alles ändern |
| Repudiation | „Ich habe das nicht gelöscht“ | Audit-Log für alle sicherheitsrelevanten Vorgänge | Audit-Log liegt in derselben, veränderbaren Datei |
| Information Disclosure | Fremde private Notizen, Secrets in Logs | Sichtbarkeit direkt im SQL, 404 statt 403, `response_model`, keine Bodies in Logs | Kein eigenes TLS. Das Bootstrap-Passwort erscheint im Log, wenn `ADMIN_PASSWORD` fehlt |
| Denial of Service | Riesige Eingaben | Längen- und Wertgrenzen (Pydantic), `limit ≤ 100` | Kein Rate-Limit, scrypt kostet CPU je Login |
| Elevation of Privilege | Token mit mehr Rechten | Rechte = Token-Scopes ∩ aktuelle Rolle, letzter Admin geschützt | – |
| Lieferkette | Manipuliertes Paket oder Image | Hash- und Digest-Pinning, SBOM, Schwachstellen-Scan, Dependabot | Image nicht signiert |

## Feld 1 – Building von Artefakten

- **Kriterium:** 2. Ein Skript baut das Artefakt, die Nutzung ist dokumentiert.
- **Umsetzung:** `Dockerfile` (mehrstufig, non-root, Health Check) und `build.sh`, das mit dem Git-Commit taggt. `--smoke` startet den Container und prüft `/health`. Zusätzlich, nicht als Vertiefung gewertet: Ein Merge nach `main` veröffentlicht das Image nach GHCR.
- **Nachweise:** `Dockerfile`, `build.sh`, [docs/building.md](docs/building.md). Prüfen mit `./build.sh --smoke`.

## Feld 2 – Code Security (Vertiefung)

| Kriterium | Umsetzung | Werkzeug | Wo |
|---|---|---|---|
| 1 Fail Fast + Type Checker | Jede Eingabe wird vor der Endpunkt-Logik auf Typ, Länge, Muster und Wertebereich geprüft, Verstöße enden mit 422. mypy läuft in der CI. | Pydantic, mypy | `web/app.py` (Schemas `*In`, `Path`, `Query`), `pyproject.toml`, `ci.yml` |
| 2 Sichere Defaults + Fehlerbehandlung | Kein Standardpasswort (Zufallspasswort, wenn `ADMIN_PASSWORD` fehlt), Tokens laufen immer ab, 404 statt 403 bei fremden Notizen, einheitliche Login-Fehlermeldung. `/health` liefert 503 statt Stacktrace, unerwartete Fehler werden als `http.error` geloggt. | – | `web/app.py` |
| 3 SAST + Secret Scanning automatisiert | bandit auf den Anwendungscode, gitleaks über die gesamte Git-Historie mit eigener Regel für `nt_`-Tokens | bandit, gitleaks | `ci.yml`, `.gitleaks.toml` |

- **Datenfluss:** [docs/datenfluss.md](docs/datenfluss.md)
- **Positivtests:** [docs/positive-tests.md](docs/positive-tests.md) und `security_examples/run_positive_tests.sh`. Jedes Werkzeug findet ein echtes Problem im Demo-Code und lässt den Lauf scheitern.
- **Mitigiert:** Unsichere Muster und Secrets gelangen nicht unbemerkt in `main`. Ungültige Eingaben erreichen nie Datenbank oder Logik.
- **Verbleibend:** bandit erkennt Muster, aber keine Datenflüsse über mehrere Funktionen (nächster Schritt: CodeQL). Die gitleaks-Ausnahmen gelten für ganze Pfade, ein echtes Secret dort fiele nicht auf.

## Feld 3 – Build & Supply Chain (Vertiefung)

Details, Nachweise und lokale Reproduktion: [docs/supply-chain.md](docs/supply-chain.md).

| Kriterium | Umsetzung | Werkzeug |
|---|---|---|
| 1 Pinning (Pflicht) | Python-Pakete mit `==` und SHA-256-Hash, Basis-Image mit Tag und Digest, Actions mit Commit-SHA | pip-tools |
| 2 SBOM | CycloneDX-SBOM aus dem veröffentlichten Image, als Workflow-Artefakt | Syft |
| 3 Schwachstellen-Scan | Alle Python-Abhängigkeiten bei Push, PR und wöchentlich | pip-audit |
| 4 Updates on-demand | PRs für Python, Docker und Actions, wöchentlich und auf Knopfdruck | Dependabot |

- **Mitigiert:** Ausgetauschte Pakete, Images oder Actions brechen den Build ab. Bekannte CVEs fallen auf. Schon bei der Einführung fand pip-audit echte Lücken in `anyio` und `idna`, beide sind behoben.
- **Verbleibend:** Das Image ist nicht signiert. Debian-Pakete im Image werden nicht auf CVEs gescannt. Eine Backdoor in einer bereits gepinnten Version erkennt kein Hash.

## Feld 4 – Logging & Betrieb

- **Kriterien:** 1 (strukturierte Logs) und 2 (Health Check).
- **Umsetzung:** `web/logging_setup.py` schreibt jede Logzeile als JSON nach STDOUT. Pro Request werden Methode, Pfad, Status und Dauer geloggt, nie Body oder Token. `/health` prüft die Datenbank und liefert 200 oder 503, das Dockerfile nutzt den Endpunkt als `HEALTHCHECK`.
- **Prüfen:** `docker ps` zeigt `(healthy)`, `docker logs <id>` zeigt JSON-Zeilen.

## Feld 5 – Dynamisches Testing

- **Kriterium:** 1. 11 pytest-Tests laufen bei jeder Änderung in der CI. `scripts/mutation_demo.py` baut 6 typische Sicherheitsfehler ein und zeigt, dass jeweils ein Test scheitert.
- **Nachweise:** [docs/testing.md](docs/testing.md), Schritt „Tests (pytest)“ in `ci.yml`.
