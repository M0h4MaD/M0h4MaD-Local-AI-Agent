import os
from pathlib import Path
from config import SANDBOX, RO_ROOTS

class SandboxError(Exception): ...

BASE = Path(__file__).resolve().parent.parent   # project root: holds .env, audit log
_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
             *(f"lpt{i}" for i in range(1, 10))}
_DENY_SUFFIX = {".pem", ".key", ".pfx", ".p12", ".kdbx"}

def _inside(p: Path, root: Path) -> bool:
    return p == root or root in p.parents

def safe_path(rel: str, write: bool = False) -> Path:
    if os.path.isabs(rel) or ":" in rel or rel.startswith(("\\", "/")):
        raise SandboxError("absolute/drive path rejected")
    parts = Path(rel).parts
    if any(part.split(".")[0].lower() in _RESERVED for part in parts):
        raise SandboxError("reserved name rejected")
    root, ro = SANDBOX.resolve(), False
    if parts and parts[0].lower() in RO_ROOTS:
        root, ro = RO_ROOTS[parts[0].lower()].resolve(), True
        rel = str(Path(*parts[1:]))
    if ro and write:
        raise SandboxError("read-only root")
    p = (root / rel).resolve()
    if not _inside(p, root):
        raise SandboxError("path escapes root")
    if ro:
        if _inside(p, BASE) and not _inside(p, SANDBOX.resolve()):
            raise SandboxError("protected: agent's own files")
        if p.name.lower().startswith(".env") or p.suffix.lower() in _DENY_SUFFIX:
            raise SandboxError("denied file type")
    return p

def resolve_existing(rel: str) -> str:
    """Map a loosely typed name to an existing top-level sandbox file: exact > +.txt > unique normalized match."""
    rel = (rel or "").strip().strip("\"'")
    try:
        if safe_path(rel).exists():
            return rel
        if safe_path(rel + ".txt").exists():
            return rel + ".txt"
    except SandboxError:
        return rel
    norm = lambda s: s.lower().replace("_", " ").replace("-", " ")
    want = {norm(rel), norm(rel + ".txt")}
    hits = [p.name for p in SANDBOX.resolve().iterdir() if p.is_file() and norm(p.name) in want]
    return hits[0] if len(hits) == 1 else rel