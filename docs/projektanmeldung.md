**Projekt**: „Notizen-API“ – eine kleine REST-API (Python, FastAPI, SQLite) zur Verwaltung von Notizen.

**Art**: Eigenentwicklung (Fallback-Web-API gemäß FAQ, kein Open-Source-Projekt).

**Anwendung**: Mehrere Endpunkte mit Pfad-, Query- und Body-Parametern. Benutzerkonten mit drei Rollen (viewer/editor/admin) und persönlichen API-Tokens mit eingeschränkten Scopes. Lese- und Schreibzugriffe auf eine SQLite-Datenbank. Schutzbedürftige Vorgänge: Login, Token-Erstellung/-Widerruf, Benutzer-/Rollenverwaltung, Löschen von Notizen, Audit-Log-Einsicht – jeweils durch Token und Rollen-Scopes geschützt. Input Validation über Pydantic, explizite Fehlerbehandlung, Audit-Logging.

**Geplante Vertiefungen**: Code Security und Build & Supply Chain