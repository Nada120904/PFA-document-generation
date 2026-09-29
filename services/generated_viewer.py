"""Open a generated file in the browser using its saved bytes."""

from __future__ import annotations

import csv
import html
from pathlib import Path

from fastapi.responses import FileResponse, HTMLResponse


def _page(filename: str, content: str) -> HTMLResponse:
    title = html.escape(filename)
    document = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#e9f0f2;color:#17323c;
font:15px/1.65 'Segoe UI',Arial,sans-serif}}main{{max-width:1080px;
min-height:78vh;margin:26px auto;padding:52px 64px;background:#fff;
box-shadow:0 12px 36px #173f4a1c;border-radius:8px}}h1{{font-size:31px;line-height:1.2;margin:0 0 14px;color:#15333e}}
h2{{font-size:20px;color:#00696f;margin:32px 0 10px}}h3{{font-size:17px;color:#15333e;margin:24px 0 4px}}
p{{margin:0 0 12px}}p.bullet{{padding-left:20px;position:relative}}p.bullet:before{{content:'•';position:absolute;left:2px;color:#00696f}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.7 Consolas,monospace;margin:0}}
table{{border-collapse:separate;border-spacing:0;width:100%;margin:14px 0 24px;font-size:14px}}
th,td{{border-bottom:1px solid #dce8e9;padding:11px 13px;text-align:left;vertical-align:top}}
th{{background:#e8f4f4;color:#154b52;font-weight:700;position:sticky;top:0}}
tr:nth-child(even) td{{background:#f7fafb}}.evidence-table{{table-layout:fixed}}
.evidence-table th:nth-child(1),.evidence-table td:nth-child(1){{width:7%}}
.evidence-table th:nth-child(2),.evidence-table td:nth-child(2){{width:16%}}
.evidence-table th:nth-child(3),.evidence-table td:nth-child(3){{width:19%}}
.evidence-table th:nth-child(4),.evidence-table td:nth-child(4){{width:10%}}
.evidence-table th:nth-child(5),.evidence-table td:nth-child(5){{width:48%}}
@media(max-width:700px){{main{{margin:0;padding:24px}}table{{font-size:12px}}th,td{{padding:8px}}}}
</style></head><body><main>{content}</main></body></html>"""
    return HTMLResponse(
        document,
        headers={"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'self'"},
    )


def open_generated_file(file_path: Path):
    """Return the real PDF, or a readable browser view parsed from the saved file."""
    filename = file_path.name
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        return FileResponse(
            file_path, media_type="application/pdf", filename=filename,
            content_disposition_type="inline",
        )
    if suffix == ".txt":
        body = f"<pre>{html.escape(file_path.read_text(encoding='utf-8'))}</pre>"
        return _page(filename, body)
    if suffix == ".csv":
        with file_path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))
        body = "<table class=\"evidence-table\">"
        for index, row in enumerate(rows):
            tag = "th" if index == 0 else "td"
            body += "<tr>" + "".join(f"<{tag}>{html.escape(cell)}</{tag}>" for cell in row) + "</tr>"
        body += "</table>"
        return _page(filename, body)
    if suffix == ".docx":
        from docx import Document
        from docx.oxml.table import CT_Tbl
        from docx.oxml.text.paragraph import CT_P
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        document = Document(file_path)
        parts: list[str] = []
        for block in document.element.body.iterchildren():
            if isinstance(block, CT_P):
                paragraph = Paragraph(block, document)
                if not paragraph.text.strip():
                    continue
                style = paragraph.style.name
                tag = "h1" if style == "Title" else "h2" if style == "Heading 1" else "h3" if style == "Heading 2" else "p"
                css = ' class="bullet"' if style.startswith("List Bullet") else ""
                parts.append(f"<{tag}{css}>{html.escape(paragraph.text)}</{tag}>")
            elif isinstance(block, CT_Tbl):
                table = Table(block, document)
                cells = []
                for index, row in enumerate(table.rows):
                    tag = "th" if index == 0 else "td"
                    cells.append("<tr>" + "".join(f"<{tag}>{html.escape(cell.text)}</{tag}>" for cell in row.cells) + "</tr>")
                parts.append("<table>" + "".join(cells) + "</table>")
        return _page(filename, "".join(parts))
    raise ValueError(f"Unsupported generated file type: {suffix}")
