"""PDF report generator using fpdf2."""

from __future__ import annotations

import logging
from pathlib import Path

from fpdf import FPDF, XPos, YPos

from ..models import AnalysisResult

logger = logging.getLogger(__name__)

# ── Colour palette ────────────────────────────────────────────────────────────
_HEADER_BG = (41, 65, 122)       # dark blue
_SECTION_BG = (240, 244, 255)    # light blue tint
_ACCENT = (220, 53, 69)          # red for breaking changes
_TEXT = (33, 37, 41)             # near-black
_SUBTEXT = (108, 117, 125)       # grey
_LINE = (206, 212, 218)          # light grey


class PDFReport(FPDF):
    def __init__(self, title: str) -> None:
        super().__init__()
        self._report_title = title
        self.set_auto_page_break(auto=True, margin=20)
        self.set_margins(left=15, top=15, right=15)

    # ── Page chrome ──────────────────────────────────────────────────────────

    def header(self) -> None:
        self.set_fill_color(*_HEADER_BG)
        self.rect(0, 0, self.w, 14, style="F")
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(255, 255, 255)
        self.set_y(3)
        self.cell(0, 8, "Git Diff Analyzer - Commit Analysis Report", align="L")
        self.ln(14)
        self.set_text_color(*_TEXT)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*_SUBTEXT)
        self.cell(0, 8, f"Page {self.page_no()}", align="C")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _section_title(self, text: str) -> None:
        self.set_fill_color(*_SECTION_BG)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(*_HEADER_BG)
        self.cell(0, 8, f"  {text}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        self.ln(2)
        self.set_text_color(*_TEXT)

    def _key_value(self, key: str, value: str) -> None:
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*_SUBTEXT)
        self.cell(38, 6, key + ":", new_x=XPos.RIGHT, new_y=YPos.LAST)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*_TEXT)
        self.multi_cell(0, 6, value, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def _body_text(self, text: str) -> None:
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*_TEXT)
        self.multi_cell(0, 6, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)

    def _code_block(self, code: str) -> None:
        """Render a monospaced code block with light grey background."""
        self.set_fill_color(245, 245, 245)
        self.set_draw_color(*_LINE)
        self.set_font("Courier", "", 8)
        self.set_text_color(30, 30, 30)
        # clip long lines
        lines = []
        for line in code.splitlines():
            while len(line) > 90:
                lines.append(line[:90])
                line = "  " + line[90:]
            lines.append(line)
        content = "\n".join(lines)
        self.multi_cell(0, 5, content, fill=True, border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(3)
        self.set_text_color(*_TEXT)

    def _divider(self) -> None:
        self.set_draw_color(*_LINE)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(3)

    def _badge(self, text: str, is_alert: bool = False) -> None:
        """Inline coloured badge."""
        if is_alert:
            self.set_fill_color(*_ACCENT)
            self.set_text_color(255, 255, 255)
        else:
            self.set_fill_color(40, 167, 69)
            self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 8)
        self.cell(0, 5, f" {text} ", new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        self.set_text_color(*_TEXT)
        self.ln(2)


def generate_pdf(result: AnalysisResult, output_path: Path) -> Path:
    """Generate a PDF report from an AnalysisResult and write it to output_path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    title = f"Analysis: {result.commit_hash[:12]}"
    pdf = PDFReport(title=title)
    pdf.add_page()

    # ── Title block ───────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*_HEADER_BG)
    pdf.cell(0, 10, "Commit Analysis Report", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(*_TEXT)
    pdf.ln(2)

    # ── Metadata ──────────────────────────────────────────────────────────────
    pdf._section_title("Commit Details")
    pdf._key_value("Commit", result.commit_hash)
    pdf._key_value("Author", result.author)
    pdf._key_value("Date", result.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC"))
    pdf._key_value("Message", result.commit_message)
    pdf._key_value("AI Model", f"{result.ai_provider}/{result.ai_model}")
    pdf._key_value("Analyzed", result.analyzed_at.strftime("%Y-%m-%d %H:%M:%S UTC"))
    pdf.ln(4)

    # ── Summary ───────────────────────────────────────────────────────────────
    pdf._section_title("Summary")
    pdf._body_text(result.summary or "No summary provided.")
    pdf.ln(2)

    # ── Impact assessment ─────────────────────────────────────────────────────
    pdf._section_title("Impact Assessment")
    pdf._body_text(result.impact_assessment or "No impact assessment provided.")
    pdf.ln(2)

    # ── Affected objects ──────────────────────────────────────────────────────
    pdf._section_title("Affected Objects")

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*_HEADER_BG)
    pdf.cell(0, 6, "Database Objects", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(*_TEXT)
    pdf.ln(1)

    if not result.affected_db_objects:
        pdf._body_text("No affected database objects detected.")
    else:
        col_w = [25, 65, 25, 65]
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(*_SECTION_BG)
        for header, w in zip(["Type", "Object", "Action", "Description"], col_w):
            pdf.cell(w, 6, header, border=1, fill=True)
        pdf.ln()
        pdf.set_font("Helvetica", "", 8)
        for obj in result.affected_db_objects:
            row_y = pdf.get_y()
            pdf.set_fill_color(255, 255, 255)
            pdf.cell(col_w[0], 6, obj.object_type, border=1)
            pdf.cell(col_w[1], 6, obj.object_name[:38], border=1)
            pdf.cell(col_w[2], 6, obj.action, border=1)
            # description may be long — truncate to fit
            pdf.cell(col_w[3], 6, obj.description[:38], border=1)
            pdf.ln()
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*_HEADER_BG)
    pdf.cell(0, 6, "Code Objects", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(*_TEXT)
    pdf.ln(1)

    if not result.affected_code_objects:
        pdf._body_text("No affected code objects detected.")
    else:
        col_w = [25, 65, 25, 65]
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(*_SECTION_BG)
        for header, w in zip(["Type", "Object", "Action", "Description"], col_w):
            pdf.cell(w, 6, header, border=1, fill=True)
        pdf.ln()
        pdf.set_font("Helvetica", "", 8)
        for obj in result.affected_code_objects:
            pdf.set_fill_color(255, 255, 255)
            pdf.cell(col_w[0], 6, obj.object_type, border=1)
            pdf.cell(col_w[1], 6, obj.object_name[:38], border=1)
            pdf.cell(col_w[2], 6, obj.action, border=1)
            pdf.cell(col_w[3], 6, obj.description[:38], border=1)
            pdf.ln()
    pdf.ln(2)

    # ── Schema changes ────────────────────────────────────────────────────────
    pdf._section_title(f"Schema Changes ({len(result.schema_changes)})")
    if not result.schema_changes:
        pdf._body_text("No schema changes detected.")
    else:
        for i, sc in enumerate(result.schema_changes, 1):
            pdf.set_font("Helvetica", "B", 10)
            label = f"[BREAKING] " if sc.is_breaking else ""
            pdf.cell(0, 6, f"{i}. {label}{sc.change_type} - {sc.table}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf._body_text(sc.description)
            if sc.migration_notes:
                pdf.set_font("Helvetica", "I", 9)
                pdf.set_text_color(*_SUBTEXT)
                pdf.multi_cell(0, 5, f"Notes: {sc.migration_notes}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.set_text_color(*_TEXT)
            pdf._code_block(sc.snowflake_sql)
            if i < len(result.schema_changes):
                pdf._divider()
    pdf.ln(2)

    # ── Data changes ──────────────────────────────────────────────────────────
    pdf._section_title(f"Data Changes ({len(result.data_changes)})")
    if not result.data_changes:
        pdf._body_text("No data changes detected.")
    else:
        for i, dc in enumerate(result.data_changes, 1):
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(0, 6, f"{i}. {dc.operation} - {dc.table}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf._body_text(dc.description)
            if dc.requires_ddl_first:
                pdf.set_font("Helvetica", "I", 9)
                pdf.set_text_color(*_ACCENT)
                dep = dc.depends_on_table or "see schema changes"
                pdf.multi_cell(0, 5, f"Requires DDL first (depends on: {dep})", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.set_text_color(*_TEXT)
            pdf._code_block(dc.snowflake_sql)
            if i < len(result.data_changes):
                pdf._divider()
    pdf.ln(2)

    # ── Recommendations ───────────────────────────────────────────────────────
    pdf._section_title(f"Recommendations ({len(result.recommendations)})")
    if not result.recommendations:
        pdf._body_text("No recommendations.")
    else:
        for rec in result.recommendations:
            priority_marker = {"high": "[HIGH]", "medium": "[MED]", "low": "[LOW]"}.get(
                rec.priority.lower(), f"[{rec.priority.upper()}]"
            )
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(18, 6, priority_marker, new_x=XPos.RIGHT, new_y=YPos.LAST)
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(*_SUBTEXT)
            pdf.cell(30, 6, rec.category + ":", new_x=XPos.RIGHT, new_y=YPos.LAST)
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(*_TEXT)
            pdf.multi_cell(0, 6, rec.text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    # ── Parse warning ─────────────────────────────────────────────────────────
    if result.parse_error:
        pdf._section_title("Analysis Warning")
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(*_ACCENT)
        pdf.multi_cell(0, 5, f"Warning: {result.parse_error}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(*_TEXT)

    pdf.output(str(output_path))
    logger.info("PDF written to %s", output_path)
    return output_path
