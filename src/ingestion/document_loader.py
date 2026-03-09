"""
Document loader for PDFs, text files, and JSON incident logs.
Extracts text with metadata for the RAG pipeline.
"""
import os
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None


@dataclass
class Document:
    content: str
    metadata: dict = field(default_factory=dict)
    doc_id: Optional[str] = None


def classify_document(filename: str) -> str:
    """Classify document type based on filename for retrieval filtering."""
    name = filename.lower()
    if any(k in name for k in ["1910", "osha3", "cfr", "regulation", "cpl", "enforcement"]):
        return "regulation"
    elif any(k in name for k in ["sop", "procedure"]):
        return "operating_procedure"
    elif any(k in name for k in ["incident", "accident", "violation"]):
        return "incident_report"
    elif any(k in name for k in ["manual", "safety", "guide", "handbook", "factsheet"]):
        return "safety_manual"
    return "general"


def load_pdf(filepath: str) -> list:
    """Extract text from PDF page-by-page with metadata."""
    if fitz is None:
        print(f"  Warning: PyMuPDF not installed, skipping {filepath}")
        return []
    docs = []
    pdf = fitz.open(filepath)
    filename = Path(filepath).stem
    for page_num, page in enumerate(pdf):
        text = page.get_text("text").strip()
        if not text or len(text) < 50:
            continue
        docs.append(Document(
            content=text,
            metadata={
                "source": filepath,
                "filename": filename,
                "page": page_num + 1,
                "total_pages": len(pdf),
                "doc_type": classify_document(filename),
            },
            doc_id=f"{filename}_p{page_num + 1}",
        ))
    pdf.close()
    return docs


def load_text_file(filepath: str) -> list:
    """Load a .txt file as a single document."""
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        content = f.read().strip()
    if not content:
        return []
    filename = Path(filepath).stem
    return [Document(
        content=content,
        metadata={
            "source": filepath,
            "filename": filename,
            "doc_type": classify_document(filename),
        },
        doc_id=filename,
    )]


def load_incident_json(filepath: str) -> list:
    """Load structured incident logs from JSON."""
    with open(filepath, "r") as f:
        records = json.load(f)
    docs = []
    for i, record in enumerate(records):
        parts = []
        for key, value in record.items():
            if value and str(value).strip() and str(value) != "nan":
                parts.append(f"{key}: {value}")
        text = "\n".join(parts)
        if text:
            docs.append(Document(
                content=text,
                metadata={
                    "source": filepath,
                    "filename": Path(filepath).stem,
                    "doc_type": "incident_report",
                    "incident_id": record.get("id", str(i)),
                },
                doc_id=f"incident_{record.get('id', i)}",
            ))
    return docs


def load_directory(dir_path: str) -> list:
    """Recursively load all supported files from a directory."""
    all_docs = []
    for root, dirs, files in os.walk(dir_path):
        # Skip image directories
        if "images" in root:
            continue
        for file in sorted(files):
            filepath = os.path.join(root, file)
            try:
                if file.lower().endswith(".pdf"):
                    loaded = load_pdf(filepath)
                    if loaded:
                        print(f"  Loaded PDF: {file} ({len(loaded)} pages)")
                    all_docs.extend(loaded)
                elif file.lower().endswith(".txt"):
                    loaded = load_text_file(filepath)
                    if loaded:
                        print(f"  Loaded TXT: {file}")
                    all_docs.extend(loaded)
                elif file.lower().endswith(".json"):
                    loaded = load_incident_json(filepath)
                    if loaded:
                        print(f"  Loaded JSON: {file} ({len(loaded)} records)")
                    all_docs.extend(loaded)
            except Exception as e:
                print(f"  Warning: Failed to load {file}: {e}")
    print(f"\nTotal: {len(all_docs)} document segments from {dir_path}")
    return all_docs
