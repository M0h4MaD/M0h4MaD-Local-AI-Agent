from transport.base import Message
from tools.executor import ToolCall, Confirm

HELP = "ls [p] | read p | write p text | rm p | launch app | confirm id code"

class StubPlanner:
    def plan(self, msg: Message) -> ToolCall | Confirm | str:
        if msg.audio:
            return f"[stub] voice saved: {msg.audio.name}"
        cmd, _, rest = (msg.text or "").strip().partition(" ")
        rest = rest.strip()
        match cmd.lower():
            case "ls":
                return ToolCall("list_dir", {"path": rest or "."})
            case "read":
                return ToolCall("read_file", {"path": rest})
            case "write":
                p, _, body = rest.partition(" ")
                return ToolCall("write_file", {"path": p, "text": body})
            case "rm":
                return ToolCall("delete_file", {"path": rest})
            case "launch":
                return ToolCall("launch_app", {"name": rest})
            case "confirm":
                parts = rest.split()
                if len(parts) == 2:
                    return Confirm(parts[0], parts[1])
        return HELP