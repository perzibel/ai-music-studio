"""Guitar/bass amp simulation: Neural Amp Modeler (.nam WaveNet/LSTM captures of real amps) + cabinet IRs.

Self-contained PyTorch inference for the NAM file format (no training dependencies needed).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
NAM_DIR = ROOT / "libraries" / "nam"
IR_DIR = ROOT / "libraries" / "cab_irs"
NAM_SR = 48000

# Friendly names -> files. The AI picks by name; users can add their own .nam / .wav files too.
AMPS = {
    "5150": ("Helga B 5150 BlockLetter - Boosted.nam", "high gain, modern metal (EVH 5150, boosted)"),
    "6505": ("Helga B 6505+ Red ch - MXR Drive.nam", "high gain, metalcore/djent (Peavey 6505+ red ch, boosted)"),
    "mesa_mark4": ("Roman A LT_MESA_MARKIV_1.nam", "high gain, tight thrash/prog (Mesa Mark IV)"),
    "jcm900": ("Tim R JCM90050WDualVerbChBG12.nam", "hot British crunch/rock (Marshall JCM900)"),
    "jcm2000": ("Tim R JCM2000 Crunch.nam", "classic rock crunch (Marshall JCM2000)"),
    "ac15": ("Phillipe P VOXAC15-TopBoost.nam", "chimey British edge-of-breakup, indie/pop rock (Vox AC15)"),
    "twin": ("Tim R Fender TwinVerb Norm Bright.nam", "sparkling clean (Fender Twin Reverb)"),
    "bass_dug": ("Jason Z Tech21 dUg DP3X bass preamp pedal all dimed no shift.nam", "gritty rock/metal bass preamp"),
}
CABS = {
    "mesa_4x12": ("mesa_4x12_v30.wav", "Mesa 4x12 V30, modern metal"),
    "v30": ("v30_sm57.wav", "4x12 V30 with SM57, tight"),
    "marshall_4x12": ("marshall_1960a.wav", "Marshall 1960A 4x12, classic rock"),
    "metal_chug": ("modern_metal_chugslayer.wav", "modern metal, chunky low mids"),
    "bass_svt": ("bass_ampeg_svt_810.wav", "Ampeg SVT 8x10 bass cab"),
    "bass_modern": ("bass_balanced.wav", "modern balanced bass cab"),
}
# Presets = amp + cab + drive + tone, so the AI can just say "amp": "metal".
RIGS = {
    "metal": {"amp": "5150", "cab": "mesa_4x12", "drive_db": 6, "gate_db": -55, "tight_hz": 110},
    "djent": {"amp": "6505", "cab": "metal_chug", "drive_db": 8, "gate_db": -50, "tight_hz": 130},
    "thrash": {"amp": "mesa_mark4", "cab": "v30", "drive_db": 6, "gate_db": -55, "tight_hz": 100},
    "rock": {"amp": "jcm900", "cab": "marshall_4x12", "drive_db": 4, "tight_hz": 80},
    "classic_rock": {"amp": "jcm2000", "cab": "marshall_4x12", "drive_db": 3, "tight_hz": 70},
    "indie": {"amp": "ac15", "cab": "v30", "drive_db": 0, "tight_hz": 70},
    "clean": {"amp": "twin", "cab": "v30", "drive_db": -3, "tight_hz": 60},
    "bass_grit": {"amp": "bass_dug", "cab": "bass_svt", "drive_db": 0, "blend": 0.45},
    "bass_clean": {"amp": None, "cab": "bass_modern", "drive_db": 0},
}


# ----------------------------------------------------------------------------- NAM inference

def _build(config: dict):
    import torch
    from torch import nn

    arch = config["architecture"]
    cfg = config["config"]
    weights = torch.tensor(config["weights"], dtype=torch.float32)

    if arch == "WaveNet":
        class Layer(nn.Module):
            def __init__(self, cond, ch, k, dil, act, gated):
                super().__init__()
                mid = 2 * ch if gated else ch
                self.conv = nn.Conv1d(ch, mid, k, dilation=dil)
                self.mixer = nn.Conv1d(cond, mid, 1, bias=False)
                self.act = getattr(torch, act.lower())
                self.one = nn.Conv1d(ch, ch, 1)
                self.ch, self.gated = ch, gated

            def forward(self, x, c, out_len):
                z = self.conv(x)
                z = z + self.mixer(c)[:, :, -z.shape[2]:]
                post = self.act(z[:, :self.ch]) * torch.sigmoid(z[:, self.ch:]) if self.gated else self.act(z)
                return x[:, :, -post.shape[2]:] + self.one(post), post[:, :, -out_len:]

        class LayerArray(nn.Module):
            def __init__(self, c):
                super().__init__()
                self.rechannel = nn.Conv1d(c["input_size"], c["channels"], 1, bias=False)
                self.layers = nn.ModuleList(Layer(c["condition_size"], c["channels"], c["kernel_size"], d,
                                                  c["activation"], c["gated"]) for d in c["dilations"])
                self.head = nn.Conv1d(c["channels"], c["head_size"], 1, bias=c["head_bias"])
                self.rf = 1 + (c["kernel_size"] - 1) * sum(c["dilations"])

            def forward(self, x, c, head):
                out_len = x.shape[2] - (self.rf - 1)
                x = self.rechannel(x)
                for layer in self.layers:
                    x, term = layer(x, c, out_len)
                    head = term if head is None else head[:, :, -out_len:] + term
                return self.head(head), x

        class WaveNet(nn.Module):
            def __init__(self):
                super().__init__()
                self.arrays = nn.ModuleList(LayerArray(c) for c in cfg["layers"])
                self.head_scale = float(cfg.get("head_scale", 1.0))
                self.rf = 1 + sum(a.rf - 1 for a in self.arrays)

            def forward(self, x):
                y, head = x, None
                for a in self.arrays:
                    head, y = a(y, x, head)
                return self.head_scale * head

        model = WaveNet()
        params = list(model.parameters())
        n = sum(p.numel() for p in params)
        # weights = all parameters in registration order, then head_scale
        with torch.no_grad():
            i = 0
            for p in params:
                p.copy_(weights[i:i + p.numel()].reshape(p.shape))
                i += p.numel()
        if i not in (len(weights), len(weights) - 1):
            raise ValueError(f"NAM weight count mismatch: model {n}, file {len(weights)}")
        return model, model.rf

    raise ValueError(f"Unsupported NAM architecture {arch!r} (only WaveNet captures are supported)")


@lru_cache(maxsize=8)
def _load_amp(path: str):
    import torch
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    model, rf = _build(config)
    model.eval()
    return model, rf, int(config.get("sample_rate") or NAM_SR)


def run_nam(path: str, mono: np.ndarray, sr: int, chunk: int = 1 << 18) -> np.ndarray:
    """Process a mono signal through a NAM model (resampling to the model's rate if needed)."""
    import torch
    from scipy.signal import resample_poly

    model, rf, model_sr = _load_amp(path)
    x = mono.astype(np.float32)
    if sr != model_sr:
        g = np.gcd(sr, model_sr)
        x = resample_poly(x, model_sr // g, sr // g).astype(np.float32)
    padded = np.concatenate([np.zeros(rf - 1, np.float32), x])
    out = np.empty_like(x)
    with torch.inference_mode():
        for s in range(0, len(x), chunk):
            e = min(len(x), s + chunk)
            seg = torch.from_numpy(padded[s:e + rf - 1]).view(1, 1, -1)
            out[s:e] = model(seg).view(-1).numpy()[-(e - s):]
    if sr != model_sr:
        g = np.gcd(sr, model_sr)
        out = resample_poly(out, sr // g, model_sr // g).astype(np.float32)
    return out[: len(mono)]


# ----------------------------------------------------------------------------- full rig

def _find(table: dict, name: str | None, folder: Path, kind: str) -> Path | None:
    if not name:
        return None
    if name in table:
        return folder / table[name][0]
    p = Path(name)
    for cand in (p, folder / name):
        if cand.exists():
            return cand
    raise ValueError(f"Unknown {kind} {name!r}. Available: {sorted(table)} or a file in {folder}")


@lru_cache(maxsize=16)
def _load_ir(path: str, sr: int) -> np.ndarray:
    from pedalboard.io import AudioFile
    from scipy.signal import resample_poly
    with AudioFile(path) as f:
        ir = f.read(f.frames).mean(axis=0)
        ir_sr = int(f.samplerate)
    if ir_sr != sr:
        g = np.gcd(ir_sr, sr)
        ir = resample_poly(ir, sr // g, ir_sr // g)
    ir = ir[: int(0.5 * sr)]
    return (ir / (np.sqrt(np.sum(ir ** 2)) + 1e-12)).astype(np.float32)  # unit energy


def resolve_rig(rig: dict | str) -> dict:
    if isinstance(rig, str):
        if rig not in RIGS:
            raise ValueError(f"Unknown amp rig {rig!r}. Presets: {sorted(RIGS)}")
        return dict(RIGS[rig])
    if "preset" in rig:
        if rig["preset"] not in RIGS:
            raise ValueError(f"Unknown amp rig {rig['preset']!r}. Presets: {sorted(RIGS)}")
        return {**RIGS[rig["preset"]], **{k: v for k, v in rig.items() if k != "preset"}}
    return dict(rig)


def apply_rig(audio: np.ndarray, sr: int, rig: dict | str) -> np.ndarray:
    """audio (2, n) DI signal -> amp + cab. rig: preset name or dict(amp, cab, drive_db, gate_db, tight_hz, blend)."""
    from scipy.signal import fftconvolve
    import pedalboard as pb

    rig = resolve_rig(rig)
    mono = audio.mean(axis=0).astype(np.float32)
    # Normalize the DI so amps see a consistent "guitar-level" signal, then apply drive.
    peak = float(np.max(np.abs(mono))) or 1.0
    di = mono * (10 ** (-6 / 20) / peak) * 10 ** (float(rig.get("drive_db", 0)) / 20)
    pre = []
    if rig.get("pre_lowpass_hz"):  # palm muting: the picking hand damps the string's highs
        pre.append(pb.LowpassFilter(cutoff_frequency_hz=float(rig["pre_lowpass_hz"])))
    if rig.get("tight_hz"):
        pre.append(pb.HighpassFilter(cutoff_frequency_hz=float(rig["tight_hz"])))  # "tube screamer" tightening
    if rig.get("gate_db") is not None:
        pre.append(pb.NoiseGate(threshold_db=float(rig["gate_db"]), ratio=10, release_ms=60))
    if pre:
        di = pb.Pedalboard(pre)(di[None, :], sr)[0]
    amp_path = _find(AMPS, rig.get("amp"), NAM_DIR, "amp")
    wet = run_nam(str(amp_path), di, sr) if amp_path else di
    if rig.get("blend") is not None and amp_path:  # bass: blend clean low end with the dirty amp
        b = float(rig["blend"])
        wet = (1 - b) * di / (np.max(np.abs(di)) + 1e-9) * (np.max(np.abs(wet)) + 1e-9) + b * wet
    cab_path = _find(CABS, rig.get("cab"), IR_DIR, "cab")
    if cab_path:
        wet = fftconvolve(wet, _load_ir(str(cab_path), sr))[: len(wet)].astype(np.float32)
    # Match the loudness (not the peak) of the DI: distortion compresses, so peak matching makes amps too loud.
    wet = wet * (_active_rms(mono) / (_active_rms(wet) + 1e-12))
    return np.stack([wet, wet]).astype(np.float32)


def _active_rms(x: np.ndarray, block: int = 4410) -> float:
    """RMS over the parts that actually play (ignores silence between phrases)."""
    n = len(x) // block * block
    if n == 0:
        return float(np.sqrt(np.mean(x ** 2)))
    r = np.sqrt(np.mean(x[:n].reshape(-1, block) ** 2, axis=1))
    active = r[r > r.max() * 0.05]
    return float(np.sqrt(np.mean(active ** 2))) if len(active) else 0.0
