import sys, msvcrt
from config import DATA
import asyncio, logging, re
import audit
from agent import Agent
from config import PLANNER
from llm.ollama import OllamaClient
from llm.stub import StubPlanner
from tools.executor import Executor, ToolCall
from transport.telegram import TelegramTransport
from tools.sandbox import resolve_existing, safe_path, SandboxError

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)  # token appears in URLs

CONFIRM = re.compile(r"^confirm\s+([0-9a-f]{6})\s+(\d{6})$", re.I)
FAST = {"status": "system_status", "processes": "list_processes", "lock": "lock_pc"}
_LS = re.compile(r"^(?:ls|dir)(?:\s+(.+))?$", re.I)
_READ = re.compile(r"^(?:read|cat)\s+(.+)$", re.I)


async def reply(msg, ex, agent, stub) -> str:
    if msg.audio:
        return f"[stub] voice saved: {msg.audio.name}"
    text = (msg.text or "").strip()
    if text.lower().startswith("confirm"):  # never routed to the LLM
        m = CONFIRM.match(text)
        return (
            await ex.confirm(m[1].lower(), m[2], msg.sender)
            if m
            else "usage: confirm <id> <6-digit code>"
        )
    low = text.lower()
    if low in FAST:  # deterministic fast paths, no LLM
        return await ex.call(ToolCall(FAST[low], {}), msg.sender, msg.channel)
    if m := _LS.match(text):
        return await ex.call(
            ToolCall("list_dir", {"path": (m[1] or ".").strip().strip("\"'")}),
            msg.sender,
            msg.channel,
        )
    if m := _READ.match(text):
        p = resolve_existing(m[1])
        try:
            found = safe_path(p).exists()
        except SandboxError:
            found = True  # let the tool report the error
        if found:
            return await ex.call(
                ToolCall("read_file", {"path": p}), msg.sender, msg.channel
            )
    if agent:
        try:
            return await agent.run(text, msg.sender, msg.channel)
        except Exception as e:
            audit.log(
                "llm_error",
                sender=msg.sender,
                err=f"{type(e).__name__}: {str(e)[:150]}",
            )
            return "llm unavailable"
    p = stub.plan(msg)
    return await ex.call(p, msg.sender, msg.channel) if isinstance(p, ToolCall) else p


async def handle(tr, msg, ex, agent, stub):
    try:
        await tr.send(msg.sender, await reply(msg, ex, agent, stub))
    except Exception:
        logging.exception("handler failed")


async def main():
    tr, ex, stub = TelegramTransport(), Executor(), StubPlanner()
    llm = OllamaClient() if PLANNER == "llm" else None
    agent = Agent(llm, ex) if llm else None
    ok, n = audit.verify()
    audit.log("start", chain_ok=ok, chain_len=n, planner=PLANNER)
    if not ok:
        logging.warning("AUDIT CHAIN BROKEN")
    if llm:
        try:
            await llm.warm()
            audit.log("llm_warm", ok=True)
        except Exception as e:
            audit.log("llm_warm", ok=False, err=f"{type(e).__name__}: {str(e)[:150]}")
            logging.warning("Ollama not ready: %s", e)
    await tr.start()
    tasks = set()
    try:
        while True:
            msg = await tr.receive()
            t = asyncio.create_task(handle(tr, msg, ex, agent, stub))
            tasks.add(t)
            t.add_done_callback(tasks.discard)
    finally:
        await tr.stop()


if __name__ == "__main__":
    _lock = open(
        DATA / "bot.lock", "w"
    )  # keep a reference: lock lives as long as the process
    try:
        msvcrt.locking(_lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        sys.exit("another instance is already running")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
