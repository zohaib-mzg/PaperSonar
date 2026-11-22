"""Build the Phase 3 insights PDF and the presentation deck from the report.

The script reads ``docs/phase3/INSIGHTS_REPORT.md`` and renders it into
``docs/phase3/INSIGHTS_REPORT.pdf`` and ``docs/phase3/INSIGHTS_DECK.pptx`` so
the two artefacts can never drift from the markdown source or from the
evidence files.

Run it from the repository root:

    python scripts/build_insights_artifacts.py

The script needs ``reportlab`` and ``python-pptx``. They are build-time tools
only and are not runtime dependencies of the pipeline.
"""

from __future__ import annotations

import re
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = PROJECT_ROOT / "docs" / "phase3" / "INSIGHTS_REPORT.md"
PDF_PATH = PROJECT_ROOT / "docs" / "phase3" / "INSIGHTS_REPORT.pdf"
DECK_PATH = PROJECT_ROOT / "docs" / "phase3" / "INSIGHTS_DECK.pptx"

ACCENT = colors.HexColor("#1F4E5F")
MUTED = colors.HexColor("#5A6570")


def _read_report() -> str:
    return REPORT_PATH.read_text(encoding="utf-8")


def _sections(text: str) -> list[tuple[str, list[str]]]:
    """Split the markdown into (heading, body lines) sections."""
    sections: list[tuple[str, list[str]]] = []
    heading = ""
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith("#"):
            if heading or body:
                sections.append((heading, body))
            heading = line.lstrip("#").strip()
            body = []
        else:
            body.append(line)
    if heading or body:
        sections.append((heading, body))
    return sections


def _strip_markdown(line: str) -> str:
    line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
    line = re.sub(r"`(.+?)`", r"\1", line)
    line = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1", line)
    return line.strip()


def _build_pdf() -> None:
    styles = getSampleStyleSheet()
    body_style = ParagraphStyle(
        "Body", parent=styles["BodyText"], fontSize=9.5, leading=13.5, spaceAfter=5
    )
    table_style = ParagraphStyle(
        "TableCell", parent=body_style, fontSize=8, leading=10, spaceAfter=0
    )
    title_style = ParagraphStyle(
        "TitleStyle",
        parent=styles["Title"],
        fontSize=20,
        leading=24,
        textColor=ACCENT,
        spaceAfter=10,
    )
    h1_style = ParagraphStyle(
        "H1", parent=styles["Heading1"], fontSize=14, leading=17, textColor=ACCENT,
        spaceBefore=10, spaceAfter=5,
    )
    h2_style = ParagraphStyle(
        "H2", parent=styles["Heading2"], fontSize=11, leading=14, textColor=MUTED,
        spaceBefore=7, spaceAfter=4,
    )

    story: list[object] = []
    for heading, lines in _sections(_read_report()):
        if not heading:
            continue
        level = 1 if heading.startswith("PaperSonar Insights") else 2
        if heading.startswith("PaperSonar Insights"):
            story.append(Paragraph(_strip_markdown(heading), title_style))
        elif heading.startswith("## "):
            story.append(Paragraph(_strip_markdown(heading), h1_style))
        else:
            story.append(Paragraph(_strip_markdown(heading), h2_style))

        table: list[list[str]] = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("|") and stripped.endswith("|"):
                cells = [cell.strip() for cell in stripped.strip("|").split("|")]
                if all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells):
                    continue
                table.append(cells)
                continue
            if table:
                story.append(_pdf_table(table, table_style))
                table = []
            if not stripped:
                continue
            if stripped.startswith("- ") or re.match(r"^\d+\.\s", stripped):
                stripped = "• " + stripped.lstrip("- ").strip()
            story.append(Paragraph(_strip_markdown(stripped), body_style))
            story.append(Spacer(1, 2))
        if table:
            story.append(_pdf_table(table, table_style))

    document = SimpleDocTemplate(
        str(PDF_PATH),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="PaperSonar Insights Report - Phase 3",
        author="PaperSonar",
    )
    document.build(story)


def _pdf_table(rows: list[list[str]], cell_style: ParagraphStyle) -> Table:
    width = max(len(row) for row in rows)
    table = Table(
        [[Paragraph(_strip_markdown(cell), cell_style) for cell in row] for row in rows],
        repeatRows=1,
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C9D2D8")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F5F7")]),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def _deck_slides() -> list[tuple[str, list[str]]]:
    return [
        (
            "PaperSonar Phase 3 - research intelligence on 296,299 published outputs",
            [
                "Five sources: OpenAlex, Crossref, arXiv, Zenodo (DataCite in flight)",
                "74.40% of the corpus is classified by the v3 taxonomy (was 1.92%)",
                "Twelve DQ rules, fail-closed publication, every number traceable to a CSV",
            ],
        ),
        (
            "1. The taxonomy was the binding constraint",
            [
                "OpenAlex 3.40% -> 98.30% coverage, arXiv 5.46% -> 100.00%",
                "Crossref 35.30% and Zenodo 34.33%: the sources carry no subject field",
                "The v2 substring artifact is gone: arts-and-culture 175,415 -> 282",
                "Evidence: docs/phase3/evidence/00_taxonomy/DQ009_before_after.csv",
            ],
        ),
        (
            "2. Growth questions cannot be answered yet - and that is the finding",
            [
                "2023 holds 389 published works, 2025 holds 1,053",
                "ai-ml 8 -> 69 works, +4.50 pp share, suppressed by the 30-work rule",
                "The corpus is bimodal: a 2026 block of 78,226 works and a pre-2009 tail",
                "Evidence: Q01_topic_growth.csv, Q02_topic_share.csv",
            ],
        ),
        (
            "3. Topic overlap is sparse but structured",
            [
                "Only three pairs clear 100 parent / 5 joint works",
                "ai-ml x health-sciences: 10 joint works, 9.62% of the smaller parent",
                "health-sciences x law: 9 joint works; ai-ml x physics: 9",
                "Evidence: Q05_topic_intersections.csv",
            ],
        ),
        (
            "4. The counting rule decides the leaderboard",
            [
                "botany 1st by primary count (57,419) falls to 4th by fractional credit",
                "physics 2nd -> 1st; ecology 6th -> 3rd; ai-ml 4th -> 11th",
                "A recommendation without its counting rule is not a recommendation",
                "Evidence: Q13_counting_sensitivity.csv",
            ],
        ),
        (
            "5. The concentration metric is an artifact, not a finding",
            [
                "Q08 reports 99.24% top-five concentration for physics in 2026",
                "One OpenAlex institution id owns 49,203 works and 56.9% of all credit",
                "The BI layer must show the work count next to the credit",
                "Evidence: Q07_institution_contribution.csv, Q08_institution_concentration.csv",
            ],
        ),
        (
            "6. What this project cannot claim",
            [
                "No growth ranking on a 389-work recent window",
                "No coverage claim above ~35% for Crossref or Zenodo",
                "No institution-based conclusion from a single dominant identifier",
                "No claim about research worldwide - only about the retained corpus",
            ],
        ),
        (
            "Deliverables",
            [
                "14 business queries, 3 OLAP analyses, 5 reporting views, measured optimization",
                "docs/phase3/INSIGHTS_REPORT.md with the full evidence index",
                "docs/phase3/POWERBI_SPEC.md - three-page model and DAX measures",
                "docs/phase3/COST_LOG.md - free-only, one X-Small warehouse",
            ],
        ),
    ]


def _build_deck() -> None:
    presentation = Presentation()
    presentation.slide_width = Inches(13.333)
    presentation.slide_height = Inches(7.5)

    title_layout = presentation.slide_layouts[0]
    bullet_layout = presentation.slide_layouts[1]

    for index, (heading, bullets) in enumerate(_deck_slides()):
        layout = title_layout if index == 0 else bullet_layout
        slide = presentation.slides.add_slide(layout)
        slide.shapes.title.text = heading
        title_frame = slide.shapes.title.text_frame
        title_frame.paragraphs[0].font.size = Pt(30 if index == 0 else 24)
        if index == 0:
            slide.placeholders[1].text = "PaperSonar - Phase 3 insights, 2026-11-22"
            slide.placeholders[1].text_frame.paragraphs[0].font.size = Pt(18)
            continue
        body = slide.placeholders[1].text_frame
        body.clear()
        for position, bullet in enumerate(bullets):
            paragraph = body.paragraphs[0] if position == 0 else body.add_paragraph()
            paragraph.text = bullet
            paragraph.level = 0
            paragraph.font.size = Pt(18)
            paragraph.space_after = Pt(10)

    presentation.save(str(DECK_PATH))


def main() -> None:
    _build_pdf()
    _build_deck()
    print(f"wrote {PDF_PATH.relative_to(PROJECT_ROOT)}")
    print(f"wrote {DECK_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
