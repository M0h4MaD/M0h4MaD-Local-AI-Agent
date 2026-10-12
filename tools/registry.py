from dataclasses import dataclass
from enum import IntEnum
from typing import Callable

class Level(IntEnum):
    READ = 1
    MODIFY = 2
    DESTRUCTIVE = 3

@dataclass(frozen=True)
class Tool:
    name: str
    level: Level
    schema: dict
    fn: Callable[..., str]
    doc: str = ""
    untrusted: bool = False   # output derived from attacker-controllable data

REGISTRY: dict[str, Tool] = {}

def tool(name: str, level: Level, props: dict, required: list[str] = (), untrusted: bool = False):
    def deco(fn):
        schema = {"type": "object", "properties": props,
                  "required": list(required), "additionalProperties": False}
        REGISTRY[name] = Tool(name, level, schema, fn, (fn.__doc__ or "").strip(), untrusted)
        return fn
    return deco