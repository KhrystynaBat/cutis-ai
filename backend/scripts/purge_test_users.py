from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.db.session import get_sessionmaker  # noqa: E402
from app.storage.local import LocalStorage  # noqa: E402

SETUP = """
CREATE TEMP TABLE pu AS SELECT id FROM users WHERE email LIKE :pattern ESCAPE '\\';
CREATE TEMP TABLE pp AS SELECT id FROM patients WHERE doctor_id IN (SELECT id FROM pu);
CREATE TEMP TABLE pc AS SELECT id FROM cases WHERE doctor_id IN (SELECT id FROM pu);
CREATE TEMP TABLE pr AS SELECT id FROM referrals WHERE case_id IN (SELECT id FROM pc);
CREATE TEMP TABLE pa AS SELECT id FROM ai_analyses WHERE case_id IN (SELECT id FROM pc);
"""
FOREIGN = {
    "referrals assigned to a test lab specialist": (
        "SELECT count(*) FROM referrals"
        " WHERE assigned_lab_specialist_id IN (SELECT id FROM pu) AND id NOT IN (SELECT id FROM pr)"
    ),
    "lab results written by a test lab specialist": (
        "SELECT count(*) FROM lab_results"
        " WHERE lab_specialist_id IN (SELECT id FROM pu) AND referral_id NOT IN (SELECT id FROM pr)"
    ),
}
FILES = """
SELECT storage_key FROM case_images WHERE case_id IN (SELECT id FROM pc)
UNION ALL SELECT storage_key FROM xai_artifacts
    WHERE storage_key IS NOT NULL AND analysis_id IN (SELECT id FROM pa)
UNION ALL SELECT pdf_storage_key FROM lab_results
    WHERE pdf_storage_key IS NOT NULL AND referral_id IN (SELECT id FROM pr)
"""
DELETES = [
    (
        "audit events",
        """DELETE FROM audit_events WHERE actor_user_id IN (SELECT id FROM pu) OR entity_id IN (
        SELECT id::text FROM pu UNION SELECT id::text FROM pp UNION SELECT id::text FROM pc
        UNION SELECT id::text FROM pr UNION SELECT id::text FROM pa)""",
    ),
    (
        "e-mails",
        "DELETE FROM email_outbox WHERE referral_id IN (SELECT id FROM pr) OR patient_id IN (SELECT id FROM pp)",
    ),
    (
        "notifications",
        "DELETE FROM notifications WHERE user_id IN (SELECT id FROM pu) OR referral_id IN (SELECT id FROM pr)",
    ),
    ("lab results", "DELETE FROM lab_results WHERE referral_id IN (SELECT id FROM pr)"),
    ("referrals", "DELETE FROM referrals WHERE id IN (SELECT id FROM pr)"),
    ("XAI maps", "DELETE FROM xai_artifacts WHERE analysis_id IN (SELECT id FROM pa)"),
    ("analyses", "DELETE FROM ai_analyses WHERE id IN (SELECT id FROM pa)"),
    ("photos", "DELETE FROM case_images WHERE case_id IN (SELECT id FROM pc)"),
    ("cases", "DELETE FROM cases WHERE id IN (SELECT id FROM pc)"),
    ("patients", "DELETE FROM patients WHERE id IN (SELECT id FROM pp)"),
    ("sessions", "DELETE FROM user_sessions WHERE user_id IN (SELECT id FROM pu)"),
    ("tokens", "DELETE FROM user_tokens WHERE user_id IN (SELECT id FROM pu)"),
    ("users", "DELETE FROM users WHERE id IN (SELECT id FROM pu)"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Remove test accounts and their data")
    ap.add_argument("--prefix", required=True, help="e-mail prefix, e.g. e2e- or qa-")
    ap.add_argument("--yes", action="store_true", help="really delete (default: dry run)")
    args = ap.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,30}", args.prefix):
        print("Префікс: латиниця, цифри, дефіс (напр. e2e-)", file=sys.stderr)
        return 2
    pattern = args.prefix.replace("_", "\\_") + "%@%.test"

    storage = LocalStorage(get_settings().storage_dir)
    with get_sessionmaker()() as db:
        for stmt in SETUP.strip().split(";\n"):
            db.execute(text(stmt), {"pattern": pattern})
        emails = db.scalars(text("SELECT email FROM users WHERE id IN (SELECT id FROM pu) ORDER BY email")).all()
        if not emails:
            print("Тестових акаунтів із таким префіксом немає.")
            return 0
        print("Акаунти:", ", ".join(emails))
        for label, q in FOREIGN.items():
            if n := db.scalar(text(q)):
                print(f"Зупинено: {label} в чужих записах ({n}). Нічого не видалено.", file=sys.stderr)
                return 1
        keys = db.scalars(text(FILES)).all()
        counts = []
        for label, q in DELETES:
            counts.append(f"{label}: {db.execute(text(q)).rowcount}")
        print("; ".join(counts) + f"; файлів: {len(keys)}")
        if not args.yes:
            db.rollback()
            print("Пробний запуск: нічого не змінено. Додайте --yes, щоб видалити.")
            return 0
        db.commit()
    removed = 0
    for key in keys:
        path = storage._path(key)
        if path.is_file():
            path.unlink()
            removed += 1
    print(f"Видалено. Файлів зі сховища: {removed}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
