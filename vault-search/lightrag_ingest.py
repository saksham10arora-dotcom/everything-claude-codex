#!/usr/bin/env python3.11
"""
LightRAG (Level 6 Graph RAG) ingest: incremental sync.
Only re-indexes files that changed since last run.
Run: python3.11 lightrag_ingest.py [--folder research studies personal]
"""

import asyncio
import os
import json
import argparse
import sys
from pathlib import Path
import aiohttp
import numpy as np

ECX_VAULT = os.path.expanduser(os.environ.get("ECX_VAULT", "~/vault"))   # your notes folder
ECX_DATA = os.path.expanduser(os.environ.get("ECX_DATA", "~/.ecx/index"))  # where indexes live

VAULT = Path(ECX_VAULT)
DB_PATH = os.path.join(ECX_DATA, "lightrag_db")
STATE_FILE = os.path.join(ECX_DATA, "lightrag_sync_state.json")
OLLAMA_HOST = os.environ.get("ECX_OLLAMA_HOST", "http://localhost:11434")
LLM_MODEL = os.environ.get("ECX_LLM_MODEL", "gemma4:31b-cloud")   # free cloud model via `ollama signin`
EMBED_MODEL = os.environ.get("ECX_EMBED_MODEL", "nomic-embed-text")
EMBED_DIM = 768


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


async def _embed(texts, **kwargs):
    if isinstance(texts, str):
        texts = [texts]
    async with aiohttp.ClientSession() as s:
        async with s.post(
            f"{OLLAMA_HOST}/api/embed",
            json={"model": EMBED_MODEL, "input": texts},
            timeout=aiohttp.ClientTimeout(total=60),
        ) as r:
            data = await r.json()
    return np.array(data["embeddings"], dtype=np.float32)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--folder",
        nargs="+",
        default=["research"],
        help="Vault subfolder(s) to index",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-index all files regardless of change",
    )
    args = parser.parse_args()

    from lightrag import LightRAG
    from lightrag.llm.ollama import ollama_model_complete
    from lightrag.utils import EmbeddingFunc, compute_mdhash_id
    from lightrag.base import DocStatus

    os.makedirs(DB_PATH, exist_ok=True)

    rag = LightRAG(
        working_dir=DB_PATH,
        llm_model_func=ollama_model_complete,
        llm_model_name=LLM_MODEL,
        llm_model_kwargs={"host": OLLAMA_HOST, "options": {"num_ctx": 8192}},
        embedding_func=EmbeddingFunc(
            embedding_dim=EMBED_DIM,
            max_token_size=8192,
            func=_embed,
        ),
    )
    await rag.initialize_storages()

    state = load_state()

    # LightRAG logs extraction errors without raising, so earlier runs left
    # docs FAILED while this script marked them done. Retry those first.
    before = await rag.doc_status.get_status_counts()
    if before.get("failed") or before.get("pending"):
        print(f"Retrying {before.get('failed', 0)} failed / {before.get('pending', 0)} pending docs...", flush=True)
        await rag.apipeline_process_enqueue_documents()

    files = []
    for folder in args.folder:
        target = VAULT / folder
        if not target.exists():
            print(f"Warning: {target} does not exist, skipping")
            continue
        for md in sorted(target.rglob("*.md")):
            files.append(md)

    # Filter to changed files only
    if not args.force:
        changed = [
            f for f in files
            if str(f) not in state or state[str(f)] != f.stat().st_mtime
        ]
        skipped = len(files) - len(changed)
        if skipped:
            print(f"Skipping {skipped} unchanged files")
        files = changed

    if not files:
        print("No changed files.", flush=True)

    print(f"Indexing {len(files)} changed files...", flush=True)

    for i, fpath in enumerate(files, 1):
        try:
            text = fpath.read_text(encoding="utf-8", errors="ignore").strip()
            if len(text) < 100:
                state[str(fpath)] = fpath.stat().st_mtime
                continue
            doc = f"Source: {fpath.relative_to(VAULT)}\n\n{text}"
            await rag.ainsert(doc)
            status = await rag.doc_status.get_by_id(compute_mdhash_id(doc, prefix="doc-"))
            if (status or {}).get("status") != "processed":
                print(f"[{i}/{len(files)}] FAILED {fpath.name}: {(status or {}).get('error_msg', 'no status')}"[:300], flush=True)
                continue
            state[str(fpath)] = fpath.stat().st_mtime
            print(f"[{i}/{len(files)}] indexed: {fpath.name}", flush=True)
        except Exception as e:
            print(f"[{i}/{len(files)}] ERROR {fpath.name}: {e}", flush=True)

    save_state(state)
    after = await rag.doc_status.get_status_counts()
    print(f"\nDone. Docs by status: {dict(after)}", flush=True)
    # "failed" also covers duplicate content (same text already indexed): not a real failure
    failed = await rag.doc_status.get_docs_by_status(DocStatus.FAILED)
    real = [k for k, v in failed.items() if not str(getattr(v, "error_msg", "") or "").startswith("Content already exists")]
    if real:
        print(f"WARNING: {len(real)} docs FAILED (is Ollama running and signed in?)", flush=True)
        sys.exit(1)
    await rag.finalize_storages()


if __name__ == "__main__":
    asyncio.run(main())
