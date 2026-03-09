"""
ChromaDB vector store with OpenAI embeddings.
Supports filtered retrieval by document type.
"""
import os
import chromadb
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

CHROMA_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed", "chroma_db")
COLLECTION_NAME = "ppe_safety_documents"

_client = None


def _get_openai_client():
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


def get_embedding(text: str) -> list:
    """Embed a single text."""
    client = _get_openai_client()
    response = client.embeddings.create(input=text, model="text-embedding-3-small")
    return response.data[0].embedding


def get_embeddings_batch(texts: list, batch_size: int = 100) -> list:
    """Batch embed for cost-efficient ingestion."""
    client = _get_openai_client()
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        response = client.embeddings.create(input=batch, model="text-embedding-3-small")
        all_embeddings.extend([d.embedding for d in response.data])
        print(f"  Embedded {len(all_embeddings)}/{len(texts)}")
    return all_embeddings


def init_vectorstore():
    """Initialize or load the persistent ChromaDB collection."""
    abs_path = os.path.abspath(CHROMA_PATH)
    os.makedirs(abs_path, exist_ok=True)
    chroma_client = chromadb.PersistentClient(path=abs_path)
    collection = chroma_client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    return collection


def ingest_chunks(chunks: list):
    """Embed and store document chunks in ChromaDB."""
    collection = init_vectorstore()

    ids = [c["id"] for c in chunks]
    documents = [c["content"] for c in chunks]
    metadatas = [c["metadata"] for c in chunks]

    # Skip already-ingested chunks
    existing = set()
    try:
        result = collection.get(ids=ids)
        if result and result.get("ids"):
            existing = set(result["ids"])
    except Exception:
        pass

    new_idx = [i for i, id_ in enumerate(ids) if id_ not in existing]
    if not new_idx:
        print("All chunks already in vector store. Skipping.")
        return

    new_ids = [ids[i] for i in new_idx]
    new_docs = [documents[i] for i in new_idx]
    new_metas = [metadatas[i] for i in new_idx]

    print(f"Embedding {len(new_docs)} new chunks...")
    embeddings = get_embeddings_batch(new_docs)

    collection.add(
        ids=new_ids,
        documents=new_docs,
        embeddings=embeddings,
        metadatas=new_metas,
    )
    print(f"Ingested {len(new_ids)} chunks. Total in store: {collection.count()}")


def retrieve(query: str, n_results: int = 5, doc_type: str = None) -> list:
    """Retrieve relevant chunks for a query."""
    collection = init_vectorstore()

    if collection.count() == 0:
        print("Warning: Vector store is empty. Run ingest.py first.")
        return []

    query_embedding = get_embedding(query)
    where_filter = {"doc_type": doc_type} if doc_type else None

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(n_results, collection.count()),
        where=where_filter,
        include=["documents", "metadatas", "distances"],
    )

    retrieved = []
    if results and results["ids"] and results["ids"][0]:
        for i in range(len(results["ids"][0])):
            retrieved.append({
                "content": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "score": 1 - results["distances"][0][i],
            })
    return retrieved
