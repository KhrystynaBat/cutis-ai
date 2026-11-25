from __future__ import annotations

import re
from collections.abc import Iterable
from functools import cache
from pathlib import Path

MIN_LENGTH = 12
MAX_LENGTH = 128
RUN = 4
_KEYBOARD_ROWS = (
    "1234567890",
    "qwertyuiop",
    "asdfghjkl",
    "zxcvbnm",
    "йцукенгшщзхї",
    "фівапролджє",
    "ячсмитьбю",
)
_ALPHABETS = ("abcdefghijklmnopqrstuvwxyz", "абвгґдеєжзиіїйклмнопрстуфхцчшщьюя", "0123456789")


@cache
def common_passwords() -> frozenset[str]:
    path = Path(__file__).with_name("common_passwords.txt")
    return frozenset(w.strip().lower() for w in path.read_text(encoding="utf-8").splitlines() if w.strip())


def _has_sequence(pw: str) -> bool:
    low = pw.lower()
    if re.search(rf"(.)\1{{{RUN - 1},}}", low):
        return True
    for seq in (*_KEYBOARD_ROWS, *_ALPHABETS):
        for line in (seq, seq[::-1]):
            for i in range(len(line) - RUN + 1):
                if line[i : i + RUN] in low:
                    return True
    return False


def _personal_parts(email: str | None, names: Iterable[str | None]) -> list[str]:
    parts = []
    if email:
        local = email.split("@")[0].lower()
        parts.append(local)
        parts += [p for p in re.split(r"[._\-+]", local) if p]
    parts += [n.strip().lower() for n in names if n and n.strip()]
    return [p for p in parts if len(p) >= 3]


def password_policy_errors(password: str, email: str | None = None, names: Iterable[str | None] = ()) -> list[str]:
    errors: list[str] = []
    if len(password) < MIN_LENGTH:
        errors.append(f"Пароль має містити щонайменше {MIN_LENGTH} символів")
    if len(password) > MAX_LENGTH:
        errors.append(f"Пароль має містити не більше {MAX_LENGTH} символів")
    if not any(c.islower() for c in password):
        errors.append("Додайте малу літеру")
    if not any(c.isupper() for c in password):
        errors.append("Додайте велику літеру")
    if not any(c.isdigit() for c in password):
        errors.append("Додайте цифру")
    if not any(not c.isalnum() and not c.isspace() for c in password):
        errors.append("Додайте спецсимвол (наприклад ! ? # - _ *)")
    low = password.lower()
    if any(p in low for p in _personal_parts(email, names)):
        errors.append("Пароль не може містити електронну пошту, ім'я чи прізвище")
    core = re.sub(r"^[\W\d_]+|[\W\d_]+$", "", low)
    if low in common_passwords() or (len(core) >= 4 and core in common_passwords()):
        errors.append("Це один із поширених паролів — оберіть інший")
    if _has_sequence(password):
        errors.append("Уникайте повторів і послідовностей (aaaa, 1234, qwerty)")
    return errors
