from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from app.ai.constants import CLASS_LABELS_UK

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    sys.path.insert(0, str(SCRIPTS))
    try:
        spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module  # dataclasses need the module registered
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPTS))


def test_every_class_has_complete_texts_within_api_limits():
    texts = _load("clinical_texts").TEXTS
    assert set(texts) == set(CLASS_LABELS_UK)
    for code, t in texts.items():
        for field in ("location", "description", "assessment", "referral_reason", "lab_diagnosis", "lab_description"):
            assert getattr(t, field).strip(), (code, field)
        assert len(t.location) <= 200 and len(t.description) <= 5000 and len(t.referral_reason) <= 2000
        assert len(t.lab_diagnosis) <= 2000 and len(t.lab_description) <= 10000
        assert "ШІ" not in t.lab_description and "AI" not in t.lab_diagnosis  # the lab part is independent


def test_demo_seed_uses_the_templates_for_every_patient():
    seed = _load("seed_demo")
    texts = _load("clinical_texts").TEXTS
    assert {p[5] for p in seed.PATIENTS} <= set(texts)
    assert all(len(p) == 6 and p[2] for p in seed.PATIENTS)  # with по батькові


def test_clinical_texts_do_not_mention_ai_or_patient_talks():
    import re

    banned = re.compile(r"ШІ|\bAI\b|штучн|модел|обговорено|поінформ", re.IGNORECASE)
    for code, t in _load("clinical_texts").TEXTS.items():
        for field in (
            "description",
            "assessment",
            "referral_reason",
            "lab_diagnosis",
            "lab_description",
            "lab_comment",
        ):
            assert not banned.search(getattr(t, field)), (code, field)
