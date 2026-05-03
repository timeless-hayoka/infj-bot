"""Document ingestion and retrieval for the INFJ companion."""
import json
import re
import uuid
from pathlib import Path
from typing import List, Optional

import chromadb

from config import PROJECT_ROOT
from memory import LocalEmbeddingFunction

SUPPORTED_TEXT = {".txt", ".md", ".py", ".js", ".ts", ".jsx", ".tsx", ".json", ".yaml", ".yml", ".csv", ".sh", ".html", ".css", ".rs", ".go", ".java", ".c", ".cpp", ".h"}
MAX_INGEST_FILE_BYTES = 2_000_000
MAX_DIRECTORY_FILES = 300


def _is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _resolve_ingest_path(path: str) -> Path:
    target = Path(path).expanduser()
    if not target.is_absolute():
        target = PROJECT_ROOT / target
    target = target.resolve()
    allowed_roots = [PROJECT_ROOT.resolve(), Path.home().resolve()]
    if not any(_is_relative_to(target, root) for root in allowed_roots):
        raise PermissionError(f"Path {path} is outside the allowed ingestion roots.")
    return target


def _chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> List[str]:
    """Split text into overlapping chunks by paragraphs."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks = []
    current = []
    current_len = 0
    for para in paragraphs:
        para_len = len(para)
        if current_len + para_len > chunk_size and current:
            chunks.append("\n\n".join(current))
            # Keep overlap
            overlap_text = []
            overlap_len = 0
            for p in reversed(current):
                if overlap_len + len(p) > overlap:
                    break
                overlap_text.insert(0, p)
                overlap_len += len(p)
            current = overlap_text
            current_len = overlap_len
        current.append(para)
        current_len += para_len
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _read_pdf(path: Path) -> str:
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(str(path))
        parts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                parts.append(text)
        return "\n\n".join(parts)
    except Exception as exc:
        raise RuntimeError(f"PDF read failed: {exc}")


def _read_file(path: Path) -> str:
    if path.stat().st_size > MAX_INGEST_FILE_BYTES:
        raise ValueError(f"File too large for ingestion: {path} ({path.stat().st_size} bytes)")
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _read_pdf(path)
    return path.read_text(encoding="utf-8", errors="replace")


class DocumentStore:
    def __init__(self, persist_directory=None, embedding_function=None):
        if persist_directory is None:
            persist_directory = str(PROJECT_ROOT / "chroma_db")
        if embedding_function is None:
            embedding_function = LocalEmbeddingFunction()
        self.client = chromadb.PersistentClient(path=persist_directory)
        self.collection = self.client.get_or_create_collection(
            name="infj_documents",
            embedding_function=embedding_function,
        )

    def ingest(self, file_path: str, tags: Optional[List[str]] = None) -> int:
        path = _resolve_ingest_path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Not found: {path}")
        if path.is_dir():
            return self.ingest_directory(path, tags=tags)

        text = _read_file(path)
        if not text.strip():
            return 0

        chunks = _chunk_text(text)
        if not chunks:
            return 0

        ids = [f"doc-{uuid.uuid4().hex[:12]}" for _ in chunks]
        metadatas = []
        for i, _chunk in enumerate(chunks):
            meta = {
                "source": str(path),
                "filename": path.name,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "tags": ",".join(tags or []),
            }
            metadatas.append(meta)

        self.collection.add(
            documents=chunks,
            ids=ids,
            metadatas=metadatas,
        )
        return len(chunks)

    def ingest_directory(self, dir_path: Path, tags: Optional[List[str]] = None, recursive: bool = True) -> int:
        total = 0
        scanned = 0
        pattern = "**/*" if recursive else "*"
        for child in Path(dir_path).glob(pattern):
            if child.is_file() and child.suffix.lower() in SUPPORTED_TEXT | {".pdf"}:
                scanned += 1
                if scanned > MAX_DIRECTORY_FILES:
                    raise ValueError(f"Directory ingestion stopped after {MAX_DIRECTORY_FILES} supported files.")
                try:
                    n = self.ingest(str(child), tags=tags)
                    total += n
                except Exception as exc:
                    print(f"[ingest skip] {child}: {exc}")
        return total

    def search(self, query: str, n_results: int = 5) -> List[dict]:
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
        )
        out = []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i]
            out.append({
                "document": doc,
                "source": meta.get("source", "?"),
                "filename": meta.get("filename", "?"),
                "chunk_index": meta.get("chunk_index", 0),
            })
        return out

    def list_sources(self) -> List[str]:
        results = self.collection.get(include=["metadatas"])
        sources = set()
        for meta in results.get("metadatas", []):
            if meta:
                sources.add(meta.get("source", "?"))
        return sorted(sources)

    def delete_source(self, source_path: str) -> int:
        results = self.collection.get(
            where={"source": source_path},
            include=[],
        )
        ids = results.get("ids", [])
        if ids:
            self.collection.delete(ids=ids)
        return len(ids)

    def count(self) -> int:
        return self.collection.count()


def format_doc_results(results: List[dict]) -> str:
    if not results:
        return "No matching documents found."
    lines = []
    for r in results:
        lines.append(f"[{r['filename']} chunk {r['chunk_index']}]\n{r['document'][:600]}")
    return "\n---\n".join(lines)


if __name__ == "__main__":
    store = DocumentStore()
    print(f"Document store initialized. Documents: {store.count()}")
