import subprocess
from config import APP_ALLOWLIST
from tools.registry import tool, Level
from tools.sandbox import safe_path

MAX_READ = 20_000
_P = {
    "type": "string",
    "minLength": 1,
    "maxLength": 200,
    "description": "relative path inside the sandbox",
}


@tool(
    "list_dir",
    Level.READ,
    {"path": {"type": "string", "maxLength": 200}},
    untrusted=True,
)
def list_dir(path: str = ".") -> str:
    """List files in a sandbox directory (default: root)."""
    p = safe_path(path)
    return (
        "\n".join(
            sorted(x.name + ("/" if x.is_dir() else "") for x in p.iterdir())[:200]
        )
        or "(empty)"
    )


@tool("read_file", Level.READ, {"path": _P}, ["path"], untrusted=True)
def read_file(path: str) -> str:
    """Read a text file from the sandbox."""
    return safe_path(path).read_bytes()[:MAX_READ].decode("utf-8", errors="replace")


@tool(
    "write_file",
    Level.MODIFY,
    {
        "path": _P,
        "text": {"type": "string", "maxLength": 20000, "description": "file content"},
    },
    ["path", "text"],
)
def write_file(path: str, text: str) -> str:
    """Create a new text file in the sandbox. Fails if it already exists."""
    p = safe_path(path, write=True)
    if p.exists():
        raise FileExistsError("exists; delete first")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return f"written {len(text)} chars"


@tool("delete_file", Level.DESTRUCTIVE, {"path": _P}, ["path"])
def delete_file(path: str) -> str:
    """Delete a file from the sandbox. Requires user confirmation."""
    p = safe_path(path, write=True)
    if not p.is_file():
        raise FileNotFoundError("not a file")
    p.unlink()
    return "deleted"


@tool(
    "launch_app",
    Level.MODIFY,
    {"name": {"type": "string", "enum": list(APP_ALLOWLIST)}},
    ["name"],
)
def launch_app(name: str) -> str:
    """Launch an allowlisted application."""
    subprocess.Popen([APP_ALLOWLIST[name]])  # no shell
    return f"launched {name}"
