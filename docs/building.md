# Feld 1 – Building von Artefakten

## Erfülltes Kriterium

Gewählt wurde **Kriterium 2** (ein Skript führt Build/Packaging maschinell durch, die Nutzung ist dokumentiert) sowie die **Vertiefung** (ein Merge in den Deployment-Branch baut und veröffentlicht das Artefakt automatisiert).

## Gewähltes Artefakt und Begründung

Als Build-Artefakt wird ein **Container-Image** (Docker) erzeugt. 

## Wie das Artefakt gebaut wird

### Dockerfile

Das `Dockerfile` ist **mehrstufig** aufgebaut:

1. Die **Build-Stufe** legt eine virtuelle Umgebung an und installiert die Abhängigkeiten ausschließlich aus der mit gepinnten `requirements.txt`.
2. Die **Laufzeit-Stufe** kopiert nur die fertige venv und den Anwendungscode in ein schlankes `python:3.12-slim`-Image. Build-Werkzeuge bleiben zurück, das Image wird kleiner und die Angriffsfläche geringer.

Sicherheitsrelevante Entscheidungen im Dockerfile (sichere Defaults):

- Die Anwendung läuft als **unprivilegierter Nutzer** `appuser` (UID 10001), nicht als root.
- Das Datenverzeichnis `/data` ist ein **Volume** und gehört dem unprivilegierten Nutzer; die SQLite-Datei liegt außerhalb des Images.
- Ein **HEALTHCHECK** prüft periodisch den `/health`-Endpunkt, sodass Docker/Orchestrierung einen ungesunden Container erkennt.
- Das Admin-Passwort wird **zur Laufzeit** als Umgebungsvariable übergeben und nie ins Image gebacken.
- Das Basis-Image ist mit Tag gepinnt; für die vollständige Immer-Pflicht aus Feld 3 ist der Digest (`@sha256:…`) einzutragen – die Anleitung dazu steht als Kommentar im `Dockerfile`.

### Build-Skript

`build.sh` führt den Build maschinell durch und ist dokumentiert (Kopf des Skripts und hier):

```bash
./build.sh                 # baut  notizen-api:<kurzer-commit>  und  notizen-api:latest
./build.sh --smoke         # baut und startet den Container kurz zum Funktionstest
IMAGE=ghcr.io/<org>/notizen-api ./build.sh   # eigenen Namen/Registry setzen
```

Das Skript taggt das Image mit dem kurzen Git-Commit (nachvollziehbare Herkunft) und zusätzlich mit `latest`. Mit `--smoke` startet es den Container und pollt `/health`; antwortet der Endpunkt, ist bewiesen, dass das Image lauffähig ist – andernfalls endet das Skript mit Fehlercode und gibt die Container-Logs aus.

## Vertiefung: automatisches Veröffentlichen bei Merge

Der Workflow `.github/workflows/build-deploy.yml` löst bei einem **Push/Merge nach `main`** (dem Deployment-Branch) aus und

1. meldet sich mit dem automatisch bereitgestellten `GITHUB_TOKEN` an der **GitHub Container Registry (GHCR)** an,
2. bestimmt die Tags (kurzer Commit-SHA sowie `latest` auf dem Default-Branch),
3. baut das Image und **pusht** es nach `ghcr.io/<org>/notizen-api`.

Das veröffentlichte Image ist **direkt installier- und ausführbar**, ohne erneuten Build:

```bash
docker run -d -p 8000:8000 \
  -e ADMIN_PASSWORD='ein-langes-passwort' \
  -v notes-data:/data \
  ghcr.io/<org>/notizen-api:latest
```

Alle verwendeten Actions sind mit Commit-SHA gepinnt (Kommentar nennt den zugehörigen Release-Tag), passend zur Supply-Chain-Linie aus Feld 3.

## Was in der Präsentation gezeigt wird

Die Aufgabe verlangt für Feld 1 ein erfolgreiches Build und eine erfolgreiche Ausführung. Vorführbar sind zwei Wege:

- **Lokal:** `./build.sh --smoke` – baut das Image und zeigt, dass `/health` antwortet.
- **Automatisiert:** ein Merge nach `main`, der den `Build & Publish`-Workflow grün durchlaufen lässt, anschließend `docker run … ghcr.io/<org>/notizen-api:latest` und ein Aufruf von `/health` bzw. `/docs`.

## Nachweise (Pfade)

- `Dockerfile` – Definition des Artefakts
- `.dockerignore` – schlanker, sauberer Build-Kontext (keine Caches/Secrets/Demo-Code im Image)
- `build.sh` – maschinelles Build-Skript inkl. Smoke-Test
- `.github/workflows/build-deploy.yml` – automatisiertes Bauen und Veröffentlichen nach GHCR
- CI-Lauf des Workflows `Build & Publish` sowie das Paket unter „Packages" des Repositories (nach dem ersten erfolgreichen Push)

## Risiko-Einordnung

**Mitigiert:** Das Artefakt ist reproduzierbar und trägt über den Commit-Tag eine nachvollziehbare Herkunft; durch Hash-verifizierte Abhängigkeiten enthält es exakt die geprüften Pakete; der non-root-Betrieb und das ausgelagerte Datenvolume verringern die Auswirkung einer Kompromittierung.

**Verbleibend:** Das Image wird derzeit nicht signiert (z. B. mit cosign) und nicht nach dem Bau auf Image-Ebene auf Schwachstellen gescannt (z. B. Trivy/Grype). Beides wären die nächsten sinnvollen Schritte, um die Lieferkette bis zum veröffentlichten Image zu schließen.