import hashlib, json, time
from config import DATA

_FILE = DATA / "audit.jsonl"
_ZERO = "0" * 64


def _last_hash() -> str:
    if not _FILE.exists():
        return _ZERO
    last = ""
    with _FILE.open("rb") as f:
        for line in f:
            if line.strip():
                last = line.decode("utf-8")
    try:
        return json.loads(last).get("h", _ZERO) if last else _ZERO
    except Exception:
        return _ZERO


_prev = _last_hash()


def _hash(rec: dict) -> str:
    return hashlib.sha256(
        json.dumps(rec, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def log(event: str, **kw):
    global _prev
    rec = {"ts": time.time(), "event": event, **kw, "p": _prev}
    rec["h"] = _hash(rec)
    with _FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    _prev = rec["h"]


def verify() -> tuple[bool, int]:
    """Legacy (M0) lines without 'h' are skipped."""
    if not _FILE.exists():
        return True, 0
    prev, n = None, 0
    for line in _FILE.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        h = r.pop("h", None)
        if h is None:
            continue
        if _hash(r) != h or (prev is not None and r["p"] != prev):
            return False, n
        prev, n = h, n + 1
    return True, n
