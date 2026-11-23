# Feld 3 – Build & Supply Chain (Vertiefung)

Alle vier Kriterien sind erfüllt. Pro Kriterium steht hier, was umgesetzt ist, wo der Nachweis liegt und wie man es lokal reproduziert.

**Risiko:** Ein Angreifer greift nicht unseren Code an, sondern etwas, dem wir vertrauen: ein PyPI-Paket, das Basis-Image oder eine GitHub Action (Folie 160). Dazu kommen bekannte Schwachstellen in Abhängigkeiten, die niemand bemerkt.

## 1. Pinning mit Release-Tag und Prüfsumme (Immer-Pflicht)

| Was | Wie gepinnt | Datei |
|---|---|---|
| Python-Laufzeitpakete (direkt und transitiv) | `paket==version` + `--hash=sha256:…` | `requirements.txt` (aus `requirements.in`) |
| Python-Werkzeuge der CI (mypy, bandit, pytest, httpx, pip-audit) | wie oben, Laufzeitpakete in identischer Version | `web/requirements-dev.txt` (aus `web/requirements-dev.in`) |
| Basis-Image | `python:3.12-slim@sha256:<digest>` in beiden `FROM`-Zeilen | `Dockerfile` |
| GitHub Actions | 40-stelliger Commit-SHA + Kommentar `# vX.Y.Z` | `.github/workflows/*.yml` |
| Systempakete im Image | keine (Health Check per Python statt `curl`) | `Dockerfile` |

`pip install --require-hashes` bricht ab, wenn eine Datei nicht exakt dem geprüften Stand entspricht. Ein Digest lässt sich im Gegensatz zu einem Tag nicht umbiegen (Folie 164–166).

**Lokal reproduzieren:**
```bash
pip install --require-hashes -r web/requirements-dev.txt      # bricht bei jeder Abweichung ab
grep -n "^FROM" Dockerfile                                     # beide Zeilen mit @sha256:
grep -n "uses:" .github/workflows/*.yml                        # alle mit Commit-SHA
```

Lock-Dateien neu erzeugen (im Python-Image, damit die Auflösung zum Image passt):
```bash
docker run --rm -v "$PWD":/w -w /w python:3.12-slim sh -c "pip install -q pip-tools==7.7.0 && \
  pip-compile --strip-extras --allow-unsafe --generate-hashes --output-file=requirements.txt requirements.in && \
  cd web && pip-compile --strip-extras --allow-unsafe --generate-hashes --output-file=requirements-dev.txt requirements-dev.in"
```

## 2. SBOM (automatisch erzeugt)

**Werkzeug:** Syft über `anchore/sbom-action`, Format CycloneDX JSON (Folie 161–163).

**Wo:** `.github/workflows/build-deploy.yml`, Schritt „SBOM des veröffentlichten Images erzeugen“. Er läuft bei jedem Push nach `main`, direkt nach dem Push des Images.

Die SBOM entsteht aus dem fertigen Image. Sie enthält deshalb auch die Debian-Pakete des Basis-Images, nicht nur die Python-Pakete.

**Nachweis:** Jeder Lauf von `Build & Publish` → Abschnitt *Artifacts* → `sbom-notizen-api.cdx.json`.

**Lokal reproduzieren:**
```bash
docker build -t notizen-api:local .
syft notizen-api:local -o cyclonedx-json=sbom.cdx.json
```

## 3. Schwachstellen-Scan der Abhängigkeiten

**Werkzeug:** pip-audit gegen die PyPI/OSV-Schwachstellendatenbank.

**Wo:** `.github/workflows/ci.yml`, Schritt „Schwachstellen-Scan der Abhängigkeiten“. Geprüft werden `requirements.txt` und `web/requirements-dev.txt` bei jedem Push, jedem PR und zusätzlich jeden Montag. Der Zeitplan ist nötig, weil neue CVEs auch ohne Code-Änderung erscheinen. Jeder Fund lässt die CI fehlschlagen.

**Echter Fund bei der Einführung:** pip-audit meldete in den transitiven Abhängigkeiten `anyio` 4.11.0 (CVE-2026-63374, CVE-2026-64847) und `idna` 3.11 (CVE-2026-45409). Beide wurden mit `pip-compile --upgrade-package` auf 4.16.0 bzw. 3.20 angehoben.

**Lokal reproduzieren:**
```bash
pip-audit --strict --require-hashes --disable-pip -r requirements.txt   # erwartet: No known vulnerabilities found
```

## 4. Automatisierte Updates (Dependabot)

**Konfiguration:** `.github/dependabot.yml` (Folie 169):
- `pip` für `/` und `/web`: erkennt die pip-compile-Dateien und erzeugt die Lock-Dateien inklusive Hashes neu.
- `docker`: aktualisiert Tag und Digest des Basis-Images.
- `github-actions`: aktualisiert die Commit-SHAs.

**Abweichung vom Standard:** zwei `pip`-Einträge, weil die Lock-Dateien an zwei Orten liegen.

**On-demand auslösen:** *Insights → Dependency graph → Dependabot* → *Check for updates*. Zusätzlich in *Settings → Code security* die *Dependabot security updates* aktivieren.

**Nachweis:** Tab *Pull requests*, Autor `dependabot`. Jeder dieser PRs durchläuft automatisch die CI.
