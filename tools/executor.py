import asyncio, hashlib, secrets, time
from dataclasses import dataclass
import jsonschema, pyotp
import audit
from config import CONFIRM_TTL, TOTP_SECRET
from tools.registry import REGISTRY, Level
import tools.builtin  # noqa: F401  (registers tools)
import tools.system  # noqa: F401

CHANNEL_MAX = {"telegram": Level.DESTRUCTIVE}
MAX_PENDING = 5

@dataclass
class ToolCall:
    name: str
    args: dict

@dataclass
class Confirm:
    id: str
    code: str

@dataclass
class Pending:
    call: ToolCall
    sender: str
    exp: float
    tries: int = 0

def _redact(args: dict) -> dict:
    return {k: ({"len": len(v), "sha": hashlib.sha256(v.encode()).hexdigest()[:12]}
                if isinstance(v, str) and len(v) > 200 else v) for k, v in args.items()}

class Executor:
    def __init__(self):
        self.pending: dict[str, Pending] = {}
        self.used: dict[str, float] = {}

    def _gc(self):
        now = time.time()
        self.pending = {k: p for k, p in self.pending.items() if p.exp > now}
        self.used = {k: t for k, t in self.used.items() if t > now}

    async def call(self, c: ToolCall, sender: str, channel: str) -> str:
        t = REGISTRY.get(c.name)
        if not t:
            audit.log("tool_unknown", sender=sender, name=c.name)
            return "unknown tool"
        try:
            jsonschema.validate(c.args, t.schema)
        except jsonschema.ValidationError as e:
            audit.log("tool_invalid", sender=sender, name=c.name, err=e.message[:200])
            return f"invalid args: {e.message[:100]}"
        if t.level > CHANNEL_MAX.get(channel, Level.READ):
            audit.log("tool_denied_channel", sender=sender, name=c.name, channel=channel)
            return "denied: level not allowed on this channel"
        if t.level == Level.DESTRUCTIVE:
            if not TOTP_SECRET:
                audit.log("tool_denied_no_totp", sender=sender, name=c.name)
                return "denied: TOTP_SECRET not set"
            self._gc()
            if len(self.pending) >= MAX_PENDING:
                return "too many pending confirmations"
            pid = secrets.token_hex(3)
            self.pending[pid] = Pending(c, sender, time.time() + CONFIRM_TTL)
            audit.log("confirm_requested", id=pid, sender=sender, name=c.name, args=_redact(c.args))
            return f"DESTRUCTIVE: {c.name} {c.args}\nconfirm {pid} <TOTP> within {CONFIRM_TTL}s"
        return await self._run(t, c, sender)

    async def confirm(self, pid: str, code: str, sender: str) -> str:
        self._gc()
        p = self.pending.get(pid)
        if not p or p.sender != sender:
            audit.log("confirm_unknown", sender=sender, id=pid)
            return "no such pending"
        ok = code not in self.used and pyotp.TOTP(TOTP_SECRET).verify(code, valid_window=1)
        if not ok:
            p.tries += 1
            audit.log("confirm_badcode", sender=sender, id=pid, tries=p.tries)
            if p.tries >= 3:
                del self.pending[pid]
                audit.log("confirm_locked", sender=sender, id=pid)
                return "bad code; pending cancelled"
            return "bad code"
        del self.pending[pid]
        self.used[code] = time.time() + 120
        audit.log("confirm_ok", sender=sender, id=pid)
        return await self._run(REGISTRY[p.call.name], p.call, sender)

    async def _run(self, t, c: ToolCall, sender: str) -> str:
        try:
            out = await asyncio.wait_for(asyncio.to_thread(t.fn, **c.args), 30)
            audit.log("tool_ok", sender=sender, name=c.name, level=t.level.name,
                      args=_redact(c.args), out_len=len(out))
            return out[:3000]
        except Exception as e:
            audit.log("tool_err", sender=sender, name=c.name, args=_redact(c.args),
                      err=f"{type(e).__name__}: {str(e)[:150]}")
            return f"error: {type(e).__name__}: {e}"[:300]