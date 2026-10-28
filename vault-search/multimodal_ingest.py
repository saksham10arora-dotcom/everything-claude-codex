#!/usr/bin/env python3.11
"""
Multimodal indexing: PDFs and images → ChromaDB via CLIP (ViT-B-32).
Stores in 'vault_visual' collection (512-dim).
Text queries work against image embeddings because CLIP aligns both spaces.
Run: python3.11 multimodal_ingest.py
"""

import os
import json
import base64
import io
from pathlib import Path

import torch
import open_clip
from PIL import Image
import fitz  # pymupdf
import chromadb

ECX_VAULT = os.path.expanduser(os.environ.get("ECX_VAULT", "~/vault"))   # your notes folder
ECX_DATA = os.path.expanduser(os.environ.get("ECX_DATA", "~/.ecx/index"))  # where indexes live

VAULT = Path(ECX_VAULT)
CHROMA_PATH = os.path.join(ECX_DATA, "chroma_db")
COLLECTION = "vault_visual"
STATE_FILE = os.path.join(ECX_DATA, "visual_sync_state.json")
EMBED_DIM = 512

SUPPORTED_IMAGE = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
SUPPORTED_PDF = {".pdf"}

# Load CLIP once
print("Loading CLIP (ViT-B-32)...")
model, _, preprocess = open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai")
tokenizer = open_clip.get_tokenizer("ViT-B-32")
model.eval()
print("CLIP ready.")


def embed_image(pil_img: Image.Image) -> list:
    img_tensor = preprocess(pil_img).unsqueeze(0)
    with torch.no_grad():
        emb = model.encode_image(img_tensor)
        emb = emb / emb.norm(dim=-1, keepdim=True)
    return emb[0].tolist()


def embed_text(text: str) -> list:
    tokens = tokenizer([text])
    with torch.no_grad():
        emb = model.encode_text(tokens)
        emb = emb / emb.norm(dim=-1, keepdim=True)
    return emb[0].tolist()


def pdf_to_images(fpath: Path, dpi: int = 150):
    doc = fitz.open(str(fpath))
    images = []
    for page in doc:
        pix = page.get_pixmap(dpi=dpi)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(img)
    doc.close()
    return images


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def main():
    state = load_state()

    client = chromadb.PersistentClient(path=CHROMA_PATH)
    if COLLECTION not in [c.name for c in client.list_collections()]:
        col = client.create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
    else:
        col = client.get_collection(COLLECTION)

    # Scan vault for PDFs and images
    targets = []
    for ext_set in [SUPPORTED_PDF, SUPPORTED_IMAGE]:
        for ext in ext_set:
            targets.extend(VAULT.rglob(f"*{ext}"))

    changed = [f for f in targets if state.get(str(f)) != f.stat().st_mtime]
    skipped = len(targets) - len(changed)
    if skipped:
        print(f"Skipping {skipped} unchanged files")
    if not changed:
        print("Nothing to index.")
        return

    print(f"Indexing {len(changed)} files...")

    for fpath in changed:
        rel = str(fpath.relative_to(VAULT))
        ext = fpath.suffix.lower()
        try:
            # Delete old entries for this file
            col.delete(where={"source": rel})

            if ext in SUPPORTED_PDF:
                pages = pdf_to_images(fpath)
                for i, img in enumerate(pages):
                    emb = embed_image(img)
                    col.add(
                        ids=[f"{rel}::page{i}"],
                        embeddings=[emb],
                        documents=[f"Page {i+1} of {fpath.name}"],
                        metadatas=[{"source": rel, "type": "pdf_page", "page": i}],
                    )
                print(f"  PDF: {fpath.name} ({len(pages)} pages)")

            elif ext in SUPPORTED_IMAGE:
                img = Image.open(fpath).convert("RGB")
                emb = embed_image(img)
                col.add(
                    ids=[f"{rel}::img"],
                    embeddings=[emb],
                    documents=[fpath.name],
                    metadatas=[{"source": rel, "type": "image"}],
                )
                print(f"  IMG: {fpath.name}")

            state[str(fpath)] = fpath.stat().st_mtime

        except Exception as e:
            print(f"  ERROR {fpath.name}: {e}")

    save_state(state)
    print(f"\nDone. {col.count()} visual chunks in '{COLLECTION}'")


if __name__ == "__main__":
    main()
