"""Keep AI runs from taking the whole PC down (Windows).

ACE-Step with CPU offload once committed ~89 GB of memory, exhausted RAM + page file and froze the desktop.
Every AI process is therefore started inside a Windows Job Object that:
  * caps how much memory any single process in it may commit: the process gets an out-of-memory error
    instead of starving Windows, and
  * kills the whole process tree when the job handle closes, so a stopped/crashed caller never leaves an
    orphaned AI process holding the GPU and RAM.
Child processes (e.g. a launcher .bat starting python) are put in the same job automatically.
On non-Windows systems these helpers do nothing.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys

IS_WIN = sys.platform == "win32"

# JOBOBJECT_EXTENDED_LIMIT_INFORMATION flags / class
_LIMIT_PROCESS_MEMORY = 0x100
_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
_EXTENDED_LIMIT_INFO = 9
_CREATE_SUSPENDED = 0x4


def total_ram_gb() -> float:
    if IS_WIN:
        class MEMSTAT(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = MEMSTAT()
        m.dwLength = ctypes.sizeof(MEMSTAT)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return m.ullTotalPhys / 1024 ** 3
    return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024 ** 3


def default_limit_gb() -> float:
    """Per-process cap: AI_MEMORY_LIMIT_GB if set, else 75% of physical RAM (24 GB on a 32 GB PC)."""
    env = os.environ.get("AI_MEMORY_LIMIT_GB")
    return float(env) if env else round(total_ram_gb() * 0.75, 1)


if IS_WIN:
    class _IO(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in ("r", "w", "o", "rb", "wb", "ob")]

    class _BASIC(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                    ("LimitFlags", ctypes.c_ulong), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", ctypes.c_ulong),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", ctypes.c_ulong),
                    ("SchedulingClass", ctypes.c_ulong)]

    class _EXT(ctypes.Structure):
        _fields_ = [("Basic", _BASIC), ("Io", _IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]


class GuardedJob:
    """A Windows job with a per-process memory cap. Close it (or let this process exit) to kill everything in it."""

    def __init__(self, limit_gb: float | None = None):
        self.limit_gb = limit_gb or default_limit_gb()
        self.handle = None
        if not IS_WIN:
            return
        k32 = ctypes.windll.kernel32
        k32.CreateJobObjectW.restype = ctypes.c_void_p
        self.handle = k32.CreateJobObjectW(None, None)
        if not self.handle:
            raise OSError("CreateJobObject failed")
        info = _EXT()
        info.Basic.LimitFlags = _LIMIT_PROCESS_MEMORY | _LIMIT_KILL_ON_JOB_CLOSE
        info.ProcessMemoryLimit = int(self.limit_gb * 1024 ** 3)
        if not k32.SetInformationJobObject(ctypes.c_void_p(self.handle), _EXTENDED_LIMIT_INFO,
                                           ctypes.byref(info), ctypes.sizeof(info)):
            raise OSError("SetInformationJobObject failed")

    def add(self, proc: subprocess.Popen) -> None:
        if self.handle:
            ok = ctypes.windll.kernel32.AssignProcessToJobObject(ctypes.c_void_p(self.handle),
                                                                 ctypes.c_void_p(int(proc._handle)))
            if not ok:
                raise OSError("AssignProcessToJobObject failed")

    def peak_gb(self) -> float | None:
        if not self.handle:
            return None
        info = _EXT()
        ctypes.windll.kernel32.QueryInformationJobObject(ctypes.c_void_p(self.handle), _EXTENDED_LIMIT_INFO,
                                                         ctypes.byref(info), ctypes.sizeof(info), None)
        return round(info.PeakProcessMemoryUsed / 1024 ** 3, 1)

    def close(self) -> None:
        if self.handle:
            ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(self.handle))  # kills anything still running
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def run_guarded(cmd: list[str], timeout: int, limit_gb: float | None = None, **popen_kw) -> tuple:
    """subprocess.run() replacement: memory-capped, and the child dies with us (timeout, Ctrl+C, crash).
    Returns (returncode, stdout, stderr, peak_gb)."""
    flags = popen_kw.pop("creationflags", 0) | (_CREATE_SUSPENDED if IS_WIN else 0)
    with GuardedJob(limit_gb) as job:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=flags,
                                **popen_kw)
        try:
            job.add(proc)  # assigned while suspended: no code runs outside the cap
        finally:
            if IS_WIN:
                _resume(proc)
        try:
            out, err = proc.communicate(timeout=timeout)
        except BaseException:
            proc.kill()
            proc.communicate()
            raise
        return proc.returncode, out, err, job.peak_gb()


def _resume(proc: subprocess.Popen) -> None:
    """Resume the main thread of a process created with CREATE_SUSPENDED."""
    ntdll = ctypes.windll.ntdll
    ntdll.NtResumeProcess(ctypes.c_void_p(int(proc._handle)))


def ace_is_busy() -> str | None:
    """Return a reason if another ACE-Step app is already using the GPU (the desktop web app on :7860)."""
    import socket
    with socket.socket() as s:
        s.settimeout(0.3)
        if s.connect_ex(("127.0.0.1", 7860)) == 0:
            return ("The P3rzible Music Studio web app (port 7860) is running and holds the GPU. "
                    "Close it first: running two AI engines at once on an 8 GB GPU overloads memory.")
    return None


def main() -> None:
    """python -m studio.memguard [--limit-gb N] [--cwd DIR] -- command args...  (used by the desktop launcher)"""
    args = sys.argv[1:]
    limit, cwd = None, None
    while args[:1] in (["--limit-gb"], ["--cwd"]):
        if args[0] == "--limit-gb":
            limit = float(args[1])
        else:
            cwd = args[1]
        args = args[2:]
    if args[:1] == ["--"]:
        args = args[1:]
    if not args:
        sys.exit("usage: python -m studio.memguard [--limit-gb N] [--cwd DIR] -- command ...")
    job = GuardedJob(limit)
    print(f"[memguard] memory cap: {job.limit_gb} GB per process; closing this window stops the app.",
          flush=True)
    proc = subprocess.Popen(args, cwd=cwd, creationflags=_CREATE_SUSPENDED if IS_WIN else 0)
    job.add(proc)
    if IS_WIN:
        _resume(proc)
    try:
        sys.exit(proc.wait())
    except KeyboardInterrupt:
        proc.kill()
    finally:
        job.close()


if __name__ == "__main__":
    main()
