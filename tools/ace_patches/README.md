# ACE-Step patches for P3rzible Music Studio

`engines/ACE-Step-1.5` is a separate checkout (gitignored here), so our changes to it live in this patch.
Re-apply after reinstalling or updating ACE-Step:

    cd engines/ACE-Step-1.5
    git apply ../../tools/ace_patches/p3rzible-studio.patch

What it changes:
- Web UI title: "P3rzible Music Studio".
- Status bar under Generate: live current step, % and elapsed time, app/PC/GPU memory.
- "Stop & free memory": interrupts a running generation at its next step and clears caches.
- "Restart engine": exits the app so `studio/launch_app.py` restarts it, returning all RAM/VRAM.
- Batch queue keeps tensors only for the newest generation (bounded RAM).

Launch with the desktop shortcut, which runs `python -m studio.launch_app` (memory cap, crash
explanation + auto-restart, DiT kept on the GPU, no int8 quantization, log in output/logs/web_app.log).
