import re
from pathlib import Path

import pytest

from app.core.config import Settings
from app.email import letters
from app.pdf import lab_result

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
FRONTEND = REPO / "frontend"

OLD_NAME = re.compile(r"дерма\s*лаб|derma\s*lab", re.IGNORECASE)
TECHNICAL = re.compile(
    r"@dermalab\.test|dermalab\.clinic2026@gmail\.com|getLogger\(\"dermalab[\w.]*\"\)"
    r"|postgresql\+psycopg://dermalab:dermalab@[\w.:]+/dermalab",
    re.IGNORECASE,
)


def _visible_hits(paths: list[Path]) -> list[str]:
    hits = []
    for path in paths:
        for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if OLD_NAME.search(TECHNICAL.sub("", line)):
                hits.append(f"{path.relative_to(REPO)}:{no}: {line.strip()}")
    return hits


def test_backend_texts_people_see_use_the_new_name():
    files = [
        BACKEND / "app/email/letters.py",
        BACKEND / "app/email/outbox.py",
        BACKEND / "app/main.py",
        BACKEND / "app/core/config.py",
        *sorted((BACKEND / "app/pdf").glob("*.py")),
        BACKEND / "app/services/lab_pdf.py",
    ]
    assert _visible_hits(files) == []


@pytest.mark.skipif(not (FRONTEND / "src").is_dir(), reason="frontend sources are not next to the backend")
def test_frontend_templates_and_texts_use_the_new_name():
    files = [
        p
        for ext in ("*.html", "*.ts", "*.scss")
        for p in (FRONTEND / "src").rglob(ext)
        if not p.name.endswith(".spec.ts")
    ] + [FRONTEND / "public/favicon.svg"]
    assert _visible_hits(files) == []
    assert "<title>CutisAI</title>" in (FRONTEND / "src/index.html").read_text(encoding="utf-8")


def test_name_constants():
    assert lab_result.SYSTEM_NAME == "CutisAI"
    assert letters.SIGNATURE == "З повагою,\nкоманда CutisAI"
    assert Settings.model_fields["smtp_from_name"].default == "CutisAI"


def test_every_letter_subject_and_signature_say_cutisai():
    letter = letters.TEST_LETTER
    assert letter.subject == "CutisAI: перевірка налаштувань пошти"
    assert "команда CutisAI" in letter.body and "команда CutisAI" in (letter.html or "")
    assert not OLD_NAME.search(letter.body + (letter.html or ""))
