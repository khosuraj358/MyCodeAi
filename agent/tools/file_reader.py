"""
file_reader.py  —  Extract text/content from any file type for the agent.

Supported:
  Images  (.png .jpg .jpeg .gif .webp .bmp .svg)
    → Describe with gemma3:4b vision model via Ollama
  PDFs    (.pdf)
    → Extract text with pymupdf; fall back to image-per-page if scanned
  Office  (.docx .xlsx .pptx)
    → Extract text with python-docx / openpyxl
  Text    (.txt .md .csv .json .yaml .toml .xml .html .py .js .ts …)
    → Read directly (already handled by read_file tool)
"""

from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ── PDF extraction ────────────────────────────────────────────────────────────


def extract_pdf(path: str | Path, max_pages: int = 20) -> str:
    """
    Extract all text from a PDF. For scanned PDFs with no text layer,
    returns a summary of page count and suggests OCR.
    """
    try:
        import fitz  # pymupdf

        doc = fitz.open(str(path))
        total_pages = len(doc)
        pages_text: list[str] = []
        total = min(total_pages, max_pages)

        for i in range(total):
            page = doc[i]
            text = page.get_text("text").strip()
            if text:
                pages_text.append(f"--- Page {i+1} ---\n{text}")

        doc.close()

        if not pages_text:
            return (
                f"[PDF has {total_pages} pages but contains no extractable text. "
                "It may be a scanned image-only PDF. "
                "Please describe what you see in the document or provide a text version.]"
            )

        full = "\n\n".join(pages_text)
        if total_pages > max_pages:
            full += (
                f"\n\n[Showing {max_pages} of {total_pages} pages. Document truncated.]"
            )
        return full

    except ImportError:
        return "[PDF reading requires: pip install pymupdf]"
    except Exception as e:
        return f"[PDF read error: {e}]"


# ── Image to base64 ───────────────────────────────────────────────────────────


def image_to_base64(path: str | Path) -> tuple[str, str]:
    """
    Returns (base64_string, mime_type) for the image.
    Used to send images to Ollama's vision API.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }
    mime = mime_map.get(suffix, "image/png")

    with open(path, "rb") as f:
        raw = f.read()

    # Resize if huge (>4MB) to stay within Ollama's limits
    if len(raw) > 4_000_000:
        try:
            from PIL import Image

            img = Image.open(io.BytesIO(raw))
            img.thumbnail((1024, 1024))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            raw = buf.getvalue()
            mime = "image/png"
        except Exception:
            pass  # send as-is

    return base64.b64encode(raw).decode("utf-8"), mime


# ── Docx/Office extraction ────────────────────────────────────────────────────


def extract_docx(path: str | Path) -> str:
    try:
        from docx import Document

        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except ImportError:
        return "[DOCX reading requires: pip install python-docx]"
    except Exception as e:
        return f"[DOCX read error: {e}]"


def extract_xlsx(path: str | Path) -> str:
    try:
        import openpyxl

        wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
        parts: list[str] = []
        for sheet in wb.sheetnames:
            ws = wb[sheet]
            rows = []
            for row in ws.iter_rows(values_only=True, max_row=200):
                cells = [str(c) if c is not None else "" for c in row]
                if any(c.strip() for c in cells):
                    rows.append(" | ".join(cells))
            if rows:
                parts.append(f"=== Sheet: {sheet} ===\n" + "\n".join(rows))
        wb.close()
        return "\n\n".join(parts) or "[Empty spreadsheet]"
    except ImportError:
        return "[XLSX reading requires: pip install openpyxl]"
    except Exception as e:
        return f"[XLSX read error: {e}]"


# ── Main dispatcher ───────────────────────────────────────────────────────────


def extract_file_content(path: str | Path) -> dict:
    """
    Returns a dict:
      { "type": "text"|"image"|"pdf",
        "content": "...",          # for text/pdf
        "base64": "...",           # for image (send to vision model)
        "mime": "image/png",       # for image
        "path": "/abs/path",
        "summary": "one-line description" }
    """
    path = Path(path)
    suffix = path.suffix.lower()

    # Image types
    if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}:
        try:
            b64, mime = image_to_base64(path)
            return {
                "type": "image",
                "base64": b64,
                "mime": mime,
                "content": "",
                "path": str(path),
                "summary": f"Image: {path.name} ({path.stat().st_size // 1024} KB)",
            }
        except Exception as e:
            return {
                "type": "error",
                "content": f"Image read error: {e}",
                "path": str(path),
                "summary": "",
            }

    # SVG — treat as text
    if suffix == ".svg":
        return {
            "type": "text",
            "content": path.read_text(errors="replace")[:8000],
            "path": str(path),
            "summary": f"SVG: {path.name}",
        }

    # PDF
    if suffix == ".pdf":
        text = extract_pdf(path)
        return {
            "type": "pdf",
            "content": text,
            "path": str(path),
            "summary": f"PDF: {path.name}",
        }

    # Office
    if suffix == ".docx":
        return {
            "type": "text",
            "content": extract_docx(path)[:12000],
            "path": str(path),
            "summary": f"Word doc: {path.name}",
        }
    if suffix in {".xlsx", ".xls"}:
        return {
            "type": "text",
            "content": extract_xlsx(path)[:8000],
            "path": str(path),
            "summary": f"Spreadsheet: {path.name}",
        }

    # Everything else — read as text
    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:12000]
        return {
            "type": "text",
            "content": text,
            "path": str(path),
            "summary": f"File: {path.name}",
        }
    except Exception as e:
        return {"type": "error", "content": str(e), "path": str(path), "summary": ""}
