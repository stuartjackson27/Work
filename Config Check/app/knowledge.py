"""Knowledge base: design-doc sections + template blocks, embedded for retrieval."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .common import DATA, KNOWLEDGE
from .rules import Block


@dataclass
class Passage:
    ref: str        # e.g. "HLD-evpn-fabric §5 Overlay"
    text: str


def _design_passages(files: list[Path]) -> list[Passage]:
    out = []
    for f in files:
        doc = f.stem
        heading, buf = "", []

        def flush():
            body = "\n".join(buf).strip()
            if body:
                num = re.match(r"(\d+(?:\.\d+)*)\s+(.*)", heading)
                ref = f"{doc} §{num.group(1)} {num.group(2)}" if num else f"{doc} {heading}".strip()
                out.append(Passage(ref=ref, text=f"[{ref}]\n{body}"))

        for line in f.read_text().splitlines():
            m = re.match(r"^#{1,4}\s+(.*)", line)
            if m:
                flush()
                heading, buf = m.group(1).strip(), []
            else:
                buf.append(line)
        flush()
    return out


def design_files(selectors: list[str] | None) -> list[Path]:
    base = KNOWLEDGE
    if selectors:
        return [base / s for s in selectors if (base / s).is_file()]
    return sorted([*base.glob("design/**/*.md"), *base.glob("design/**/*.txt")])


class Retriever:
    """Cosine search over passages. Embeddings are cached on disk by content hash."""

    def __init__(self, ollama, embed_model: str):
        self.ollama = ollama
        self.model = embed_model
        self.cache_file = DATA / "embed_cache.json"
        try:
            self.cache = json.loads(self.cache_file.read_text())
        except Exception:
            self.cache = {}
        self.passages: list[Passage] = []
        self.matrix: np.ndarray | None = None

    def _key(self, text: str) -> str:
        return hashlib.sha1(f"{self.model}|{text}".encode()).hexdigest()

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        todo = [t for t in texts if self._key(t) not in self.cache]
        for i in range(0, len(todo), 16):
            batch = todo[i:i + 16]
            vecs = await self.ollama.embed(self.model, batch)
            for t, v in zip(batch, vecs):
                self.cache[self._key(t)] = v
        if todo:
            DATA.mkdir(parents=True, exist_ok=True)
            self.cache_file.write_text(json.dumps(self.cache))
        return [self.cache[self._key(t)] for t in texts]

    async def build(self, design: list[Path], blocks: list[Block]) -> int:
        self.passages = _design_passages(design) + [
            Passage(ref=f"template {b.source_file} {b.id}", text=b.text()) for b in blocks]
        vecs = await self._embed([p.text for p in self.passages])
        m = np.array(vecs, dtype=np.float32)
        self.matrix = m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-9)
        return len(self.passages)

    async def search(self, query: str, k: int = 4) -> list[Passage]:
        if self.matrix is None or not len(self.passages):
            return []
        q = np.array((await self._embed([query[:4000]]))[0], dtype=np.float32)
        q /= np.linalg.norm(q) + 1e-9
        idx = np.argsort(-(self.matrix @ q))[:k]
        return [self.passages[i] for i in idx]
