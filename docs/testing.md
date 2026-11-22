# Feld 5 – Dynamisches Testing

**Erfülltes Kriterium:** 1. Automatisierte Anwendungstests prüfen bei jeder Codeänderung die korrekte Funktion und scheitern nachweislich bei einer fehlerhaften Änderung.

## Was getestet wird

`web/testapi.py` enthält 11 Tests. Sie starten die echte App mit einer frischen SQLite-Datei und schicken HTTP-Requests über den FastAPI-`TestClient`. Geprüft werden Authentifizierung, Sichtbarkeit privater Notizen, Rollenrechte, Eigentümerprüfung, Suche mit Platzhaltern, Token-Scopes und -Widerruf, Herabstufung, Deaktivierung und der Schutz des letzten Admins.

**Automatisierung:** `.github/workflows/ci.yml`, Schritt „Tests (pytest)“, bei jedem Push auf `main`/`develop` und bei jedem Pull Request.

## Nachweis: Tests scheitern bei fehlerhaften Änderungen

`scripts/mutation_demo.py` baut nacheinander 6 typische Sicherheitsfehler in eine Kopie von `web/app.py` ein und lässt jedes Mal alle Tests laufen. Bemerkt kein Test den Fehler, endet das Skript mit Exit 1.

Ergebnis eines echten Laufs (2026-11-21):

```text
Ausgangslage: alle Tests grün.

[1] ERKANNT    Eigentümerprüfung beim Ändern/Löschen entfernt
       scheiternde Tests: test_fremde_notiz_nicht_aenderbar
[2] ERKANNT    Token-Scopes nicht mehr mit aktueller Rolle geschnitten
       scheiternde Tests: test_herabstufung_wirkt_sofort
[3] ERKANNT    Sichtbarkeitsfilter in der Notizliste entfernt
       scheiternde Tests: test_sichtbarkeit_von_notizen
[4] ERKANNT    LIKE-Platzhalter in der Suche nicht mehr maskiert
       scheiternde Tests: test_suche_behandelt_platzhalter_woertlich
[5] ERKANNT    Login prüft das Passwort nicht mehr
       scheiternde Tests: test_fehlgeschlagener_login_wird_protokolliert
[6] ERKANNT    Deaktivierung widerruft keine Tokens mehr
       scheiternde Tests: test_deaktivierung_entzieht_tokens

Alle 6 Fehler erkannt: Die Tests scheitern bei jeder dieser fehlerhaften Änderungen.
```

**Nachweis in GitHub:** ein Pull Request, der in `ensure_can_modify` die Bedingung durch `if False:` ersetzt. Die CI wird rot. Link zum roten Lauf: `<hier eintragen>`.

## Lokal ausführen

```bash
pip install --require-hashes -r web/requirements-dev.txt
pytest                              # 11 Tests, erwartet: alle grün
python scripts/mutation_demo.py     # erwartet: "Alle 6 Fehler erkannt", Exit 0
```
