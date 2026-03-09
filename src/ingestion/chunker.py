"""
Smart document chunker with overlap for RAG pipeline.
"""
try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:
    from langchain.text_splitter import RecursiveCharacterTextSplitter


def chunk_documents(documents: list, chunk_size: int = 1000, chunk_overlap: int = 200) -> list:
    """
    Chunk documents for embedding and retrieval.

    Args:
        documents: List of Document objects from document_loader
        chunk_size: 1000 chars captures a full procedure step or regulation clause
        chunk_overlap: 200 chars preserves context across chunk boundaries
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " "],
        length_function=len,
    )
    chunks = []
    for doc in documents:
        texts = splitter.split_text(doc.content)
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
