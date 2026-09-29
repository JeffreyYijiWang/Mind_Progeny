"""Compatibility adapter for pinned NVIDIA code and PyTorch 2.7.1.

Uses NVIDIA's reference operations on the selected device; no C++/CUDA compiler.
This is a local adaptation, not an NVIDIA-tested Windows/PyTorch combination.
"""
import functools


def install():
    import torch
    from torch_utils.ops import bias_act, upfirdn2d, conv2d_gradfix, grid_sample_gradfix

    if not torch.__version__.startswith("2.7.1"):
        raise RuntimeError("Use the isolated environment with PyTorch 2.7.1+cu128.")
    if getattr(bias_act, "_local_reference_adapter", False):
        return

    # The public signatures permit impl as a positional argument as well.
    def force_reference(fn):
        import inspect
        signature = inspect.signature(fn)

        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            bound = signature.bind(*args, **kwargs)
            bound.arguments["impl"] = "ref"
            return fn(*bound.args, **bound.kwargs)
        return wrapped

    bias_act.bias_act = force_reference(bias_act.bias_act)
    upfirdn2d.upfirdn2d = force_reference(upfirdn2d.upfirdn2d)
    # Modern native convolution supports the derivatives used by the loss.
    conv2d_gradfix._should_use_custom_op = lambda input: False
    # Preserve NVIDIA's higher-order input-gradient implementation, updating
    # only the aten backward signature that changed since PyTorch 1.7.
    grid_sample_gradfix._should_use_custom_op = lambda: grid_sample_gradfix.enabled

    def backward_forward(ctx, grad_output, input, grid):
        grad_input, grad_grid = torch.ops.aten.grid_sampler_2d_backward(
            grad_output, input, grid, 0, 0, False, [True, True])
        ctx.save_for_backward(grid)
        return grad_input, grad_grid

    grid_sample_gradfix._GridSample2dBackward.forward = staticmethod(backward_forward)
    bias_act._local_reference_adapter = True


def small_preview(training_set, random_seed=0):
    """A fixed 2x2 grid avoids upstream's 28-image 1024px preview allocation."""
    import numpy as np
    rng = np.random.RandomState(random_seed)
    indices = rng.permutation(len(training_set))[:4]
    images, labels = zip(*(training_set[int(i)] for i in indices))
    return (2, 2), np.stack(images), np.stack(labels)
