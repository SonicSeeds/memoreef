from __future__ import annotations

from dataclasses import dataclass, field
import importlib.metadata
import importlib.util
from pathlib import Path
from typing import Any
import csv
import io
import json
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
DOCUMENT_EXTRACTION_ENGINES = {"builtin", "auto", "docling"}


@dataclass
class DocumentImportResult:
    bookmark: Bookmark
    warning: str | None = None


@dataclass
class DocumentExtraction:
    text: str
    visual_analysis: str | None = None
    numeric_analysis: str | None = None
    warnings: list[str] = field(default_factory=list)
    engine: str = "builtin"
    engine_version: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


PDF_VISION_MAX_PAGES = 25
PDF_LARGE_FILE_WARNING_BYTES = 50 * 1024 * 1024


PDF_VISUAL_PROMPT = (
    "Describe graphs, figures, diagrams, charts, axes, legends, captions, and tables on this PDF crop/page. "
    "Focus on research-paper evidence. For exact numeric values, do not estimate: only report values from printed numeric labels, table cells, data labels, axis tick labels, or explicitly tick-aligned marks. "
    "If exact values are readable, include a fenced ```json block with this schema: "
    "{\"type\":\"numeric_artifact\",\"artifact\":\"Figure/Table identifier if visible\",\"source\":\"page/crop\",\"values\":[{\"label\":\"series/row\",\"x\":\"axis/category if visible\",\"y\":\"exact value\",\"unit\":\"unit if visible\",\"confidence\":\"high|medium|low\"}],\"notes\":\"uncertainty\"}. "
    "For simple vertical bar charts where tick labels and bar tops are visible, you may instead include exactly a fenced ```json block with this chart digitization schema: "
    "{\"type\":\"chart_digitization\",\"chart_type\":\"vertical_bar\",\"artifact\":\"Figure identifier\",\"source\":\"page/crop\",\"y_axis\":{\"unit\":\"unit\",\"ticks\":[{\"value\":\"0\",\"pixel_y\":440},{\"value\":\"100\",\"pixel_y\":140}]},\"bars\":[{\"label\":\"A\",\"pixel_top_y\":230,\"confidence\":\"medium\"}]}. "
    "Only provide chart_digitization when coordinates are referenced to the analyzed crop/page image. "
    "If exact values are not readable, say that exact values were not extracted."
)


def parse_documents(
    paths: list[Path],
    ocr: bool = False,
    ocr_lang: str | None = None,
    vision_command: str | None = None,
    vision_page_limit: int = 10,
    engine: str = "builtin",
) -> tuple[list[Bookmark], list[str]]:
    bookmarks: list[Bookmark] = []
    warnings: list[str] = []
    for path in paths:
        result = parse_document(
            path,
            ocr=ocr,
            ocr_lang=ocr_lang,
            vision_command=vision_command,
            vision_page_limit=vision_page_limit,
            engine=engine,
        )
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
    engine: str = "builtin",
) -> DocumentImportResult:
    source = path.expanduser().resolve()
    suffix = source.suffix.lower()
    engine = normalize_document_engine(engine)
    if suffix not in SUPPORTED_DOCUMENT_SUFFIXES:
        supported = ", ".join(sorted(SUPPORTED_DOCUMENT_SUFFIXES))
        raise ValueError(f"Unsupported document type for {source.name}. Supported: {supported}")
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"Document not found: {source}")

    extraction = extract_document(source, engine=engine, ocr=ocr, ocr_lang=ocr_lang, vision_command=vision_command, vision_page_limit=vision_page_limit)
    text = normalize_document_text(extraction.text)
    warning = "; ".join(extraction.warnings) if extraction.warnings else None
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
        document_visual_analysis=extraction.visual_analysis,
        document_numeric_analysis=extraction.numeric_analysis,
        document_type=suffix.lstrip("."),
        original_file=str(source),
        document_extraction_engine=extraction.engine,
        document_extraction_engine_version=extraction.engine_version,
    )
    return DocumentImportResult(bookmark=bookmark, warning=warning)


def normalize_document_engine(engine: str | None) -> str:
    normalized = (engine or "builtin").strip().lower()
    if normalized not in DOCUMENT_EXTRACTION_ENGINES:
        choices = ", ".join(sorted(DOCUMENT_EXTRACTION_ENGINES))
        raise ValueError(f"Unsupported document extraction engine: {engine}. Supported: {choices}")
    return normalized


def extract_document(
    path: Path,
    engine: str = "builtin",
    ocr: bool = False,
    ocr_lang: str | None = None,
    vision_command: str | None = None,
    vision_page_limit: int = 10,
) -> DocumentExtraction:
    engine = normalize_document_engine(engine)
    if engine == "auto":
        if docling_available():
            extraction = extract_document_with_docling(path, requested_engine="auto")
            if extraction is not None:
                return enrich_pdf_extraction(path, extraction, vision_command=vision_command, vision_page_limit=vision_page_limit)
        extraction = extract_document_builtin(path, ocr=ocr, ocr_lang=ocr_lang, vision_command=vision_command, vision_page_limit=vision_page_limit)
        extraction.warnings.insert(0, f"{path.name}: --engine auto used builtin extraction; no supported optional local extraction engine produced output.")
        return extraction
    if engine == "docling":
        extraction = extract_document_with_docling(path, requested_engine="docling")
        if extraction is not None:
            return enrich_pdf_extraction(path, extraction, vision_command=vision_command, vision_page_limit=vision_page_limit)
        fallback = extract_document_builtin(path, ocr=ocr, ocr_lang=ocr_lang, vision_command=vision_command, vision_page_limit=vision_page_limit)
        fallback.warnings.insert(0, f"{path.name}: Docling extraction requested but docling is not installed or failed; used builtin extraction.")
        return fallback
    return extract_document_builtin(path, ocr=ocr, ocr_lang=ocr_lang, vision_command=vision_command, vision_page_limit=vision_page_limit)


def extract_document_builtin(
    path: Path,
    ocr: bool = False,
    ocr_lang: str | None = None,
    vision_command: str | None = None,
    vision_page_limit: int = 10,
) -> DocumentExtraction:
    suffix = path.suffix.lower()
    warnings: list[str] = []
    visual_analysis: str | None = None
    numeric_analysis: str | None = None
    if suffix == ".docx":
        text = extract_docx_text(path)
    elif suffix == ".pdf":
        text = extract_pdf_text(path)
        if not text.strip() and ocr:
            text, warning = extract_pdf_ocr_text(path, lang=ocr_lang)
            if warning:
                warnings.append(warning)
        elif not text.strip():
            warnings.append(f"{path.name}: no extractable PDF text found; run import-docs --ocr after installing tesseract and pdftoppm/poppler for scanned/image PDFs.")
        visual_analysis, visual_warnings = extract_pdf_visual_analysis(path, text, vision_command=vision_command, page_limit=vision_page_limit)
        warnings.extend(visual_warnings)
        numeric_analysis = extract_pdf_numeric_analysis(text, visual_analysis)
    elif suffix in IMAGE_DOCUMENT_SUFFIXES:
        if ocr:
            text, warning = extract_image_ocr_text(path, lang=ocr_lang)
            if warning:
                warnings.append(warning)
        else:
            text = ""
            warnings.append(f"{path.name}: image files need OCR; rerun with --ocr after installing tesseract.")
    else:
        text = path.read_text(encoding="utf-8", errors="replace")
    return DocumentExtraction(
        text=normalize_document_text(text),
        visual_analysis=visual_analysis,
        numeric_analysis=numeric_analysis,
        warnings=warnings,
        engine="builtin",
    )


def docling_available() -> bool:
    try:
        return importlib.util.find_spec("docling.document_converter") is not None
    except ModuleNotFoundError:
        return False


def package_version(package: str) -> str | None:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None


def extract_document_with_docling(path: Path, requested_engine: str) -> DocumentExtraction | None:
    if not docling_available():
        return None
    try:
        from docling.document_converter import DocumentConverter  # type: ignore[import-not-found]

        result = DocumentConverter().convert(str(path))
        document = getattr(result, "document", None)
        if document is None or not hasattr(document, "export_to_markdown"):
            return None
        text = document.export_to_markdown()
    except Exception:
        return None
    if not isinstance(text, str) or not text.strip():
        return None
    return DocumentExtraction(
        text=normalize_document_text(text),
        warnings=[] if requested_engine == "docling" else [f"{path.name}: --engine auto used Docling extraction."],
        engine="docling",
        engine_version=package_version("docling"),
    )


def enrich_pdf_extraction(
    path: Path,
    extraction: DocumentExtraction,
    vision_command: str | None = None,
    vision_page_limit: int = 10,
) -> DocumentExtraction:
    if path.suffix.lower() != ".pdf":
        return extraction
    visual_analysis, visual_warnings = extract_pdf_visual_analysis(path, extraction.text, vision_command=vision_command, page_limit=vision_page_limit)
    extraction.visual_analysis = visual_analysis
    extraction.numeric_analysis = extract_pdf_numeric_analysis(extraction.text, visual_analysis)
    extraction.warnings.extend(visual_warnings)
    return extraction


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
        sections.append("### Text table candidates\n\n" + "\n\n".join(fenced_code("text", table) for table in tables))

    if vision_command:
        descriptions, vision_warnings = describe_pdf_pages_with_vision_command(path, vision_command, page_limit=max(1, page_limit))
        warnings.extend(vision_warnings)
        if descriptions:
            sections.append("### Vision page descriptions\n\n" + "\n\n".join(descriptions))

    if not sections:
        return None, warnings
    return "\n\n".join(sections), warnings


def extract_pdf_numeric_analysis(text: str, visual_analysis: str | None = None) -> str | None:
    sections: list[str] = []
    table_artifacts = extract_numeric_table_artifacts(text)
    digitized_chart_artifacts = extract_digitized_chart_artifacts(visual_analysis or "")
    vision_artifacts = extract_vision_numeric_json_artifacts(visual_analysis or "")

    if not table_artifacts and not digitized_chart_artifacts and not vision_artifacts:
        return None

    sections.append(
        "### Exact-number answering contract\n\n"
        "Agents may answer exact numeric questions only from quoted source table text or validated structured values in this section. "
        "CSV tables here are machine-extracted candidates from PDF text and include their source snippet; preserve row/column context and do not invent missing headers. "
        "Vision-reported values are accepted only when they pass the numeric-artifact schema and include confidence. "
        "Digitized chart values are calibrated estimates computed from chart geometry, not source-printed exact values; use them only with their confidence/source fields and call them digitized estimates. "
        "If a value is only described in visual prose, treat it as a trend/meaning summary, not exact evidence. "
        "If the requested exact value is absent here, say that the exact value was not extracted."
    )
    if table_artifacts:
        sections.append("### Extracted numeric tables\n\n" + "\n\n".join(table_artifacts))
    if digitized_chart_artifacts:
        sections.append("### Digitized chart values\n\n" + "\n\n".join(digitized_chart_artifacts))
    if vision_artifacts:
        sections.append("### Vision-reported numeric candidates\n\n" + "\n\n".join(vision_artifacts))
    return "\n\n".join(sections)


def extract_numeric_table_artifacts(text: str) -> list[str]:
    artifacts: list[str] = []
    for index, snippet in enumerate(extract_text_table_snippets(text), start=1):
        rows = parse_numeric_table_rows(snippet)
        if not rows:
            continue
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerows(rows)
        csv_text = output.getvalue().strip()
        artifacts.append(
            f"#### Table candidate {index}\n\n"
            "Source snippet:\n\n"
            f"{fenced_code('text', snippet)}\n\n"
            "Machine-extracted CSV:\n\n"
            f"{fenced_code('csv', csv_text)}"
        )
    return artifacts[:10]


def fenced_code(language: str, content: str) -> str:
    longest = max((len(match.group(0)) for match in re.finditer(r"`+", content)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}{language}\n{content}\n{fence}"


def parse_numeric_table_rows(snippet: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in snippet.splitlines():
        cells = split_table_line(line)
        if len(cells) < 2:
            continue
        rows.append(cells)
    if len(rows) < 2:
        return []
    max_width = max(len(row) for row in rows)
    normalized = [row + [""] * (max_width - len(row)) for row in rows]
    numeric_cells = sum(1 for row in normalized for cell in row if contains_number(cell))
    if numeric_cells < 2:
        return []
    return normalized


def split_table_line(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    if "|" in stripped:
        return [cell.strip() for cell in stripped.split("|") if cell.strip()]
    if "\t" in stripped:
        return [cell.strip() for cell in stripped.split("\t") if cell.strip()]
    parts = [cell.strip() for cell in re.split(r"\s{2,}", stripped) if cell.strip()]
    if len(parts) >= 2:
        return parts
    tokens = stripped.split()
    numeric_token_count = len([token for token in tokens if contains_number(token)])
    if numeric_token_count == 0 and looks_like_header_tokens(tokens, stripped):
        return tokens
    if numeric_token_count >= 1:
        first_number = next((index for index, token in enumerate(tokens) if contains_number(token)), 0)
        if first_number > 0:
            return [" ".join(tokens[:first_number]), *tokens[first_number:]]
        if numeric_token_count >= 2:
            return tokens
    return []


def looks_like_header_tokens(tokens: list[str], line: str) -> bool:
    if not 2 <= len(tokens) <= 8:
        return False
    if line.endswith(('.', ':', ';')):
        return False
    return any(re.search(r"[A-Za-z]", token) for token in tokens) and all(len(token) <= 40 for token in tokens)


NUMERIC_TOKEN_PATTERN = re.compile(
    r"(?:[+\-−]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[+\-−]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?|\([0-9]+(?:\.[0-9]+)?\))%?"
)
STRICT_NUMERIC_FIELD_PATTERN = re.compile(
    r"^(?:[+\-−]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)(?:[eE][+\-]?\d+)?%?|\(\d+(?:\.\d+)?\)%?)$"
)


def contains_number(value: str) -> bool:
    return bool(NUMERIC_TOKEN_PATTERN.search(value))


def extract_digitized_chart_artifacts(markdown: str) -> list[str]:
    artifacts: list[str] = []
    for raw_json in re.findall(r"```json\s*(.*?)\s*```", markdown, flags=re.S | re.I):
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError:
            continue
        artifact = digitize_chart_json(parsed)
        if artifact:
            artifacts.append(artifact)
    return artifacts[:10]


def digitize_chart_json(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    if value.get("type") != "chart_digitization":
        return None
    if value.get("chart_type") != "vertical_bar":
        return None
    ticks = extract_chart_ticks(value.get("y_axis"))
    if len(ticks) < 2:
        return None
    tick_low, tick_high = choose_calibration_ticks(ticks)
    if tick_low is None or tick_high is None:
        return None
    if not chart_ticks_are_consistent(ticks, tick_low, tick_high):
        return None
    bars = value.get("bars")
    if not isinstance(bars, list):
        return None
    unit = ""
    if isinstance(value.get("y_axis"), dict):
        unit = safe_short_string(value["y_axis"].get("unit"), fallback="")
    rows = [["artifact", "chart_type", "label", "value", "value_kind", "unit", "confidence", "source", "pixel_top_y"]]
    for bar in bars[:100]:
        row = digitize_vertical_bar_row(bar, value, tick_low, tick_high, unit)
        if row:
            rows.append(row)
    if len(rows) < 2:
        return None
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerows(rows)
    return (
        f"#### {safe_short_string(value.get('artifact'), fallback='Digitized vertical bar chart')}\n\n"
        "Digitized CSV:\n\n"
        f"{fenced_code('csv', output.getvalue().strip())}"
    )


def extract_chart_ticks(y_axis: object) -> list[tuple[float, float]]:
    if not isinstance(y_axis, dict):
        return []
    ticks = y_axis.get("ticks")
    if not isinstance(ticks, list):
        return []
    parsed: list[tuple[float, float]] = []
    for tick in ticks[:20]:
        if not isinstance(tick, dict):
            continue
        value = parse_number(tick.get("value"))
        pixel_y = parse_number(tick.get("pixel_y"))
        if value is None or pixel_y is None:
            continue
        parsed.append((value, pixel_y))
    return parsed


def choose_calibration_ticks(ticks: list[tuple[float, float]]) -> tuple[tuple[float, float] | None, tuple[float, float] | None]:
    best_pair: tuple[tuple[float, float], tuple[float, float]] | None = None
    best_span = 0.0
    for i, first in enumerate(ticks):
        for second in ticks[i + 1 :]:
            value_span = abs(second[0] - first[0])
            pixel_span = abs(second[1] - first[1])
            if value_span <= 0 or pixel_span <= 0:
                continue
            span = value_span * pixel_span
            if span > best_span:
                best_pair = (first, second)
                best_span = span
    if best_pair is None:
        return None, None
    return best_pair


def chart_ticks_are_consistent(ticks: list[tuple[float, float]], tick_a: tuple[float, float], tick_b: tuple[float, float]) -> bool:
    value_span = abs(tick_b[0] - tick_a[0])
    tolerance = max(value_span * 0.02, 1e-6)
    for value, pixel_y in ticks:
        predicted = interpolate_value_from_pixel_y(pixel_y, tick_a, tick_b)
        if predicted is None:
            return False
        if abs(predicted - value) > tolerance:
            return False
    return True


def pixel_y_within_calibration(pixel_y: float, tick_a: tuple[float, float], tick_b: tuple[float, float]) -> bool:
    low = min(tick_a[1], tick_b[1])
    high = max(tick_a[1], tick_b[1])
    tolerance = max((high - low) * 0.01, 1.0)
    return low - tolerance <= pixel_y <= high + tolerance


def digitize_vertical_bar_row(
    bar: object,
    chart: dict[str, object],
    tick_a: tuple[float, float],
    tick_b: tuple[float, float],
    unit: str,
) -> list[str] | None:
    if not isinstance(bar, dict):
        return None
    pixel_top = parse_number(bar.get("pixel_top_y"))
    if pixel_top is None:
        return None
    if not pixel_y_within_calibration(pixel_top, tick_a, tick_b):
        return None
    value = interpolate_value_from_pixel_y(pixel_top, tick_a, tick_b)
    if value is None:
        return None
    confidence = safe_short_string(bar.get("confidence"), fallback="medium").lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "low"
    return [
        safe_csv_text(safe_short_string(chart.get("artifact"), fallback="unknown")),
        "vertical_bar",
        safe_csv_text(safe_short_string(bar.get("label"), fallback="unknown")),
        format_digitized_number(value),
        "digitized_estimate",
        safe_csv_text(unit),
        confidence,
        safe_csv_text(safe_short_string(chart.get("source"), fallback="unknown")),
        format_digitized_number(pixel_top),
    ]


def interpolate_value_from_pixel_y(pixel_y: float, tick_a: tuple[float, float], tick_b: tuple[float, float]) -> float | None:
    value_a, pixel_a = tick_a
    value_b, pixel_b = tick_b
    if pixel_a == pixel_b:
        return None
    slope = (value_b - value_a) / (pixel_b - pixel_a)
    return value_a + (pixel_y - pixel_a) * slope


def parse_number(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    text = str(value).strip().replace("−", "-")
    if not STRICT_NUMERIC_FIELD_PATTERN.fullmatch(text):
        return None
    token = text.replace(",", "").rstrip("%")
    if token.startswith("(") and token.endswith(")"):
        token = "-" + token[1:-1]
    try:
        return float(token)
    except ValueError:
        return None


def format_digitized_number(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.6g}"


def extract_vision_numeric_json_artifacts(markdown: str) -> list[str]:
    artifacts: list[str] = []
    for raw_json in re.findall(r"```json\s*(.*?)\s*```", markdown, flags=re.S | re.I):
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError:
            continue
        normalized = normalize_numeric_artifact_json(parsed)
        if normalized is None:
            continue
        artifacts.append(fenced_code("json", json.dumps(normalized, indent=2, ensure_ascii=False, sort_keys=True)))
    return artifacts[:10]


def normalize_numeric_artifact_json(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    if value.get("type") != "numeric_artifact":
        return None
    raw_values = value.get("values")
    if not isinstance(raw_values, list):
        return None
    normalized_values: list[dict[str, str]] = []
    for raw_item in raw_values[:50]:
        item = normalize_numeric_value_item(raw_item)
        if item is not None:
            normalized_values.append(item)
    if not normalized_values:
        return None
    return {
        "type": "numeric_artifact",
        "artifact": safe_short_string(value.get("artifact"), fallback="unknown"),
        "source": safe_short_string(value.get("source"), fallback="unknown"),
        "values": normalized_values,
        "notes": safe_short_string(value.get("notes"), fallback=""),
    }


def normalize_numeric_value_item(value: object) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    y = safe_short_string(value.get("y"), fallback="")
    if not y or not contains_number(y):
        return None
    confidence = safe_short_string(value.get("confidence"), fallback="low").lower()
    if confidence not in {"high", "medium", "low"}:
        return None
    return {
        "label": safe_short_string(value.get("label"), fallback="unknown"),
        "x": safe_short_string(value.get("x"), fallback=""),
        "y": y,
        "unit": safe_short_string(value.get("unit"), fallback=""),
        "confidence": confidence,
    }


def safe_csv_text(value: str) -> str:
    if value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def safe_short_string(value: object, fallback: str, max_len: int = 200) -> str:
    if value is None:
        return fallback
    text = str(value).replace("\x00", "").strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) > max_len:
        text = text[:max_len].rstrip() + "…"
    return text


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
    previous_nonempty = ""
    for line in text.splitlines():
        stripped = line.strip()
        if looks_like_table_row(stripped):
            if not current and previous_nonempty and looks_like_table_header(previous_nonempty):
                current.append(previous_nonempty)
            current.append(stripped)
            previous_nonempty = stripped
            continue
        if len(current) >= 2:
            snippets.append("\n".join(current[:8]))
        current = []
        if stripped:
            previous_nonempty = stripped
    if len(current) >= 2:
        snippets.append("\n".join(current[:8]))
    return snippets[:5]


def looks_like_table_header(line: str) -> bool:
    if not line or len(line) > 300:
        return False
    if looks_like_table_row(line):
        return False
    return len(split_table_line(line)) >= 2


def looks_like_table_row(line: str) -> bool:
    if not line or len(line) > 300:
        return False
    if "|" in line and line.count("|") >= 2:
        return True
    numeric_cells = re.findall(NUMERIC_TOKEN_PATTERN, line)
    if len(numeric_cells) >= 2:
        return True
    if len(numeric_cells) == 1:
        tokens = line.split()
        first_number = next((index for index, token in enumerate(tokens) if contains_number(token)), -1)
        return first_number > 0 and len(tokens) >= 2
    return False


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
