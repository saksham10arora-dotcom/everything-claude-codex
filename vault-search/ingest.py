"""
Vault RAG ingestion: ChromaDB with incremental sync.
Only re-indexes files that changed since last run.
"""
import os
import re
import json
import chromadb
from chromadb.utils import embedding_functions

ECX_VAULT = os.path.expanduser(os.environ.get("ECX_VAULT", "~/vault"))   # your notes folder
ECX_DATA = os.path.expanduser(os.environ.get("ECX_DATA", "~/.ecx/index"))  # where indexes live

VAULT_PATH = ECX_VAULT
CHROMA_PATH = os.path.join(ECX_DATA, "chroma_db")
COLLECTION = "vault"
STATE_FILE = os.path.join(ECX_DATA, "chroma_sync_state.json")

SKIP_DIRS = {".claude", ".obsidian", ".git", "archive",
             ".agents", "node_modules", "graphify-out", ".margin-history", ".superpowers", ".impeccable"}
SKIP_FILES = {"MEMORY.md"}


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def chunk_markdown(text, max_tokens=400):
    sections = re.split(r'\n(?=#{1,3} )', text)
    chunks = []
    for section in sections:
        section = section.strip()
        if not section or len(section) < 50:
            continue
        words = section.split()
        for i in range(0, len(words), max_tokens):
            chunks.append(" ".join(words[i:i + max_tokens]))
    return chunks


def scan_vault():
    files = {}
    for root, dirs, filenames in os.walk(VAULT_PATH):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in filenames:
            if not fname.endswith(".md") or fname in SKIP_FILES:
                continue
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, VAULT_PATH)
            files[rel] = os.path.getmtime(fpath)
    return files


def main():
    state = load_state()
    current = scan_vault()

    changed = [f for f, mtime in current.items() if state.get(f) != mtime]
    deleted = [f for f in state if f not in current]

    if not changed and not deleted:
        print("Nothing changed. Index up to date.")
        return

    print(f"Changed: {len(changed)} | Deleted: {len(deleted)}")

    client = chromadb.PersistentClient(path=CHROMA_PATH)
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )

    if COLLECTION not in [c.name for c in client.list_collections()]:
        col = client.create_collection(COLLECTION, embedding_function=ef)
    else:
        col = client.get_collection(COLLECTION, embedding_function=ef)

    # Delete stale chunks for changed + deleted files
    stale = changed + deleted
    if stale:
        col.delete(where={"source": {"$in": stale}})
        print(f"Deleted old chunks for {len(stale)} files")

    # Re-index changed files
    for rel in changed:
        fpath = os.path.join(VAULT_PATH, rel)
        try:
            with open(fpath, encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            print(f"  ERROR reading {rel}: {e}")
            continue
        chunks = chunk_markdown(text)
        if not chunks:
            continue
        col.add(
            documents=chunks,
            metadatas=[{"source": rel, "chunk": i} for i in range(len(chunks))],
            ids=[f"{rel}::{i}" for i in range(len(chunks))],
        )
        print(f"  indexed: {rel} ({len(chunks)} chunks)")

    # Update state
    new_state = {f: mtime for f, mtime in current.items()}
    save_state(new_state)
    print(f"Done. {col.count()} total chunks in index.")


if __name__ == "__main__":
    main()
