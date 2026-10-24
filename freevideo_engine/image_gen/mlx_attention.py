"""Image attention through MLX's fused Metal kernel on Apple GPUs.

At the 1024 x 1024 shape (4125 keys, 32 heads of 128) Torch's MPS attention
ran at about 3.5 TFLOPS on an M5; this kernel is the one the Mac video engine
already uses. Q/K/V and the output share their Metal buffers through DLPack.
"""
import math

import torch

from ..backends.mps_mlx_attention import to_mlx_many, to_torch

# The first MLX call with and without a mask is compared with the fallback on this many
# queries; each query attends independently, so the slice is exact. Measured MLX-to-Torch
# differences on M-series Macs were 0.004-0.0098; a wrong kernel is off by far more.
CHECK_QUERIES = 64
TOLERANCE = .05


def available():
    try:
        import mlx.core  # noqa: F401
    except Exception:
        return False
    return True


def routed(fallback, *, min_queries=256):
    """``attention`` for image-sized calls; short text segments, where the hand-over costs more, keep ``fallback``.

    A call MLX cannot run, or whose first result disagrees with ``fallback``, goes to
    ``fallback`` instead of failing or spoiling the picture, and so does every later call of
    the process. ``failed`` keeps why, for the image report.
    """
    failed = []
    checked = set()

    def run(query, key, value, attn_mask=None):
        if failed or query.shape[1] < min_queries:
            return fallback(query, key, value, attn_mask=attn_mask)
        try:
            out = attention(query, key, value, attn_mask=attn_mask)
            kind = attn_mask is not None
            if kind not in checked:
                reason = differs(query, key, value, attn_mask, out, fallback)
                checked.add(kind)
                if reason:
                    failed.append(reason)
                    return fallback(query, key, value, attn_mask=attn_mask)
            return out
        except Exception as error:
            failed.append(f'{type(error).__name__}: {error}'[:300])
            return fallback(query, key, value, attn_mask=attn_mask)
    run.failed = failed
    return run


def differs(query, key, value, attn_mask, out, fallback):
    """Why ``out`` cannot be trusted, or None when its first queries match ``fallback``."""
    count = min(CHECK_QUERIES, query.shape[1])
    mask = attn_mask
    if mask is not None and mask.dim() >= 2 and mask.shape[-2] == query.shape[1]:
        mask = mask[..., :count, :]
    reference = fallback(query[:, :count], key, value, attn_mask=mask).float()
    got = out[:, :count].float()
    if not torch.isfinite(got).all():
        # Non-finite values the fallback also gives come from the inputs, not from MLX.
        return 'mismatch: non-finite output' if torch.isfinite(reference).all() else None
    difference = (got - reference).abs().max().item()
    if difference > TOLERANCE * max(1., reference.abs().max().item()):
        return 'mismatch: max difference %.3g over %d queries' % (difference, count)
    return None


def summary(function):
    """What the image report says about attention: None unless ``function`` came from routed()."""
    failed = getattr(function, 'failed', None)
    if failed is None:
        return None
    return dict(kernel='torch' if failed else 'mlx', **({'fallback_reason': failed[0]} if failed else {}))


def attention(query, key, value, attn_mask=None):
    """Same contract as ``qwen_dit.attention``: (batch, sequence, heads, dim), boolean mask or None."""
    import mlx.core as mx
    tensors = (query, key, value) if attn_mask is None else (query, key, value, attn_mask)
    arrays = to_mlx_many(tensors)
    q, k, v = (mx.swapaxes(array, 1, 2) for array in arrays[:3])
    mask = arrays[3] if attn_mask is not None else None
    out = mx.fast.scaled_dot_product_attention(q, k, v, scale=1 / math.sqrt(query.shape[-1]), mask=mask)
    out = mx.contiguous(mx.swapaxes(out, 1, 2))
    result = to_torch(out, query.device)
    del arrays, q, k, v, mask, out
    # One unified pool: do not let MLX keep the freed buffers from Torch.
    mx.clear_cache()
    return result
