"""Runs inside ACE-Step's own Python environment. Called by studio/enhance.py as a subprocess.

Prints one line "ACE_RESULT {json}" at the end so the caller can parse the result.
"""
import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

ACE_ROOT = Path(__file__).resolve().parent.parent / "engines" / "ACE-Step-1.5"
sys.path.insert(0, str(ACE_ROOT))
os.chdir(ACE_ROOT)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=None, help="source audio (not needed for text2music)")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--caption", required=True)
    ap.add_argument("--lyrics", default="")
    ap.add_argument("--task", default="cover")
    ap.add_argument("--strength", type=float, default=0.7)
    ap.add_argument("--bpm", type=int, default=None)
    ap.add_argument("--duration", type=float, default=-1)
    ap.add_argument("--seed", type=int, default=-1)
    ap.add_argument("--steps", type=int, default=8)
    ap.add_argument("--model", default="acestep-v15-turbo")
    ap.add_argument("--offload", action="store_true")
    ap.add_argument("--instruction", default=None)
    ap.add_argument("--language", default="unknown")
    ap.add_argument("--takes", type=int, default=1)
    ap.add_argument("--quant", default=None, help="e.g. int8_weight_only: halves DiT VRAM (6-8 GB GPUs)")
    ap.add_argument("--keyscale", default="", help='e.g. "E minor"')
    ap.add_argument("--timesignature", default="", help='e.g. "4" or "3"')
    ap.add_argument("--guidance", type=float, default=None, help="CFG scale (base model only)")
    ap.add_argument("--lm", default=None, help="5Hz LM that plans the song first (text2music), e.g. acestep-5Hz-lm-1.7B")
    ap.add_argument("--repaint-start", type=float, default=None, help="repaint: start of the region to redo (s)")
    ap.add_argument("--repaint-end", type=float, default=None, help="repaint: end of the region to redo (s)")
    a = ap.parse_args()
    t0 = time.time()
    try:
        from acestep.handler import AceStepHandler
        from acestep.inference import GenerationConfig, GenerationParams, generate_music

        handler = AceStepHandler()
        status, ok = handler.initialize_service(project_root=str(ACE_ROOT), config_path=a.model, device="auto",
                                                offload_to_cpu=a.offload, quantization=a.quant)
        if not ok:
            raise RuntimeError(f"ACE-Step init failed: {status}")
        llm = None
        if a.lm:  # the LM writes the song's semantic "blueprint" that the DiT then renders: better structure
            from acestep.llm_inference import LLMHandler
            llm = LLMHandler()
            status, ok = llm.initialize(checkpoint_dir=str(ACE_ROOT / "checkpoints"), lm_model_path=a.lm,
                                        backend="pt", device="auto", offload_to_cpu=a.offload)
            if not ok:
                raise RuntimeError(f"ACE-Step LM init failed: {status}")
        paths, errors = [], []
        for take in range(max(1, a.takes)):  # takes run one after another: batching doesn't fit 8 GB GPUs
            seed = a.seed + take if a.seed >= 0 else -1
            kwargs = dict(task_type=a.task, src_audio=a.src, caption=a.caption, lyrics=a.lyrics,
                          instrumental=not a.lyrics, vocal_language=a.language,
                          audio_cover_strength=a.strength, bpm=a.bpm, duration=a.duration,
                          inference_steps=a.steps, seed=seed, thinking=llm is not None,
                          use_cot_metas=llm is not None, use_cot_caption=False, use_cot_language=False,
                          keyscale=a.keyscale, timesignature=a.timesignature)
            if a.guidance is not None:
                kwargs["guidance_scale"] = a.guidance
            if a.instruction:
                kwargs["instruction"] = a.instruction
            if a.task == "repaint" and a.repaint_start is not None:
                # Only the chosen range is regenerated; "explicit" makes the model honor it as a hard mask.
                kwargs.update(repainting_start=a.repaint_start,
                              repainting_end=a.repaint_end if a.repaint_end is not None else -1,
                              chunk_mask_mode="explicit")
            elif a.task in ("repaint", "lego"):
                kwargs.update(repainting_start=0.0, repainting_end=-1)
            params = GenerationParams(**kwargs)
            config = GenerationConfig(batch_size=1, use_random_seed=seed < 0,
                                      seeds=[seed] if seed >= 0 else None, audio_format="flac")
            res = generate_music(handler, llm, params, config, save_dir=a.out_dir)
            if res.success:
                paths += [x["path"] for x in res.audios]
            else:
                errors.append(res.error)
        out = {"ok": bool(paths), "error": "; ".join(e for e in errors if e) or None, "paths": paths,
               "seconds": round(time.time() - t0, 1)}
    except Exception as e:
        out = {"ok": False, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-2000:]}
    print("ACE_RESULT " + json.dumps(out), flush=True)


if __name__ == "__main__":
    main()
