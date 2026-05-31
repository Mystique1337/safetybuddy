"""Recursive character chunker with overlap for the RAG pipeline.

Dependency-free re-implementation of the recursive-character splitting strategy
(split on the largest natural boundary that keeps pieces under the size limit,
then merge with overlap), so ingestion needs no LangChain.
"""
from src.config import settings

SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


def _recursive_split(text: str, chunk_size: int, separators: list) -> list:
    """Split text into pieces no larger than chunk_size, preferring high-level
    separators (paragraphs > lines > sentences > words > characters)."""
    if len(text) <= chunk_size:
        return [text] if text else []

    sep = separators[0]
    rest = separators[1:]
    if sep == "":  # last resort: hard character split
        return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]

    pieces = []
    for part in text.split(sep):
        seg = part + sep
        if len(seg) > chunk_size and rest:
            pieces.extend(_recursive_split(part, chunk_size, rest))
        elif seg.strip():
            pieces.append(seg)
    return pieces


def _merge_with_overlap(pieces: list, chunk_size: int, overlap: int) -> list:
    """Greedily merge small pieces up to chunk_size, carrying an overlap tail."""
    chunks, cur = [], ""
    for p in pieces:
        if cur and len(cur) + len(p) > chunk_size:
            chunks.append(cur.strip())
            cur = (cur[-overlap:] if overlap else "") + p
        else:
            cur += p
    if cur.strip():
        chunks.append(cur.strip())
    return chunks


def chunk_documents(documents: list, chunk_size: int = None, chunk_overlap: int = None) -> list:
    """
    Chunk documents for embedding and retrieval.

    Args:
        documents: List of Document objects from document_loader
        chunk_size: Target characters per chunk (defaults to config RAG_CHUNK_CHARS)
        chunk_overlap: Overlap characters between chunks (defaults to config)
    """
    chunk_size = chunk_size or settings.chunk_chars
    chunk_overlap = chunk_overlap if chunk_overlap is not None else settings.chunk_overlap

    chunks = []
    for doc in documents:
        pieces = _recursive_split(doc.content, chunk_size, SEPARATORS)
        texts = _merge_with_overlap(pieces, chunk_size, chunk_overlap)
        for i, text in enumerate(texts):
            meta = {
                **doc.metadata,
                "chunk_index": i,
                "total_chunks": len(texts),
                "doc_id": doc.doc_id or doc.metadata.get("filename", "unknown"),
            }
            chunks.append({
                "content": text,
                "metadata": meta,
                "id": f"{meta['doc_id']}_chunk{i}",
            })
    print(f"Created {len(chunks)} chunks from {len(documents)} document segments")
    return chunks
