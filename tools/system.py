import ctypes, os, shutil, subprocess
from pathlib import Path
import psutil
from config import APP_ALLOWLIST, ENABLE_POWER
from tools.registry import tool, Level

_KILLABLE = sorted({Path(v).name.lower() for v in APP_ALLOWLIST.values()})

@tool("system_status", Level.READ, {})
def system_status() -> str:
    """CPU, RAM, disk and GPU usage."""
    vm = psutil.virtual_memory()
    drive = os.environ.get("SystemDrive", "C:") + "\\"
    du = shutil.disk_usage(drive)
    out = [f"CPU {psutil.cpu_percent(interval=0.5):.0f}%",
           f"RAM {vm.used / 2**30:.1f}/{vm.total / 2**30:.1f} GB ({vm.percent:.0f}%)",
           f"Disk {drive} free {du.free / 2**30:.0f}/{du.total / 2**30:.0f} GB"]
    try:
        g = subprocess.run(["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5)
        if g.returncode == 0 and g.stdout.strip():
            n, u, mu, mt = [x.strip() for x in g.stdout.strip().splitlines()[0].split(",")]
            out.append(f"GPU {n} {u}% VRAM {mu}/{mt} MiB")
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "\n".join(out)

@tool("list_processes", Level.READ,
      {"top": {"type": "integer", "minimum": 1, "maximum": 30}}, untrusted=True)
def list_processes(top: int = 10) -> str:
    """List the top processes by memory use."""
    procs = []
    for p in psutil.process_iter(["name", "pid", "memory_info"]):
        mi = p.info["memory_info"]
        if mi:
            procs.append((mi.rss, p.info["name"], p.info["pid"]))
    procs.sort(reverse=True)
    return "\n".join(f"{n} (pid {pid}) {rss / 2**20:.0f} MB" for rss, n, pid in procs[:top])

@tool("lock_pc", Level.MODIFY, {})
def lock_pc() -> str:
    """Lock the Windows session."""
    if not ctypes.windll.user32.LockWorkStation():
        raise OSError("lock failed")
    return "locked"

@tool("kill_process", Level.DESTRUCTIVE,
      {"process": {"type": "string", "enum": _KILLABLE}}, ["process"])
def kill_process(process: str) -> str:
    """Terminate all instances of an allowlisted application. Requires confirmation."""
    n = 0
    for p in psutil.process_iter(["name"]):
        if (p.info["name"] or "").lower() == process:
            try:
                p.terminate()
                n += 1
            except psutil.Error:
                pass
    return f"terminated {n}"

if ENABLE_POWER:
    @tool("power", Level.DESTRUCTIVE,
          {"action": {"type": "string", "enum": ["shutdown", "restart"]}}, ["action"])
    def power(action: str) -> str:
        """Shut down or restart the PC after 60 seconds. Requires confirmation."""
        subprocess.run(["shutdown", "/s" if action == "shutdown" else "/r", "/t", "60"], check=True)
        return f"{action} in 60 s; send 'cancel shutdown' to abort"

    @tool("cancel_shutdown", Level.MODIFY, {})
    def cancel_shutdown() -> str:
        """Abort a pending shutdown or restart."""
        subprocess.run(["shutdown", "/a"], check=True)
        return "aborted"