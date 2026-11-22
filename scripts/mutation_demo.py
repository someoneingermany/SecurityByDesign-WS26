#!/usr/bin/env python3
"""Mutationstest (Feld 5, Kriterium 1): "Zeigt, dass die Tests bei einer
fehlerhaften Änderung scheitern."

Baut nacheinander typische Sicherheitsfehler in eine KOPIE von web/app.py ein
und lässt jeweils die Testsuite laufen. Ein Fehler gilt als "erkannt", wenn
mindestens ein Test fehlschlägt. Bemerkt kein Test den Fehler, endet das Skript
mit Exit 1.

Nutzung:  python scripts/mutation_demo.py
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (Beschreibung, Originalcode, fehlerhafter Code)
MUTANTS = [
    ("Eigentümerprüfung beim Ändern/Löschen entfernt",
     'if row["owner_id"] != p.user_id and not is_admin(p):',
     "if False:"),
    ("Token-Scopes nicht mehr mit aktueller Rolle geschnitten",
     'scopes=set(row["scopes"].split(",")) & ROLE_SCOPES[row["role"]],',
     'scopes=set(row["scopes"].split(",")),'),
    ("Sichtbarkeitsfilter in der Notizliste entfernt",
     "if not is_admin(p):\n        sql += \" AND (n.owner_id = ? OR n.visibility = 'team')\"",
     "if False:\n        sql += \" AND (n.owner_id = ? OR n.visibility = 'team')\""),
    ("LIKE-Platzhalter in der Suche nicht mehr maskiert",
     'like = f"%{escape_like(q)}%"',
     'like = f"%{q}%"'),
    ("Login prüft das Passwort nicht mehr",
     'if user is None or not password_ok or not user["active"]:',
     'if user is None or not user["active"]:'),
    ("Deaktivierung widerruft keine Tokens mehr",
     "if not new_active:  # Deaktivierung entzieht sofort alle Tokens",
     "if False:"),
]


def run_tests(workdir: Path) -> tuple[int, list[str]]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-W", "ignore"],
        cwd=workdir, capture_output=True, text=True, timeout=300,
    )
    return proc.returncode, re.findall(r"FAILED \S+::(\w+)", proc.stdout)


def main() -> int:
    original = (ROOT / "web" / "app.py").read_text()
    survivors = 0
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        shutil.copytree(ROOT / "web", work / "web", ignore=shutil.ignore_patterns("__pycache__", "*.db"))
        shutil.copy(ROOT / "pyproject.toml", work / "pyproject.toml")
        target = work / "web" / "app.py"

        code, failed = run_tests(work)
        if code != 0:
            print(f"Ausgangslage FEHLERHAFT: Tests scheitern schon ohne Mutation: {failed}")
            return 1
        print("Ausgangslage: alle Tests grün.\n")

        for no, (desc, old, new) in enumerate(MUTANTS, 1):
            if original.count(old) != 1:
                print(f"[{no}] FEHLER: Codestelle für '{desc}' nicht eindeutig gefunden – Skript anpassen")
                return 1
            target.write_text(original.replace(old, new))
            code, failed = run_tests(work)
            if code != 0:
                print(f"[{no}] ERKANNT    {desc}\n       scheiternde Tests: {', '.join(failed)}")
            else:
                survivors += 1
                print(f"[{no}] ÜBERLEBT   {desc}\n       KEIN Test schlägt fehl – diese Regel ist ungetestet!")

    print()
    if survivors:
        print(f"{survivors} von {len(MUTANTS)} Fehlern blieben unbemerkt.")
        return 1
    print(f"Alle {len(MUTANTS)} Fehler erkannt: Die Tests scheitern bei jeder dieser fehlerhaften Änderungen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
