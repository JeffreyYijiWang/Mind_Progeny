"""Read-only Windows commit/physical memory report; does not alter settings."""
import ctypes
import os
if os.name == "nt":
    class Memory(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [(name, ctypes.c_ulonglong) for name in ("total_physical", "available_physical", "total_commit", "available_commit", "total_virtual", "available_virtual", "extended")]
    memory = Memory()
    memory.length = ctypes.sizeof(memory)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
        raise ctypes.WinError()
    print({name + "_GiB": round(getattr(memory, name) / 2**30, 2) for name in ("total_physical", "available_physical", "total_commit", "available_commit")})
