"""
Ingest all PPE documents into the ChromaDB vector store.
Run once before launching the app:  python ingest.py
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.ingestion.document_loader import load_directory
from src.ingestion.chunker import chunk_documents
from src.rag.vectorstore import ingest_chunks


def main():
    print("=" * 55)
    print("  SafetyBuddy — PPE Document Ingestion")
    print("=" * 55)

    data_dir = os.path.join(os.path.dirname(__file__), "data", "raw")

    print(f"\n[1/3] Loading documents from {data_dir}...")
    documents = load_directory(data_dir)

    if not documents:
        print("\n❌ ERROR: No documents found!")
        print("Add files to these directories:")
        print("  data/raw/regulations/  — OSHA PDFs and .txt files")
        print("  data/raw/manuals/      — SOP .txt files")
        print("  data/raw/incident_logs/ — Incident .json files")
        print("\nSee README.md for data sourcing instructions.")
        return

    print(f"\n[2/3] Chunking {len(documents)} documents...")
    chunks = chunk_documents(documents)

    print(f"\n[3/3] Ingesting {len(chunks)} chunks into ChromaDB...")
    ingest_chunks(chunks)

    print("\n" + "=" * 55)
    print("  ✅ Ingestion complete!")
    print("  Run the app:  streamlit run src/ui/app.py")
    print("=" * 55)


if __name__ == "__main__":
    main()
