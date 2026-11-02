"""
ABSICHTLICH FEHLERHAFTER BEISPIELCODE – Positivtest für den Type Checker (mypy).

Erwarteter Fund: mypy meldet zwei Typfehler (arg-type und return-value).
"""


def add_days(days: int) -> int:
    return days + 1


add_days("30")  # arg-type: str statt int


def user_name(user_id: int) -> str:
    return user_id  # return-value: int statt str
