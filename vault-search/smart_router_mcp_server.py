#!/usr/bin/env python3.11
"""
Level 7: Smart Router MCP server.
Routes queries to ChromaDB (vector) or LightRAG (graph) based on query type.
ChromaDB uses nomic-embed-text (768-dim, via Ollama): swap to Gemini Embedding 2
once billing is enabled on the Google Cloud project.
"""

import asyncio
import json
import sys
import os
import re
import aiohttp
import numpy as np

ECX_VAULT = os.path.expanduser(os.environ.get("ECX_VAULT", "~/vault"))   # your notes folder
ECX_DATA = os.path.expanduser(os.environ.get("ECX_DATA", "~/.ecx/index"))  # where indexes live

CHROMA_PATH = os.path.join(ECX_DATA, "chroma_db")
LIGHTRAG_DB = os.path.join(ECX_DATA, "lightrag_db")
OLLAMA_HOST = os.environ.get("ECX_OLLAMA_HOST", "http://localhost:11434")
LLM_MODEL = os.environ.get("ECX_LLM_MODEL", "gemma4:31b-cloud")   # free cloud model via `ollama signin`
EMBED_MODEL = os.environ.get("ECX_EMBED_MODEL", "nomic-embed-text")
EMBED_DIM = 768

# --- Query classifier ---
GRAPH_SIGNALS = re.compile(
    r"\b(how does|relate[sd]? to|relationship|connected|impact of|compare|"
    r"across|between|depend|influence|cause|effect|why does|explain how|"
    r"link between|interplay|contrast)\b",
    re.IGNORECASE,
)
VECTOR_SIGNALS = re.compile(
    r"\b(find|exact|where is|what is|show me|definition|syntax|example|"
    r"snippet|code for|list|give me|tell me about|what does)\b",
    re.IGNORECASE,
)

def classify_query(query: str) -> str:
    g = len(GRAPH_SIGNALS.findall(query))
    v = len(VECTOR_SIGNALS.findall(query))
    if g > v:
        return "graph"
    if v > g:
        return "vector"
    return "hybrid"


# --- Embed via sentence-transformers (matches vault collection: all-MiniLM-L6-v2, 384-dim) ---
_st_model = None

def _embed_query(text: str):
    global _st_model
    if _st_model is None:
        from sentence_transformers import SentenceTransformer
        _st_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _st_model.encode([text])[0].tolist()


# --- ChromaDB search ---
async def vector_search(query: str, n_results: int = 5) -> str:
    import chromadb
    emb = _embed_query(query)
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    col = client.get_or_create_collection("vault")
    results = col.query(query_embeddings=[emb], n_results=n_results)
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    parts = [f"[{m.get('source','?')}]\n{d}" for d, m in zip(docs, metas)]
    return "\n\n---\n\n".join(parts)


# --- LightRAG search ---
_rag = None

async def graph_search(query: str, mode: str = "hybrid") -> str:
    global _rag
    if _rag is None:
        from lightrag import LightRAG
        from lightrag.llm.ollama import ollama_model_complete
        from lightrag.utils import EmbeddingFunc

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

        os.makedirs(LIGHTRAG_DB, exist_ok=True)
        _rag = LightRAG(
            working_dir=LIGHTRAG_DB,
            llm_model_func=ollama_model_complete,
            llm_model_name=LLM_MODEL,
            llm_model_kwargs={"host": OLLAMA_HOST, "options": {"num_ctx": 8192}},
            embedding_func=EmbeddingFunc(
                embedding_dim=EMBED_DIM,
                max_token_size=8192,
                func=_embed,
            ),
        )
        await _rag.initialize_storages()

    from lightrag import QueryParam
    result = await _rag.aquery(query, param=QueryParam(mode=mode))
    return result if isinstance(result, str) else str(result)


TOOLS = [
    {
        "name": "smart_search_vault",
        "description": (
            "Level 7 smart search over the Obsidian vault. "
            "Auto-routes: vector RAG (text+visual) for factual lookups, "
            "graph RAG (LightRAG) for relationship/conceptual queries, "
            "hybrid for ambiguous. Use this as the primary vault search tool."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "force_mode": {
                    "type": "string",
                    "enum": ["auto", "vector", "graph", "hybrid"],
                    "default": "auto",
                },
            },
            "required": ["query"],
        },
    }
]


async def handle_message(msg):
    method = msg.get("method")
    mid = msg.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": mid,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "vault-smart-router", "version": "1.0.0"},
            },
        }

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}

    if method == "tools/call":
        params = msg.get("params", {})
        if params.get("name") != "smart_search_vault":
            return {"jsonrpc": "2.0", "id": mid,
                    "error": {"code": -32601, "message": "Unknown tool"}}

        args = params.get("arguments", {})
        query = args.get("query", "")
        force = args.get("force_mode", "auto")
        mode = classify_query(query) if force == "auto" else force

        text_parts = [f"[Router → {mode}]"]

        if mode in ("vector", "hybrid"):
            try:
                v = await vector_search(query)
                text_parts.append(f"## Vector Results\n{v}")
            except Exception as e:
                text_parts.append(f"## Vector Error\n{e}")

        if mode in ("graph", "hybrid"):
            try:
                g = await graph_search(query)
                text_parts.append(f"## Graph Results\n{g}")
            except Exception as e:
                text_parts.append(f"## Graph Error\n{e}")

        return {
            "jsonrpc": "2.0", "id": mid,
            "result": {"content": [{"type": "text", "text": "\n\n".join(text_parts)}]},
        }

    return {
        "jsonrpc": "2.0", "id": mid,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


async def run_stdio():
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    proto = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: proto, sys.stdin)

    buffer = b""
    while True:
        try:
            chunk = await asyncio.wait_for(reader.read(4096), timeout=1.0)
        except asyncio.TimeoutError:
            continue
        if not chunk:
            break
        buffer += chunk
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            resp = await handle_message(msg)
            if resp is not None:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()


if __name__ == "__main__":
    asyncio.run(run_stdio())
