#!/usr/bin/env python3.11
"""
LightRAG MCP server: exposes graph_search_vault tool to Claude Code.
"""

import asyncio
import json
import sys
import os
import aiohttp

ECX_VAULT = os.path.expanduser(os.environ.get("ECX_VAULT", "~/vault"))   # your notes folder
ECX_DATA = os.path.expanduser(os.environ.get("ECX_DATA", "~/.ecx/index"))  # where indexes live

DB_PATH = os.path.join(ECX_DATA, "lightrag_db")
OLLAMA_HOST = os.environ.get("ECX_OLLAMA_HOST", "http://localhost:11434")
LLM_MODEL = os.environ.get("ECX_LLM_MODEL", "gemma4:31b-cloud")   # free cloud model via `ollama signin`
EMBED_MODEL = os.environ.get("ECX_EMBED_MODEL", "nomic-embed-text")
EMBED_DIM = 768

_rag = None


async def _embed(texts, **kwargs):
    import numpy as np
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


async def get_rag():
    global _rag
    if _rag is None:
        from lightrag import LightRAG
        from lightrag.llm.ollama import ollama_model_complete
        from lightrag.utils import EmbeddingFunc

        os.makedirs(DB_PATH, exist_ok=True)
        _rag = LightRAG(
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
        await _rag.initialize_storages()
    return _rag


TOOLS = [
    {
        "name": "graph_search_vault",
        "description": (
            "Graph RAG search over the Obsidian vault. "
            "Uses entity-relationship graph: better than keyword search for "
            "multi-hop questions like 'how does X relate to Y'. "
            "mode: 'hybrid' (default), 'local', 'global', 'naive'."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "mode": {
                    "type": "string",
                    "enum": ["hybrid", "local", "global", "naive"],
                    "default": "hybrid",
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
                "serverInfo": {"name": "vault-graph", "version": "1.0.0"},
            },
        }

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}

    if method == "tools/call":
        params = msg.get("params", {})
        tool = params.get("name")
        args = params.get("arguments", {})

        if tool == "graph_search_vault":
            from lightrag import QueryParam
            query = args.get("query", "")
            mode = args.get("mode", "hybrid")
            try:
                rag = await get_rag()
                result = await rag.aquery(query, param=QueryParam(mode=mode))
                text = result if isinstance(result, str) else str(result)
            except Exception as e:
                text = f"Error: {e}"
            return {
                "jsonrpc": "2.0", "id": mid,
                "result": {"content": [{"type": "text", "text": text}]},
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
