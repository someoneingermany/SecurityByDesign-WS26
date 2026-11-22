# Nachweise

Diese Seite zeigt, **wo im Repository welches Prüfungskriterium erfüllt wird** und wie man es nachprüft.
Begründungen und Restrisiken stehen im [Schutzkonzept](../SCHUTZKONZEPT.md).

> [!NOTE]
> **Unsere Vertiefungen:** Feld 2 (Code Security) und Feld 3 (Build & Supply Chain).

**Inhalt:**
[Überblick](#überblick) ·
[Feld 1](#feld-1--building-von-artefakten) ·
[Feld 2](#feld-2--code-security-vertiefung) ·
[Feld 3](#feld-3--build--supply-chain-vertiefung) ·
[Feld 4](#feld-4--logging--betrieb) ·
[Feld 5](#feld-5--dynamisches-testing) ·
[Dokumentation](#dokumentation) ·
[Lokal prüfen](#alles-lokal-prüfen)

## Überblick

| Feld | Erfüllt | Wichtigste Dateien |
|:--|:--|:--|
| 1 Building | Kriterium 2 | `Dockerfile`, `build.sh` |
| 2 Code Security | **Vertiefung** (alle 3 Kriterien) | `web/app.py`, `ci.yml`, `security_examples/` |
| 3 Supply Chain | **Vertiefung** (alle 4 Kriterien) | `requirements*.txt`, `ci.yml`, `build-deploy.yml`, `dependabot.yml` |
| 4 Logging & Betrieb | Kriterien 1 und 2 | `web/logging_setup.py`, `web/app.py` |
| 5 Testing | Kriterium 1 | `web/testapi.py`, `scripts/mutation_demo.py` |

---

## Feld 1 – Building von Artefakten

**Kriterium 2: Ein Skript baut das Artefakt, die Nutzung ist dokumentiert**

- **Umsetzung:** mehrstufiges Container-Image (non-root, Health Check). `build.sh` baut es und taggt mit dem Git-Commit.
- **Dateien:** `Dockerfile`, `build.sh`, [docs/building.md](building.md)
- **Prüfen:** `./build.sh --smoke` endet mit `OK`

**Zusatz, nicht als Vertiefung gewertet:** Ein Merge nach `main` veröffentlicht das Image nach GHCR
(`.github/workflows/build-deploy.yml`).

---

## Feld 2 – Code Security (Vertiefung)

**Kriterium 1: Fail Fast + Type Checker**

- **Umsetzung:** Pydantic prüft jede Eingabe vor der Endpunkt-Logik, Verstöße enden mit 422. mypy läuft in der CI.
- **Dateien:** `web/app.py` (Schemas `*In`, `Path`, `Query`), `pyproject.toml`, `.github/workflows/ci.yml`
- **Prüfen:** `mypy`

**Kriterium 2: Sichere Defaults + Fehlerbehandlung**

- **Umsetzung:** kein Standardpasswort, Tokens laufen immer ab, 404 statt 403 bei fremden Notizen, `/health` liefert 503 statt Stacktrace, unerwartete Fehler werden als `http.error` geloggt.
- **Dateien:** `web/app.py` (`init_db`, `load_note`, `health`, `access_log`)
- **Prüfen:** `pytest`

**Kriterium 3: SAST + Secret Scanning, automatisiert**

- **Umsetzung:** bandit und gitleaks laufen bei jedem Push und Pull Request.
- **Dateien:** `.github/workflows/ci.yml`, `.gitleaks.toml`
- **Prüfen:** Workflow „CI“ im Tab *Actions*

**Zusätzlich für die Vertiefung**

- **Datenfluss:** [docs/datenfluss.md](datenfluss.md)
- **Positivtest je Werkzeug:** [docs/positive-tests.md](positive-tests.md), Skript `security_examples/run_positive_tests.sh`

---

## Feld 3 – Build & Supply Chain (Vertiefung)

**Kriterium 1: Versionen mit Release-Tag und Prüfsumme (Pflicht für alle)**

- **Umsetzung:** Python-Pakete mit `==` und SHA-256-Hash, Basis-Image mit Digest, Actions mit Commit-SHA.
- **Dateien:** `requirements.txt`, `web/requirements-dev.txt`, `Dockerfile`, `.github/workflows/*.yml`
- **Prüfen:** `pip install --require-hashes -r web/requirements-dev.txt`

**Kriterium 2: SBOM**

- **Umsetzung:** Syft erzeugt eine CycloneDX-SBOM aus dem veröffentlichten Image.
- **Dateien:** `.github/workflows/build-deploy.yml`
- **Prüfen:** Lauf „Build & Publish“ → Abschnitt *Artifacts*

**Kriterium 3: Schwachstellen-Scan**

- **Umsetzung:** pip-audit bei jedem Push, jedem PR und wöchentlich.
- **Dateien:** `.github/workflows/ci.yml`
- **Prüfen:** `pip-audit --require-hashes --disable-pip -r requirements.txt`

**Kriterium 4: Automatische Updates, auch auf Knopfdruck**

- **Umsetzung:** Dependabot für pip, Docker und GitHub Actions.
- **Dateien:** `.github/dependabot.yml`
- **Prüfen:** Tab *Pull requests*, Autor `dependabot`

**Zusätzlich für die Vertiefung**

- **Nachweise und lokale Reproduktion:** [docs/supply-chain.md](supply-chain.md)

---

## Feld 4 – Logging & Betrieb

**Kriterium 1: Strukturierte Logs**

- **Umsetzung:** jede Logzeile als JSON nach STDOUT, nie Request-Bodies oder Tokens.
- **Dateien:** `web/logging_setup.py`, `web/app.py` (`access_log`)
- **Prüfen:** `docker logs <container>`

**Kriterium 2: Health Check**

- **Umsetzung:** `/health` prüft die Datenbank (200 oder 503), das Dockerfile nutzt den Endpunkt als `HEALTHCHECK`.
- **Dateien:** `web/app.py` (`health`), `Dockerfile`
- **Prüfen:** `docker ps` zeigt `(healthy)`

---

## Feld 5 – Dynamisches Testing

**Kriterium 1: Automatisierte Tests, die bei fehlerhaften Änderungen scheitern**

- **Umsetzung:** 11 pytest-Tests laufen in der CI. Ein Skript baut 6 typische Sicherheitsfehler ein und zeigt, dass jeweils ein Test scheitert.
- **Dateien:** `web/testapi.py`, `scripts/mutation_demo.py`, [docs/testing.md](testing.md)
- **Prüfen:** `pytest` und `python scripts/mutation_demo.py`

---

## Dokumentation

- **Überblick, Bedienung, Endpunkte:** [README.md](../README.md)
- **Schutzkonzept nach den fünf Feldern:** [SCHUTZKONZEPT.md](../SCHUTZKONZEPT.md)
- **Kurzbeschreibung aus der Projektanmeldung:** [docs/projektanmeldung.md](projektanmeldung.md)

## Alles lokal prüfen

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install --require-hashes -r web/requirements-dev.txt

mypy
bandit -c pyproject.toml -r web/app.py web/logging_setup.py
pytest
pip-audit --strict --require-hashes --disable-pip -r requirements.txt
./security_examples/run_positive_tests.sh   # braucht gitleaks
python scripts/mutation_demo.py
./build.sh --smoke                          # braucht Docker
```

<!-- ======== CHECKLISTE: vor der Abgabe von hier bis "ENDE CHECKLISTE" löschen ======== -->

---

## Checkliste bis zur Abgabe

> [!IMPORTANT]
> Dieser Abschnitt wird vor der Abgabe gelöscht.
> Stand: 22.11.2026, Branch `michelletest`. Abhaken: `[ ]` zu `[x]` ändern, oder auf GitHub direkt das Kästchen anklicken.

### Im Repository: erledigt

- [x] Feld 1: Dockerfile, `build.sh`, `docs/building.md` (Vertiefungs-Behauptung entfernt)
- [x] Feld 2: Pydantic, mypy, bandit, gitleaks, Positivtests
- [x] Feld 2: Middleware-Fix in `web/app.py`
- [x] Feld 2: `docs/datenfluss.md` mit korrigierter Reihenfolge
- [x] Feld 3: `requirements.txt` mit korrekten Hashes, `anyio` und `idna` ohne bekannte Lücken
- [x] Feld 3: `web/requirements-dev.txt` mit Hashes
- [x] Feld 3: `ci.yml` installiert hash-verifiziert, ohne ungepinntes `pip install --upgrade pip`
- [x] Feld 3: Schwachstellen-Scan mit pip-audit in `ci.yml`, auch wöchentlich
- [x] Feld 3: Basis-Image mit Digest, kein `curl` per `apt-get`
- [x] Feld 3: SBOM in `build-deploy.yml`, `dependabot.yml`, `docs/supply-chain.md`
- [x] Feld 4: JSON-Logs und Health Check, kein toter Verweis mehr in `logging_setup.py`
- [x] Feld 5: `scripts/mutation_demo.py`, `docs/testing.md`
- [x] `SCHUTZKONZEPT.md`, README im Root, Kurzbeschreibung in `docs/projektanmeldung.md`

### Lokal prüfen (siehe [Alles lokal prüfen](#alles-lokal-prüfen))

- [ ] `mypy`, `bandit`, `pytest`, `pip-audit` grün
- [ ] `python scripts/mutation_demo.py` meldet „Alle 6 Fehler erkannt“
- [ ] `./security_examples/run_positive_tests.sh` meldet „Alle Positivtests erfolgreich“
- [ ] `./build.sh --smoke` meldet „OK“ (braucht Docker)

### Auf GitHub

- [ ] Team hat `michelletest` angeschaut und ist einverstanden
- [ ] Pull Request `michelletest` → `feature/codesecurity` (oder direkt → `main`) öffnen, alle Checks grün
- [ ] Nachweis Feld 5: PR mit absichtlichem Fehler öffnen (z. B. `if False:` in `ensure_can_modify`), roten CI-Lauf in `docs/testing.md` statt `<hier eintragen>` verlinken, PR schließen ohne Merge
- [ ] Nach `main` mergen. Erst dann sieht der Dozent alles. Dependabot und der wöchentliche Scan lesen ihre Konfiguration nur vom Standard-Branch `main` und wirken vorher nicht
- [ ] Nach dem ersten Lauf von „Build & Publish“: SBOM unter *Artifacts* vorhanden. Artefakte verfallen nach 90 Tagen, für die Präsentation einmal herunterladen
- [ ] GHCR-Paket auf *public* stellen (*Packages → Paket → Package settings → Change visibility*)
- [ ] *Settings → Code security*: Dependabot alerts und security updates einschalten
- [ ] Erster Dependabot-PR erschienen (oder über *Insights → Dependency graph → Dependabot → Check for updates* auslösen)
- [ ] Optional: alte Branches `develop`, `feature/building`, `michelletest` nach dem Merge löschen

### Präsentation (15–20 Minuten, jedes Teammitglied trägt bei)

- [ ] Aufteilen, wer was vorstellt
- [ ] Anwendung und Angriffsfläche (STRIDE-Tabelle aus dem Schutzkonzept)
- [ ] Überblick über alle fünf Felder (Tabelle oben auf dieser Seite)
- [ ] Vertiefung Feld 2 mit Positivtests, live oder als Screenshot
- [ ] Vertiefung Feld 3: Pinning, SBOM, pip-audit (echter Fund `anyio`/`idna`), Dependabot-PR
- [ ] Restrisiken und nächste Schritte (aus dem Schutzkonzept)
- [ ] Nachweise vorab öffnen: grüner CI-Lauf, roter CI-Lauf (Feld 5), SBOM-Artefakt

### Abgabe

- [ ] Eine Woche vor der Präsentation: Vertiefungen (Feld 2 und 3) und Repo-Link an den Dozenten
- [ ] Diese Checkliste löschen

<!-- ======== ENDE CHECKLISTE ======== -->