"""Throughput options and a process-local PyTorch allocation budget.

No GPU is accessed at import time. Driver allocations and other processes are
outside PyTorch's allocator cap; this is not a system-wide VRAM guarantee.
"""
import math

GIB = 1024 ** 3


def validate(policy):
    fraction = policy["max_allocator_fraction"]
    reserve = policy["reserve_mib"]
    if not math.isfinite(fraction) or not 0.1 <= fraction <= 0.9:
        raise ValueError("GPU allocator fraction must be between 0.1 and 0.9.")
    if not math.isfinite(reserve) or reserve < 512:
        raise ValueError("Keep at least 512 MiB of GPU headroom.")
    for key in ("allow_tf32", "fp16_channels_last"):
        if not isinstance(policy[key], bool):
            raise ValueError(f"{key} must be a boolean.")


def budget(free, total, policy):
    validate(policy)
    if total <= 0 or free < 0 or free > total:
        raise ValueError("Invalid GPU memory reading.")
    limit = int(min(total * policy["max_allocator_fraction"],
                    free - policy["reserve_mib"] * 1024 ** 2))
    if limit < GIB:
        raise RuntimeError("Insufficient free GPU memory after reserving headroom; model was not loaded.")
    return {"allocator_limit_bytes": limit, "allocator_fraction": limit / total,
            "initial_free_bytes": free, "total_bytes": total,
            "reserved_headroom_bytes": free - limit}


def configure(torch, policy):
    """Call after launch authorization, before moving any model to CUDA."""
    torch.cuda.set_device(0)
    free, total = torch.cuda.mem_get_info(0)
    report = budget(free, total, policy)
    torch.cuda.set_per_process_memory_fraction(report["allocator_fraction"], device=0)
    torch.backends.cuda.matmul.allow_tf32 = policy["allow_tf32"]
    torch.backends.cudnn.allow_tf32 = policy["allow_tf32"]
    # Avoid benchmark search's transient workspace peaks. FP16 remains enabled.
    torch.backends.cudnn.benchmark = False
    print(f"PyTorch GPU allocation cap: {report['allocator_limit_bytes'] / GIB:.2f} GiB; "
          f"initial headroom: {report['reserved_headroom_bytes'] / GIB:.2f} GiB. "
          "External/driver allocations are outside this cap.", flush=True)
    return report


def memory_status(torch):
    free, total = torch.cuda.mem_get_info(0)
    return {"free_bytes": free, "total_bytes": total,
            "allocated_bytes": torch.cuda.memory_allocated(0),
            "reserved_bytes": torch.cuda.memory_reserved(0)}
