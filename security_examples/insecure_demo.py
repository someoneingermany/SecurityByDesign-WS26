"""
ABSICHTLICH UNSICHERER BEISPIELCODE – NICHT IN PRODUKTION VERWENDEN.

Dieser Code dient ausschließlich als Positivtest für die Sicherheitswerkzeuge
(Feld 2: Code Security). Er gehört NICHT in den Default-Branch-Deploy und wird
von der CI nur verwendet, um zu zeigen, dass die Scanner reale Probleme finden
und der Lauf dann fehlschlägt.

Erwartete Funde:
  * bandit  -> B105 (hartkodiertes Passwort), B602/B605 (Shell-Injection),
               B307 (Nutzung von eval)
  * gitleaks -> generischer API-Key / unsere nt_-Token-Regel
"""
import os
import subprocess

# --- Secret-Scanning-Trigger (gitleaks) --------------------------------------
# Echt aussehende, aber erfundene Secrets im Klartext im Code:
LEAKED_API_TOKEN = "nt_A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0U1v2"  # noqa
GITHUB_PAT = "ghp_1234567890abcdefGHIJKLMNopqrstuvWX12"  # noqa  (triggert Default-Regel)
GENERIC_API_KEY = "api_key = 'sk_live_51H8xQe2eZvKYlo2C0abcdEFghIJ'"  # noqa

# --- SAST-Trigger (bandit) ---------------------------------------------------
HARDCODED_PASSWORD = "SuperGeheim123!"  # B105


def run(cmd: str) -> None:
    # B602/B605: Shell-Injection durch shell=True mit String-Eingabe
    subprocess.call(cmd, shell=True)


def calculate(expr: str):
    # B307: eval auf nicht vertrauenswürdiger Eingabe
    return eval(expr)  # noqa


def read_secret() -> str:
    return os.environ.get("PASSWORD", HARDCODED_PASSWORD)
