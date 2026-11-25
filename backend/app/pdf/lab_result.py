from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from functools import cache
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

FONT_DIR = Path(__file__).parent / "fonts"
FONT, FONT_BOLD = "DejaVuSans", "DejaVuSans-Bold"
SYSTEM_NAME = "CutisAI"
TITLE = "Результат гістопатологічного дослідження"
TEMPLATE_VERSION = 5

ACCENT = colors.HexColor("#0b5f8a")
MUTED = colors.HexColor("#5b6672")
RULE = colors.HexColor("#d5dde5")
LABEL_WIDTH = 52 * mm


@dataclass(frozen=True)
class LabResultPdf:
    referral_number: str
    lab_accession_number: str
    examined_at: date
    approved_at: datetime  # aware, UTC
    patient_name: str
    patient_birth_date: date
    doctor_name: str
    lab_specialist_name: str
    diagnosis: str
    description: str
    comment: str | None
    referral_date: datetime  # aware, UTC
    timezone: str
    doctor_phone: str | None = None


@cache
def _register_fonts() -> None:
    pdfmetrics.registerFont(TTFont(FONT, str(FONT_DIR / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, str(FONT_DIR / "DejaVuSans-Bold.ttf")))
    pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=FONT_BOLD, italic=FONT, boldItalic=FONT_BOLD)


def _styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle("base", fontName=FONT, fontSize=10.5, leading=15, alignment=TA_LEFT)
    return {
        "base": base,
        "brand": ParagraphStyle("brand", parent=base, fontName=FONT_BOLD, fontSize=13, leading=16, textColor=ACCENT),
        "title": ParagraphStyle("title", parent=base, fontName=FONT_BOLD, fontSize=15, leading=19),
        "meta": ParagraphStyle("meta", parent=base, fontSize=9.5, leading=13, alignment=TA_RIGHT),
        "h2": ParagraphStyle(
            "h2", parent=base, fontName=FONT_BOLD, fontSize=11.5, leading=15, textColor=ACCENT, spaceAfter=4
        ),
        "label": ParagraphStyle("label", parent=base, fontSize=9.5, leading=14, textColor=MUTED),
        "strong": ParagraphStyle("strong", parent=base, fontName=FONT_BOLD),
    }


def _text(value: str) -> str:
    return escape(value.strip()).replace("\r\n", "\n").replace("\n", "<br/>")


def _rule(space: float = 8) -> HRFlowable:
    return HRFlowable(width="100%", thickness=0.5, color=RULE, spaceBefore=space, spaceAfter=space)


def _kv_table(rows: list[tuple[str, str]], s: dict[str, ParagraphStyle]) -> Table:
    table = Table(
        [[Paragraph(k, s["label"]), Paragraph(_text(v), s["base"])] for k, v in rows],
        colWidths=[LABEL_WIDTH, None],
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _block(title: str, body: list, s: dict[str, ParagraphStyle]) -> KeepTogether:
    return KeepTogether([Paragraph(title, s["h2"]), *body])


class _NumberedCanvas(Canvas):
    def __init__(self, *args, footer: str = "", **kwargs):
        super().__init__(*args, **kwargs)
        self._footer = footer
        self._pages: list[dict] = []

    def showPage(self):  # noqa: N802 (ReportLab API)
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._pages)
        left, right = 18 * mm, A4[0] - 18 * mm
        for state in self._pages:
            self.__dict__.update(state)
            self.setStrokeColor(RULE)
            self.setLineWidth(0.5)
            self.line(left, 14 * mm, right, 14 * mm)
            self.setFont(FONT, 8)
            self.setFillColor(MUTED)
            self.drawString(left, 10 * mm, self._footer)
            self.drawRightString(right, 10 * mm, f"Сторінка {self._pageNumber} з {total}")
            super().showPage()
        super().save()


def render(data: LabResultPdf) -> bytes:
    _register_fonts()
    s = _styles()
    tz = ZoneInfo(data.timezone)

    def dt(v: datetime) -> str:
        return v.astimezone(tz).strftime("%d.%m.%Y %H:%M")

    def d(v: date) -> str:
        return v.strftime("%d.%m.%Y")

    numbers = (
        f"Направлення: <b>{escape(data.referral_number)}</b><br/>"
        f"Дослідження: <b>{escape(data.lab_accession_number)}</b><br/>"
        f"Дата: <b>{d(data.examined_at)}</b>"
    )
    header = Table(
        [[Paragraph(SYSTEM_NAME, s["brand"]), Paragraph(numbers, s["meta"])]],
        colWidths=[None, 70 * mm],
    )
    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story: list = [
        header,
        Spacer(1, 6),
        Paragraph(TITLE, s["title"]),
        HRFlowable(width="100%", thickness=1.2, color=ACCENT, spaceBefore=6, spaceAfter=10),
        _block(
            "Пацієнт",
            [_kv_table([("ПІБ", data.patient_name), ("Дата народження", d(data.patient_birth_date))], s)],
            s,
        ),
        _rule(),
        _block(
            "Лікар, що направив",
            [
                _kv_table(
                    [
                        ("ПІБ", data.doctor_name),
                        *([("Телефон", data.doctor_phone)] if data.doctor_phone else []),
                        ("Дата направлення", dt(data.referral_date)),
                    ],
                    s,
                )
            ],
            s,
        ),
        _rule(),
        _block(
            "Лабораторний спеціаліст",
            [
                _kv_table(
                    [
                        ("ПІБ", data.lab_specialist_name),
                        ("Дата дослідження", d(data.examined_at)),
                        ("Дата затвердження", dt(data.approved_at)),
                    ],
                    s,
                )
            ],
            s,
        ),
        _rule(),
        _block("Висновок", [Paragraph(_text(data.diagnosis), s["strong"])], s),
        _rule(),
        Paragraph("Опис", s["h2"]),
        Paragraph(_text(data.description), s["base"]),
    ]
    if data.comment and data.comment.strip():
        story += [_rule(), _block("Коментар", [Paragraph(_text(data.comment), s["base"])], s)]

    buf = BytesIO()
    footer = f"{SYSTEM_NAME} · {data.referral_number}"
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=22 * mm,
        title=f"{TITLE} {data.referral_number}",
        author=SYSTEM_NAME,
        subject=TITLE,
        lang="uk-UA",
    )
    doc.build(story, canvasmaker=lambda *a, **kw: _NumberedCanvas(*a, footer=footer, **kw))
    return buf.getvalue()
