"""OCR service: AWS Textract primary, Tesseract local fallback."""
from __future__ import annotations

import io
from pathlib import Path

from loguru import logger

from app.config import settings


def _textract_available() -> bool:
    return bool(settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY)


def ocr_pdf(pdf_bytes: bytes) -> str:
    """Run OCR on a PDF. Tries Textract first if configured, else Tesseract."""
    if _textract_available():
        try:
            return _textract_pdf(pdf_bytes)
        except Exception as e:
            logger.warning("textract_failed", error=str(e))
    return _tesseract_pdf(pdf_bytes)


def ocr_image(image_bytes: bytes) -> str:
    """Run OCR on a single image."""
    if _textract_available():
        try:
            return _textract_image(image_bytes)
        except Exception as e:
            logger.warning("textract_failed", error=str(e))
    return _tesseract_image(image_bytes)


def _textract_pdf(pdf_bytes: bytes) -> str:
    import boto3

    client = boto3.client(
        "textract",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )
    resp = client.detect_document_text(Document={"Bytes": pdf_bytes})
    lines = [b["Text"] for b in resp.get("Blocks", []) if b.get("BlockType") == "LINE"]
    return "\n".join(lines)


def _textract_image(image_bytes: bytes) -> str:
    return _textract_pdf(image_bytes)


def _tesseract_pdf(pdf_bytes: bytes) -> str:
    """Render each PDF page to an image and OCR with Tesseract."""
    try:
        import fitz  # PyMuPDF
        import pytesseract
        from PIL import Image
    except ImportError as e:
        logger.error("tesseract_deps_missing", error=str(e))
        return ""

    text_parts = []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page in doc:
            pix = page.get_pixmap(dpi=200)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            page_text = pytesseract.image_to_string(img)
            text_parts.append(page_text)
        doc.close()
    except Exception as e:
        logger.error("tesseract_pdf_failed", error=str(e))
        return ""
    return "\n\n".join(text_parts)


def _tesseract_image(image_bytes: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return ""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        return pytesseract.image_to_string(img)
    except Exception as e:
        logger.error("tesseract_image_failed", error=str(e))
        return ""
