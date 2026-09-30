"""SFZ sample-library engine: drives sfizz (sfizz.dll) through ctypes for offline rendering."""
from __future__ import annotations

import ctypes
import os
from functools import lru_cache
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DLL_PATH = Path(os.environ.get("AI_MUSIC_SFIZZ_DLL", ROOT / "engines" / "sfizz" / "bin" / "Release" / "sfizz.dll"))
BLOCK = 512


@lru_cache(maxsize=1)
def _dll():
    if not DLL_PATH.exists():
        raise RuntimeError(f"sfizz not found at {DLL_PATH}. Run setup.ps1.")
    d = ctypes.CDLL(str(DLL_PATH))
    p, i, f = ctypes.c_void_p, ctypes.c_int, ctypes.c_float
    d.sfizz_create_synth.restype = p
    d.sfizz_free.argtypes = [p]
    d.sfizz_load_file.argtypes = [p, ctypes.c_char_p]
    d.sfizz_load_file.restype = ctypes.c_bool
    d.sfizz_load_string.argtypes = [p, ctypes.c_char_p, ctypes.c_char_p]
    d.sfizz_load_string.restype = ctypes.c_bool
    d.sfizz_set_samples_per_block.argtypes = [p, i]
    d.sfizz_set_sample_rate.argtypes = [p, f]
    d.sfizz_send_note_on.argtypes = [p, i, i, i]
    d.sfizz_send_note_off.argtypes = [p, i, i, i]
    d.sfizz_send_cc.argtypes = [p, i, i, i]
    d.sfizz_send_pitch_wheel.argtypes = [p, i, i]
    d.sfizz_set_num_voices.argtypes = [p, i]
    d.sfizz_enable_freewheeling.argtypes = [p]
    d.sfizz_get_num_regions.argtypes = [p]
    d.sfizz_get_num_regions.restype = i
    d.sfizz_get_num_active_voices.argtypes = [p]
    d.sfizz_get_num_active_voices.restype = i
    d.sfizz_render_block.argtypes = [p, ctypes.POINTER(ctypes.POINTER(f)), i, i]
    return d


class SfzError(RuntimeError):
    pass


def render_sfz(sfz: str, events: list[tuple], length: int, sr: int, sfz_text: str | None = None,
               init_cc: dict[int, int] | None = None) -> np.ndarray:
    """Render events through an SFZ instrument.

    events: (sample_index, kind, a, b) with kind in
      "on" (note, velocity) / "off" (note, 0) / "cc" (number, value 0-127) / "bend" (value -8192..8191, 0)
    If sfz_text is given it is loaded as a virtual file located at `sfz` (lets us wrap/include real files).
    """
    d = _dll()
    synth = d.sfizz_create_synth()
    try:
        d.sfizz_set_sample_rate(synth, float(sr))
        d.sfizz_set_samples_per_block(synth, BLOCK)
        d.sfizz_set_num_voices(synth, 256)
        d.sfizz_enable_freewheeling(synth)  # offline: load samples synchronously, max quality
        ok = (d.sfizz_load_string(synth, str(sfz).encode("utf-8"), sfz_text.encode("utf-8")) if sfz_text
              else d.sfizz_load_file(synth, str(sfz).encode("utf-8")))
        if not ok or d.sfizz_get_num_regions(synth) == 0:
            raise SfzError(f"sfizz could not load {sfz}")
        for num, val in (init_cc or {}).items():
            d.sfizz_send_cc(synth, 0, int(num), int(val))

        order = {"off": 0, "cc": 1, "bend": 1, "on": 2}
        events = sorted(events, key=lambda e: (e[0], order[e[1]]))
        n_blocks = (length + BLOCK - 1) // BLOCK
        out = np.zeros((2, n_blocks * BLOCK), dtype=np.float32)
        left = np.zeros(BLOCK, dtype=np.float32)
        right = np.zeros(BLOCK, dtype=np.float32)
        fp = ctypes.POINTER(ctypes.c_float)
        chans = (fp * 2)(left.ctypes.data_as(fp), right.ctypes.data_as(fp))
        ei = 0
        for b in range(n_blocks):
            start = b * BLOCK
            end = start + BLOCK
            while ei < len(events) and events[ei][0] < end:
                t, kind, a, v = events[ei]
                delay = max(0, int(t) - start)
                if kind == "on":
                    d.sfizz_send_note_on(synth, delay, int(a), max(1, min(127, int(v))))
                elif kind == "off":
                    d.sfizz_send_note_off(synth, delay, int(a), 0)
                elif kind == "cc":
                    d.sfizz_send_cc(synth, delay, int(a), max(0, min(127, int(v))))
                elif kind == "bend":
                    d.sfizz_send_pitch_wheel(synth, delay, max(-8192, min(8191, int(a))))
                ei += 1
            left[:] = 0
            right[:] = 0
            d.sfizz_render_block(synth, chans, 2, BLOCK)
            out[0, start:end] = left
            out[1, start:end] = right
        return out[:, :length]
    finally:
        d.sfizz_free(synth)
