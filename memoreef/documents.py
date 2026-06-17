from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import re
import shlex
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


PDF_VISION_MAX_PAGES = 25
PDF_LARGE_FILE_WARNING_BYTES = 50 * 1024 * 1024


PDF_VISUAL_PROMPT = (
    "Describe graphs, figures, diagrams, charts, axes, legends, captions, and tables on this PDF page. "
    "Focus on research-paper evidence."
)


def parse_documents(
    paths: list[Path],
    ocr: bool = False,
    ocr_lang: str | None = None,
    vision_command: str | None = None,
    vision_page_limit: int = 10,
) -> tuple[list[Bookmark], list[str]]:
    bookmarks: list[Bookmark] = []
    warnings: list[str] = []
    for path in paths:
        result = parse_document(path, ocr=ocr, ocr_lang=ocr_lang, vision_command=vision_command, vision_page_limit=vision_page_limit)
        bookmarks.append(result.bookmark)
        if result.warning:
            warnings.append(result.warning)
    return bookmarks, warnings


def parse_document(
    path: Path,
    ocr: bool = False,
    ocr_lang: str | None = None,
    vision_command: str | None = None,
    vision_page_limit: int = 10,
) -> DocumentImportResult:
    source = path.expanduser().resolve()
    suffix = source.suffix.lower()
    if suffix not in SUPPORTED_DOCUMENT_SUFFIXES:
        supported = ", ".join(sorted(SUPPORTED_DOCUMENT_SUFFIXES))
        raise ValueError(f"Unsupported document type for {source.name}. Supported: {supported}")
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"Document not found: {source}")

    warning: str | None = None
    visual_analysis: str | None = None
    visual_warnings: list[str] = []
    if suffix == ".docx":
        text = extract_docx_text(source)
    elif suffix == ".pdf":
        text = extract_pdf_text(source)
        if not text.strip() and ocr:
            text, warning = extract_pdf_ocr_text(source, lang=ocr_lang)
        elif not text.strip():
            warning = f"{source.name}: no extractable PDF text found; run import-docs --ocr after installing tesseract and pdftoppm/poppler for scanned/image PDFs."
        visual_analysis, visual_warnings = extract_pdf_visual_analysis(source, text, vision_command=vision_command, page_limit=vision_page_limit)
    elif suffix in IMAGE_DOCUMENT_SUFFIXES:
        if ocr:
            text, warning = extract_image_ocr_text(source, lang=ocr_lang)
        else:
            text = ""
            warning = f"{source.name}: image files need OCR; rerun with --ocr after installing tesseract."
    else:
        text = source.read_text(encoding="utf-8", errors="replace")

    text = normalize_document_text(text)
    if visual_warnings:
        warning = "; ".join([part for part in [warning, *visual_warnings] if part])
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
        document_visual_analysis=visual_analysis,
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


def extract_pdf_visual_analysis(
    path: Path,
    text: str,
    vision_command: str | None = None,
    page_limit: int = 10,
) -> tuple[str | None, list[str]]:
    """Return optional visual notes for a research PDF without making vision mandatory."""
    sections: list[str] = []
    warnings: list[str] = []

    if vision_command:
        effective_page_limit = min(max(1, page_limit), PDF_VISION_MAX_PAGES)
        warnings.extend(pdf_visual_size_warnings(path, page_limit=effective_page_limit))

    captions = extract_pdf_visual_captions(text)
    if captions:
        sections.append("### Captions and table references\n\n" + "\n".join(f"- {caption}" for caption in captions))

    tables = extract_text_table_snippets(text)
    if tables:
        sections.append("### Text table candidates\n\n" + "\n\n".join(f"```text\n{table}\n```" for table in tables))

    if vision_command:
        descriptions, vision_warnings = describe_pdf_pages_with_vision_command(path, vision_command, page_limit=max(1, page_limit))
        warnings.extend(vision_warnings)
        if descriptions:
            sections.append("### Vision page descriptions\n\n" + "\n\n".join(descriptions))

    if not sections:
        return None, warnings
    return "\n\n".join(sections), warnings


def extract_pdf_visual_captions(text: str) -> list[str]:
    captions: list[str] = []
    seen: set[str] = set()
    pattern = re.compile(r"^(fig(?:ure)?\.?\s*\d+[a-z]?\b.*|table\s*\d+[a-z]?\b.*)$", re.IGNORECASE)
    for line in text.splitlines():
        candidate = line.strip()
        if not candidate or len(candidate) > 500:
            continue
        if not pattern.match(candidate):
            continue
        normalized = re.sub(r"\s+", " ", candidate)
        key = normalized.lower()
        if key not in seen:
            captions.append(normalized)
            seen.add(key)
    return captions[:25]


def extract_text_table_snippets(text: str) -> list[str]:
    snippets: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if looks_like_table_row(stripped):
            current.append(stripped)
            continue
        if len(current) >= 2:
            snippets.append("\n".join(current[:8]))
        current = []
    if len(current) >= 2:
        snippets.append("\n".join(current[:8]))
    return snippets[:5]


def looks_like_table_row(line: str) -> bool:
    if not line or len(line) > 300:
        return False
    if "|" in line and line.count("|") >= 2:
        return True
    numeric_cells = re.findall(r"(?:^|\s)(?:-?\d+(?:\.\d+)?%?)(?=\s|$)", line)
    return len(numeric_cells) >= 3


def describe_pdf_pages_with_vision_command(path: Path, vision_command: str, page_limit: int = 10) -> tuple[list[str], list[str]]:
    page_limit = min(max(1, page_limit), PDF_VISION_MAX_PAGES)
    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        return [], [f"{path.name}: --vision-command requested, but pdftoppm/poppler is not installed or not on PATH."]
    descriptions: list[str] = []
    warnings: list[str] = []
    seen_region_warnings: set[str] = set()
    with tempfile.TemporaryDirectory() as tmp:
        prefix = Path(tmp) / "page"
        render = subprocess.run(
            [pdftoppm, "-png", "-r", "150", "-f", "1", "-l", str(page_limit), str(path), str(prefix)],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if render.returncode != 0:
            message = render.stderr.strip() or "unknown pdftoppm error"
            return [], [f"{path.name}: PDF page rendering for vision failed: {message}"]
        pages = sorted(Path(tmp).glob("page-*.png"), key=pdf_rendered_page_number)
        if not pages:
            return [], [f"{path.name}: PDF page rendering for vision produced no images."]
        for page in pages:
            page_number = pdf_rendered_page_number(page)
            regions, region_warnings = crop_pdf_visual_regions(page, Path(tmp), page_number)
            for region_warning in region_warnings:
                warning_key = normalize_region_warning_key(region_warning)
                if warning_key not in seen_region_warnings:
                    warnings.append(region_warning)
                    seen_region_warnings.add(warning_key)
            targets = regions or [page]
            for region_index, target in enumerate(targets, start=1):
                description, warning = run_vision_command(vision_command, target, page_number)
                if description:
                    if regions:
                        descriptions.append(f"#### Page {page_number} · visual region {region_index}\n\n{description}")
                    else:
                        descriptions.append(f"#### Page {page_number}\n\n{description}")
                if warning:
                    warnings.append(warning)
    return descriptions, warnings


def normalize_region_warning_key(warning: str) -> str:
    return re.sub(r"^page \d+: ", "page *: ", warning)


def pdf_visual_size_warnings(path: Path, page_limit: int) -> list[str]:
    warnings: list[str] = []
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    if size > PDF_LARGE_FILE_WARNING_BYTES:
        warnings.append(f"{path.name}: large PDF ({size // (1024 * 1024)} MB); visual analysis may be slow or costly.")
    page_count = pdf_page_count(path)
    if page_count and page_count > page_limit:
        warnings.append(f"{path.name}: PDF has {page_count} pages; visual analysis will inspect first {page_limit} only. Increase --vision-page-limit up to {PDF_VISION_MAX_PAGES} if needed.")
    return warnings


def pdf_page_count(path: Path) -> int | None:
    pdfinfo = shutil.which("pdfinfo")
    if pdfinfo:
        try:
            completed = subprocess.run([pdfinfo, str(path)], check=False, capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            completed = None
        if completed and completed.returncode == 0:
            match = re.search(r"^Pages:\s*(\d+)\s*$", completed.stdout, re.MULTILINE)
            if match:
                return int(match.group(1))
    try:
        data = read_pdf_count_sample(path)
    except OSError:
        return None
    counts = [int(match.group(1)) for match in re.finditer(rb"/Count\s+(\d+)", data)]
    return max(counts) if counts else None


def read_pdf_count_sample(path: Path, max_bytes: int = 2 * 1024 * 1024) -> bytes:
    size = path.stat().st_size
    with path.open("rb") as handle:
        if size <= max_bytes * 2:
            return handle.read()
        head = handle.read(max_bytes)
        handle.seek(max(0, size - max_bytes))
        tail = handle.read(max_bytes)
    return head + tail


def crop_pdf_visual_regions(page_image: Path, output_dir: Path, page_number: int, max_regions: int = 6) -> tuple[list[Path], list[str]]:
    try:
        from PIL import Image
    except ImportError as error:
        return [], [f"page {page_number}: visual region cropping skipped because Pillow is not installed ({error})."]
    try:
        image = Image.open(page_image).convert("L")
    except OSError as error:
        return [], [f"page {page_number}: visual region cropping failed to read rendered page ({error})."]

    boxes = detect_visual_region_boxes(image)
    crops: list[Path] = []
    for index, box in enumerate(boxes[:max_regions], start=1):
        crop_path = output_dir / f"page-{page_number}-visual-region-{index}.png"
        image.crop(box).save(crop_path)
        crops.append(crop_path)
    return crops, []


def detect_visual_region_boxes(image: Any) -> list[tuple[int, int, int, int]]:
    width, height = image.size
    if width <= 0 or height <= 0:
        return []
    block = max(8, min(width, height) // 80)
    cols = max(1, (width + block - 1) // block)
    rows = max(1, (height + block - 1) // block)
    occupied: set[tuple[int, int]] = set()
    pixels = image.load()
    for row in range(rows):
        y0 = row * block
        y1 = min(height, y0 + block)
        for col in range(cols):
            x0 = col * block
            x1 = min(width, x0 + block)
            dark = 0
            total = max(1, (x1 - x0) * (y1 - y0))
            for y in range(y0, y1):
                for x in range(x0, x1):
                    if pixels[x, y] < 245:
                        dark += 1
            if dark / total > 0.025:
                occupied.add((col, row))

    boxes: list[tuple[int, int, int, int]] = []
    seen: set[tuple[int, int]] = set()
    for cell in sorted(occupied):
        if cell in seen:
            continue
        stack = [cell]
        seen.add(cell)
        component: list[tuple[int, int]] = []
        while stack:
            col, row = stack.pop()
            component.append((col, row))
            for neighbor in ((col - 1, row), (col + 1, row), (col, row - 1), (col, row + 1)):
                if neighbor in occupied and neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        box = component_to_image_box(component, block, width, height)
        if is_plausible_visual_box(box, width, height):
            boxes.append(expand_box(box, width, height, padding=block))
    boxes.sort(key=lambda box: (box[1], box[0]))
    return boxes


def component_to_image_box(component: list[tuple[int, int]], block: int, width: int, height: int) -> tuple[int, int, int, int]:
    min_col = min(col for col, _row in component)
    max_col = max(col for col, _row in component)
    min_row = min(row for _col, row in component)
    max_row = max(row for _col, row in component)
    return (min_col * block, min_row * block, min(width, (max_col + 1) * block), min(height, (max_row + 1) * block))


def is_plausible_visual_box(box: tuple[int, int, int, int], page_width: int, page_height: int) -> bool:
    x0, y0, x1, y1 = box
    width = x1 - x0
    height = y1 - y0
    area = width * height
    page_area = page_width * page_height
    if width < page_width * 0.12 or height < page_height * 0.06:
        return False
    if area < page_area * 0.01:
        return False
    if area > page_area * 0.85:
        return False
    return True


def expand_box(box: tuple[int, int, int, int], page_width: int, page_height: int, padding: int) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    return (max(0, x0 - padding), max(0, y0 - padding), min(page_width, x1 + padding), min(page_height, y1 + padding))


def pdf_rendered_page_number(path: Path) -> int:
    match = re.search(r"-(\d+)\.png$", path.name)
    if match:
        return int(match.group(1))
    return 0


def replace_vision_placeholders(argument: str, values: dict[str, str]) -> str:
    for placeholder, value in values.items():
        argument = argument.replace(placeholder, value)
    return argument


def run_vision_command(command_template: str, image: Path, page: int) -> tuple[str | None, str | None]:
    values = {"{image}": str(image), "{page}": str(page), "{prompt}": PDF_VISUAL_PROMPT}
    try:
        command = shlex.split(command_template)
    except ValueError as error:
        return None, f"vision command template is invalid: {error}"
    command = [replace_vision_placeholders(argument, values) for argument in command]
    if not command:
        return None, "vision command template produced an empty command."
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=180)
    except OSError as error:
        return None, f"vision command failed to start for page {page}: {error}"
    except subprocess.TimeoutExpired:
        return None, f"vision command timed out for page {page}."
    if completed.returncode != 0:
        message = completed.stderr.strip() or "unknown vision command error"
        return None, f"vision command failed for page {page}: {message}"
    description = normalize_document_text(completed.stdout)
    if not description:
        return None, f"vision command returned no description for page {page}."
    return description, None


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
