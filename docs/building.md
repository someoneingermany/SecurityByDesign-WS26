# Feld 1 – Building von Artefakten

## Erfülltes Kriterium

Gewählt wurde **Kriterium 2**: Ein Skript führt Build und Packaging maschinell durch, die Nutzung ist dokumentiert. Zusätzlich veröffentlicht ein Merge nach `main` das Image automatisch. Das zählt nicht als Vertiefung, unsere zwei Vertiefungen sind Feld 2 und Feld 3.

## Gewähltes Artefakt und Begründung

Als Build-Artefakt entsteht ein Container-Image (Docker).

## Wie das Artefakt gebaut wird

### Dockerfile

Das `Dockerfile` hat zwei Stufen:

1. Die **Build-Stufe** legt eine virtuelle Umgebung an und installiert die Abhängigkeiten ausschließlich aus der mit Hashes gepinnten `requirements.txt`.
2. Die **Laufzeit-Stufe** kopiert nur die fertige venv und den Anwendungscode in ein schlankes `python:3.12-slim`-Image. Build-Werkzeuge bleiben zurück. Das macht das Image kleiner und verringert die Angriffsfläche.

Sicherheitsrelevante Entscheidungen im Dockerfile (sichere Defaults):

- Die Anwendung läuft als unprivilegierter Nutzer `appuser` (UID 10001), nicht als root.
- Das Datenverzeichnis `/data` ist ein Volume und gehört diesem Nutzer. Die SQLite-Datei liegt also außerhalb des Images.
- Ein `HEALTHCHECK` fragt regelmäßig den Endpunkt `/health` ab, damit Docker oder eine Orchestrierung einen ungesunden Container erkennt. Er nutzt Python statt `curl`, damit kein ungepinntes Systempaket per `apt-get` ins Image kommt.
- Das Admin-Passwort kommt erst zur Laufzeit als Umgebungsvariable hinzu und steckt nie im Image.
- Das Basis-Image ist mit Tag und Digest gepinnt (`python:3.12-slim@sha256:…`) und erfüllt damit die Immer-Pflicht aus Feld 3. Dependabot hält den Digest aktuell.

### Abhängigkeiten (`requirements.in` → `requirements.txt`)

Direkte Abhängigkeiten stehen in `requirements.in`. Daraus erzeugt pip-compile die `requirements.txt` mit dem vollständigen Abhängigkeitsbaum und SHA-256-Hashes für alle Plattformen (u. a. x86_64 und arm64). `pip install --require-hashes` bricht ab, wenn ein Paket nicht gepinnt ist oder der Hash abweicht. Zum Aktualisieren:

```bash
docker run --rm -v "$PWD":/w -w /w python:3.12-slim sh -c \
  "pip install -q pip-tools==7.7.0 && pip-compile --generate-hashes --allow-unsafe --output-file=requirements.txt requirements.in"
```

Der Lauf im `python:3.12-slim`-Container stellt sicher, dass die Auflösung zur Python-Version des Images passt.

### Build-Skript

`build.sh` führt den Build maschinell durch und ist dokumentiert (Kopf des Skripts und hier):

```bash
./build.sh                 # baut  notizen-api:<kurzer-commit>  und  notizen-api:latest
./build.sh --smoke         # baut und startet den Container kurz zum Funktionstest
IMAGE=ghcr.io/someoneingermany/securitybydesign-ws26 ./build.sh   # eigenen Namen/Registry setzen
```

Das Skript taggt das Image mit dem kurzen Git-Commit, damit die Herkunft nachvollziehbar bleibt, und zusätzlich mit `latest`. Mit `--smoke` startet es den Container und fragt `/health` ab. Antwortet der Endpunkt, läuft das Image. Andernfalls endet das Skript mit Fehlercode und gibt die Container-Logs aus.

## Zusätzlich: automatisches Veröffentlichen bei Merge (keine Vertiefung)

Der Workflow `.github/workflows/build-deploy.yml` startet bei jedem Push oder Merge nach `main`, unserem Deployment-Branch. Er

1. meldet sich mit dem automatisch bereitgestellten `GITHUB_TOKEN` an der GitHub Container Registry (GHCR) an,
2. bestimmt die Tags (kurzer Commit-SHA sowie `latest` auf dem Default-Branch),
3. baut das Image und pusht es nach `ghcr.io/someoneingermany/securitybydesign-ws26` (Repository-Name in Kleinbuchstaben).

Das veröffentlichte Image lässt sich ohne erneuten Build direkt installieren und starten. Neue GHCR-Pakete sind allerdings privat. Nach dem ersten Push muss das Paket deshalb unter *Packages → Package settings → Change visibility* auf **public** gestellt werden, sonst ist vorher `docker login ghcr.io` nötig:

```bash
docker run -d -p 8000:8000 \
  -e ADMIN_PASSWORD='ein-langes-passwort' \
  -v notes-data:/data \
  ghcr.io/someoneingermany/securitybydesign-ws26:latest
```

Alle verwendeten Actions sind mit Commit-SHA gepinnt, der Kommentar dahinter nennt den Release-Tag. Das gehört zu den Supply-Chain-Maßnahmen aus Feld 3.

## Was in der Präsentation gezeigt wird

Für Feld 1 muss die Präsentation ein erfolgreiches Build und eine erfolgreiche Ausführung zeigen. Dafür gibt es zwei Wege:

- **Lokal:** `./build.sh --smoke` baut das Image und zeigt, dass `/health` antwortet.
- **Automatisiert:** Ein Merge nach `main` lässt den Workflow `Build & Publish` grün durchlaufen. Danach folgen `docker run … ghcr.io/someoneingermany/securitybydesign-ws26:latest` und ein Aufruf von `/health` oder `/docs`.

## Nachweise (Pfade)

- `requirements.in` / `requirements.txt`: direkte Abhängigkeiten bzw. der vollständig gepinnte Baum mit Hashes
- `Dockerfile`: Definition des Artefakts
- `.dockerignore`: hält Caches, Secrets und Demo-Code aus dem Build-Kontext
- `build.sh`: Build-Skript mit Smoke-Test
- `.github/workflows/build-deploy.yml`: baut und veröffentlicht automatisch nach GHCR
- der CI-Lauf des Workflows `Build & Publish` und, nach dem ersten erfolgreichen Push, das Paket unter „Packages“ im Repository

## Risiko-Einordnung

**Mitigiert:** Das Artefakt ist reproduzierbar, und der Commit-Tag zeigt, woher es stammt. Weil die Abhängigkeiten per Hash geprüft werden, enthält es genau die geprüften Pakete. Läuft der Container trotzdem kompromittiert, begrenzen der Betrieb ohne root und das ausgelagerte Datenvolume den Schaden.

**Verbleibend:** Das Image wird nicht signiert (z. B. mit cosign). Der Schwachstellen-Scan (pip-audit, siehe [supply-chain.md](supply-chain.md)) prüft die Python-Abhängigkeiten, nicht die Debian-Pakete des Basis-Images. Beides wären die nächsten sinnvollen Schritte.