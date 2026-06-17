from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zlib
import zipfile
import xml.etree.ElementTree as ET

from .bookmarks import Bookmark


TEXT_DOCUMENT_SUFFIXES = {".txt", ".md", ".markdown"}
IMAGE_DOCUMENT_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}
SUPPORTED_DOCUMENT_SUFFIXES = {".pdf", ".docx", *TEXT_DOCUMENT_SUFFIXES, *IMAGE_DOCUMENT_SUFFIXES}


@dataclass
class DocumentImportResult:
    bookmark: Bookmark
    warning: str | None = None


def parse_documents(paths: list[Path], ocr: bool = False, ocr_lang: str | None = None) -> tuple[list[Bookmark], list[str]]:
    bookmarks: list[Bookmark] = []
    warnings: list[str] = []
    for path in paths:
        result = parse_document(path, ocr=ocr, ocr_lang=ocr_lang)
        bookmarks.append(result.bookmark)
        if result.warning:
            warnings.append(result.warning)
    return bookmarks, warnings


def parse_document(path: Path, ocr: bool = False, ocr_lang: str | None = None) -> DocumentImportResult:
    source = path.expanduser().resolve()
    suffix = source.suffix.lower()
    if suffix not in SUPPORTED_DOCUMENT_SUFFIXES:
        supported = ", ".join(sorted(SUPPORTED_DOCUMENT_SUFFIXES))
        raise ValueError(f"Unsupported document type for {source.name}. Supported: {supported}")
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"Document not found: {source}")

    warning: str | None = None
    if suffix == ".docx":
        text = extract_docx_text(source)
    elif suffix == ".pdf":
        text = extract_pdf_text(source)
        if not text.strip() and ocr:
            text, warning = extract_pdf_ocr_text(source, lang=ocr_lang)
        elif not text.strip():
            warning = f"{source.name}: no extractable PDF text found; run import-docs --ocr after installing tesseract and pdftoppm/poppler for scanned/image PDFs."
    elif suffix in IMAGE_DOCUMENT_SUFFIXES:
        if ocr:
            text, warning = extract_image_ocr_text(source, lang=ocr_lang)
        else:
            text = ""
            warning = f"{source.name}: image files need OCR; rerun with --ocr after installing tesseract."
    else:
        text = source.read_text(encoding="utf-8", errors="replace")

    text = normalize_document_text(text)
    title = source.stem.replace("_", " ").replace("-", " ").strip() or source.name
    tags = ["document", suffix.lstrip(".")]
    if ocr and suffix in IMAGE_DOCUMENT_SUFFIXES | {".pdf"}:
        tags.append("ocr")
    bookmark = Bookmark(
        title=title,
        url=source.as_uri(),
        source="document-import",
        tags=tags,
        document_text=text,
        document_type=suffix.lstrip("."),
        original_file=str(source),
    )
    return DocumentImportResult(bookmark=bookmark, warning=warning)


def extract_docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        try:
            xml_bytes = archive.read("word/document.xml")
        except KeyError as error:
            raise ValueError(f"{path.name} is not a readable DOCX file") from error
    root = ET.fromstring(xml_bytes)
    paragraphs: list[str] = []
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    for paragraph in root.iter(f"{namespace}p"):
        texts: list[str] = []
        for node in paragraph.iter():
            if node.tag == f"{namespace}t" and node.text:
                texts.append(node.text)
            elif node.tag == f"{namespace}tab":
                texts.append("\t")
            elif node.tag == f"{namespace}br":
                texts.append("\n")
        line = "".join(texts).strip()
        if line:
            paragraphs.append(line)
    return "\n\n".join(paragraphs)


def extract_pdf_text(path: Path) -> str:
    data = path.read_bytes()
    chunks: list[bytes] = []
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, flags=re.S):
        stream = match.group(1)
        dictionary = data[max(0, match.start() - 500): match.start()]
        if b"/FlateDecode" in dictionary:
            try:
                stream = zlib.decompress(stream)
            except zlib.error:
                continue
        chunks.append(stream)
    if not chunks:
        chunks = [data]

    text_parts: list[str] = []
    for chunk in chunks:
        text_parts.extend(extract_pdf_literal_strings(chunk))
        text_parts.extend(extract_pdf_hex_strings(chunk))
    return normalize_document_text("\n".join(part for part in text_parts if part.strip()))


def extract_image_ocr_text(path: Path, lang: str | None = None) -> tuple[str, str | None]:
    tesseract = shutil.which("tesseract")
    if not tesseract:
        return "", f"{path.name}: OCR requested but tesseract is not installed or not on PATH."
    try:
        command = [tesseract, str(path), "stdout"]
        if lang:
            command.extend(["-l", lang])
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except OSError as error:
        return "", f"{path.name}: OCR failed to start: {error}"
    except subprocess.TimeoutExpired:
        return "", f"{path.name}: OCR timed out."
    if completed.returncode != 0:
        message = completed.stderr.strip() or "unknown tesseract error"
        return "", f"{path.name}: OCR failed: {message}"
    text = normalize_document_text(completed.stdout)
    if not text:
        return "", f"{path.name}: OCR completed but found no text."
    return text, None


def extract_pdf_ocr_text(path: Path, lang: str | None = None) -> tuple[str, str | None]:
    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        return "", f"{path.name}: OCR requested for PDF, but pdftoppm/poppler is not installed or not on PATH."
    if not shutil.which("tesseract"):
        return "", f"{path.name}: OCR requested but tesseract is not installed or not on PATH."
    with tempfile.TemporaryDirectory() as tmp:
        prefix = Path(tmp) / "page"
        render = subprocess.run(
            [pdftoppm, "-png", "-r", "200", str(path), str(prefix)],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if render.returncode != 0:
            message = render.stderr.strip() or "unknown pdftoppm error"
            return "", f"{path.name}: PDF page rendering failed: {message}"
        pages = sorted(Path(tmp).glob("page-*.png"))
        if not pages:
            return "", f"{path.name}: PDF page rendering produced no images."
        parts: list[str] = []
        warnings: list[str] = []
        for index, page in enumerate(pages, start=1):
            text, warning = extract_image_ocr_text(page, lang=lang)
            if text:
                parts.append(f"### Page {index}\n\n{text}")
            if warning:
                warnings.append(f"page {index}: {warning}")
        combined = normalize_document_text("\n\n".join(parts))
        if combined:
            return combined, "; ".join(warnings) if warnings else None
        return "", f"{path.name}: OCR found no text." + (f" {'; '.join(warnings)}" if warnings else "")


def extract_pdf_literal_strings(chunk: bytes) -> list[str]:
    results: list[str] = []
    i = 0
    while i < len(chunk):
        if chunk[i] != 0x28:  # (
            i += 1
            continue
        i += 1
        depth = 1
        current = bytearray()
        while i < len(chunk) and depth:
            char = chunk[i]
            if char == 0x5C and i + 1 < len(chunk):  # backslash escape
                nxt = chunk[i + 1]
                escapes = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12, ord("("): 40, ord(")"): 41, ord("\\"): 92}
                current.append(escapes.get(nxt, nxt))
                i += 2
                continue
            if char == 0x28:
                depth += 1
                current.append(char)
            elif char == 0x29:
                depth -= 1
                if depth:
                    current.append(char)
            else:
                current.append(char)
            i += 1
        try:
            results.append(current.decode("utf-8"))
        except UnicodeDecodeError:
            results.append(current.decode("latin-1", errors="replace"))
    return results


def extract_pdf_hex_strings(chunk: bytes) -> list[str]:
    results: list[str] = []
    for raw in re.findall(rb"<([0-9A-Fa-f\s]{4,})>", chunk):
        compact = re.sub(rb"\s+", b"", raw)
        if len(compact) % 2:
            compact += b"0"
        try:
            decoded = bytes.fromhex(compact.decode("ascii"))
        except ValueError:
            continue
        text = decoded.decode("utf-16-be", errors="ignore") if decoded.startswith(b"\xfe\xff") else decoded.decode("latin-1", errors="ignore")
        if text.strip():
            results.append(text)
    return results


def normalize_document_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    normalized: list[str] = []
    blank = False
    for line in lines:
        if not line:
            if not blank and normalized:
                normalized.append("")
            blank = True
            continue
        normalized.append(line)
        blank = False
    return "\n".join(normalized).strip()
