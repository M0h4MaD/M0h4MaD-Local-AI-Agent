import json, re, time
from dataclasses import dataclass
import httpx
from config import (OLLAMA_URL, LLM_MODEL, LLM_KEEP_ALIVE, LLM_NUM_CTX,
                    LLM_NUM_GPU, RAW_PROMPT)
from tools.executor import ToolCall

_THINK = re.compile(r"<think>.*?(</think>|$)", re.S)

def _clean(t: str) -> str:
    t = t.rsplit("</think>", 1)[-1]
    return re.sub(r"<think>.*$", "", t, flags=re.S).strip()

def _chatml(messages: list[dict]) -> str:
    s = "".join(f"<|im_start|>{m['role']}\n{m.get('content') or ''}<|im_end|>\n" for m in messages)
    return s + "<|im_start|>assistant\n<think>\n\n</think>\n\n"

@dataclass
class LLMReply:
    text: str
    calls: list[ToolCall]
    raw: dict
    ms: int
    p_tok: int
    e_tok: int

class OllamaClient:
    def __init__(self):
        self.http = httpx.AsyncClient(base_url=OLLAMA_URL, timeout=httpx.Timeout(300, connect=5))

    async def warm(self):
        r = await self.http.post("/api/generate", json={"model": LLM_MODEL, "keep_alive": LLM_KEEP_ALIVE})
        r.raise_for_status()

    def _opts(self, num_predict: int) -> dict:
        o = {"num_ctx": LLM_NUM_CTX, "temperature": 0, "num_predict": num_predict}
        if LLM_NUM_GPU is not None:
            o["num_gpu"] = LLM_NUM_GPU
        return o

    async def _gen(self, messages: list[dict], schema: dict | None = None,
                   num_predict: int = 300) -> LLMReply:
        opts = self._opts(num_predict)
        opts["stop"] = ["<|im_end|>"]
        body = {"model": LLM_MODEL, "prompt": _chatml(messages), "raw": True, "stream": False,
                "keep_alive": LLM_KEEP_ALIVE, "options": opts}
        if schema:
            body["format"] = schema
        t0 = time.perf_counter()
        r = await self.http.post("/api/generate", json=body)
        r.raise_for_status()
        d = r.json()
        text = _clean(d.get("response") or "")
        return LLMReply(text, [], {"role": "assistant", "content": text},
                        int((time.perf_counter() - t0) * 1000),
                        d.get("prompt_eval_count", 0), d.get("eval_count", 0))

    async def chat_json(self, messages: list[dict], schema: dict) -> LLMReply:
        return await self._gen(messages, schema, 200)

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> LLMReply:
        if RAW_PROMPT and not tools:
            return await self._gen(messages)
        body = {"model": LLM_MODEL, "messages": messages, "stream": False, "think": False,
                "keep_alive": LLM_KEEP_ALIVE, "options": self._opts(300)}
        if tools:
            body["tools"] = tools
        t0 = time.perf_counter()
        r = await self.http.post("/api/chat", json=body)
        if r.status_code == 400:  # model may reject 'think'
            body.pop("think")
            r = await self.http.post("/api/chat", json=body)
        r.raise_for_status()
        d = r.json()
        m = d["message"]
        calls = []
        for tc in m.get("tool_calls") or []:
            f = tc["function"]
            a = f.get("arguments", {})
            if isinstance(a, str):
                try:
                    a = json.loads(a)
                except ValueError:
                    a = {}
            calls.append(ToolCall(f["name"], a if isinstance(a, dict) else {}))
        text = _clean(m.get("content") or "")
        return LLMReply(text, calls, m, int((time.perf_counter() - t0) * 1000),
                        d.get("prompt_eval_count", 0), d.get("eval_count", 0))