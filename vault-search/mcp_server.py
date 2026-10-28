"""
Vault RAG MCP server: exposes vault semantic search to Claude Code.
Start with: python3 mcp_server.py
"""
import os
import sys
import json
import chromadb
from chromadb.utils import embedding_functions

ECX_VAULT = os.path.expanduser(os.environ.get("ECX_VAULT", "~/vault"))   # your notes folder
ECX_DATA = os.path.expanduser(os.environ.get("ECX_DATA", "~/.ecx/index"))  # where indexes live

CHROMA_PATH = os.path.join(ECX_DATA, "chroma_db")
COLLECTION = "vault"
TOP_K = 5

_client = None
_col = None

def get_collection():
    global _client, _col
    if _col is None:
        _client = chromadb.PersistentClient(path=CHROMA_PATH)
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        _col = _client.get_collection(COLLECTION, embedding_function=ef)
    return _col

def search_vault(query: str, n: int = TOP_K) -> str:
    col = get_collection()
    results = col.query(query_texts=[query], n_results=n)
    docs = results["documents"][0]
    metas = results["metadatas"][0]
    out = []
    for doc, meta in zip(docs, metas):
        out.append(f"[{meta['source']}]\n{doc[:400]}")
    return "\n\n---\n\n".join(out)

VAULT = ECX_VAULT
_clip = None


def clip_text(text):
    """Text -> CLIP ViT-B-32 vector, same model multimodal_ingest.py indexes images with."""
    global _clip
    import torch
    if _clip is None:
        import open_clip
        model, _, _ = open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai")
        model.eval()
        _clip = (model, open_clip.get_tokenizer("ViT-B-32"))
    model, tok = _clip
    with torch.no_grad():
        emb = model.encode_text(tok([text]))
        emb = emb / emb.norm(dim=-1, keepdim=True)
    return emb[0].tolist()


def notes_embedding(rel):
    """Notes in the image's folder or its parent that embed it, so a hit can open the lecture note."""
    import os
    name = os.path.basename(rel)
    found = []
    folder = os.path.dirname(os.path.join(VAULT, rel))
    for d in {folder, os.path.dirname(folder)}:
        try:
            entries = os.listdir(d)
        except OSError:
            continue
        for f in entries:
            if f.endswith((".md", ".ipynb")):
                fp = os.path.join(d, f)
                try:
                    if name in open(fp, encoding="utf-8", errors="ignore").read():
                        found.append(os.path.relpath(fp, VAULT))
                except OSError:
                    pass
    return found[:3]


def search_images(query, n=TOP_K):
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    col = client.get_collection("vault_visual")
    res = col.query(query_embeddings=[clip_text(query)], n_results=n * 4)
    out, seen = [], set()
    for meta, dist in zip(res["metadatas"][0], res["distances"][0]):
        key = (meta["source"].rsplit("/", 1)[-1], meta.get("page"))   # same file copied in two folders
        if key in seen:
            continue
        seen.add(key)
        if len(out) == n:
            break
        line = f"[{meta['source']}]" + (f" page {meta['page'] + 1}" if meta.get("type") == "pdf_page" else "")
        line += f"  (similarity {1 - dist:.2f})"
        notes = notes_embedding(meta["source"]) if meta.get("type") == "image" else []
        if notes:
            line += "\n  appears in: " + ", ".join(notes)
        out.append(line)
    return "\n".join(out)


TOOLS = [
    {
        "name": "search_vault",
        "description": "Semantically search the Obsidian vault. Returns relevant excerpts from notes, research, trackers, and wiki articles.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to search for"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_images",
        "description": "Search the vault's images, lecture slides, screenshots and PDF pages by describing what's in them (CLIP). Returns file paths, PDF page numbers, and the notes each image appears in.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What the image shows, e.g. 'gradient descent diagram'"}
            },
            "required": ["query"]
        }
    }
]

def handle(req):
    method = req.get("method")
    rid = req.get("id")

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "vault-rag", "version": "1.0.0"}
        }}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}

    if method == "tools/call":
        name = req["params"]["name"]
        args = req["params"].get("arguments", {})
        if name in ("search_vault", "search_images"):
            try:
                result = (search_vault if name == "search_vault" else search_images)(args["query"])
                return {"jsonrpc": "2.0", "id": rid, "result": {
                    "content": [{"type": "text", "text": result}]
                }}
            except Exception as e:
                return {"jsonrpc": "2.0", "id": rid, "result": {
                    "content": [{"type": "text", "text": f"Error: {e}. Run ingest.py first."}]
                }}

    return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "Method not found"}}

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(req)
        print(json.dumps(resp), flush=True)

if __name__ == "__main__":
    main()
