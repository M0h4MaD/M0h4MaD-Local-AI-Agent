import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED = {int(x) for x in os.environ["ALLOWED_USER_IDS"].split(",") if x.strip()}
DATA = Path("data")
VOICE = DATA / "voice"
VOICE.mkdir(parents=True, exist_ok=True)
MAX_VOICE_BYTES = 2_000_000
TOTP_SECRET = os.environ.get("TOTP_SECRET", "")
SANDBOX = DATA / "sandbox"
SANDBOX.mkdir(parents=True, exist_ok=True)
CONFIRM_TTL = 120

def _kv(env: str, default: dict) -> dict:
    d = dict(default)
    for item in os.environ.get(env, "").split(";"):
        if "=" in item:
            k, v = item.split("=", 1)
            d[k.strip().lower()] = v.strip()
    return d

APP_ALLOWLIST = _kv("APPS", {"notepad": "notepad.exe", "calc": "calc.exe"})
RO_ROOTS = {k: Path(v) for k, v in _kv("RO_ROOTS", {}).items()}
ENABLE_POWER = os.environ.get("ENABLE_POWER", "0") == "1"

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
LLM_MODEL = os.environ.get("LLM_MODEL", "Qwen-4B")
LLM_KEEP_ALIVE = os.environ.get("LLM_KEEP_ALIVE", "30m")
LLM_NUM_CTX = int(os.environ.get("LLM_NUM_CTX", "4096"))
_g = os.environ.get("LLM_NUM_GPU", "")
LLM_NUM_GPU = int(_g) if _g else None
PLANNER = os.environ.get("PLANNER", "llm")
AGENT_LOOP = os.environ.get("AGENT_LOOP", "0") == "1"
RAW_PROMPT = os.environ.get("RAW_PROMPT", "1") == "1"
TOOL_MODE = os.environ.get("TOOL_MODE", "json")