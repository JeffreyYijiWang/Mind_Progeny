"""Read-only Windows commit/physical memory report; does not alter settings."""
import ctypes
import os


def memory_snapshot():
    """Read process-available commit headroom, which can be below global headroom."""
    if os.name != "nt":
        return None
    class Memory(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [(name, ctypes.c_ulonglong) for name in ("total_physical", "available_physical", "total_commit", "available_commit", "total_virtual", "available_virtual", "extended")]
    memory = Memory()
    memory.length = ctypes.sizeof(memory)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
        raise ctypes.WinError()
    return {name + "_GiB": round(getattr(memory, name) / 2**30, 3) for name in ("total_physical", "available_physical", "total_commit", "available_commit")}


if __name__ == "__main__":
    print(memory_snapshot())
