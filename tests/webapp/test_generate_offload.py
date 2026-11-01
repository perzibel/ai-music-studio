"""The brief's generate_job tests stub out studio.generate.generate entirely, so they never
exercise its own --offload wiring. This file tests that directly: the single most
safety-critical line in the plan (Global Constraints: offload from the first attempt,
not only as a hang-prone OOM retry).
"""
import studio.generate as generate_module
import studio.render as render_module


def test_generate_passes_offload_flag_to_run_ace_by_default(monkeypatch, tmp_path):
    monkeypatch.setattr(render_module, "OUTPUT_DIR", tmp_path)
    captured_args = []

    def fake_run_ace(args, timeout=3600):
        captured_args.append(args)
        return {"error": "stop before real work"}

    monkeypatch.setattr(generate_module, "run_ace", fake_run_ace)
    generate_module.generate("an idea", name="s", takes=1)
    assert "--offload" in captured_args[0]


def test_generate_omits_offload_flag_when_disabled(monkeypatch, tmp_path):
    monkeypatch.setattr(render_module, "OUTPUT_DIR", tmp_path)
    captured_args = []

    def fake_run_ace(args, timeout=3600):
        captured_args.append(args)
        return {"error": "stop before real work"}

    monkeypatch.setattr(generate_module, "run_ace", fake_run_ace)
    generate_module.generate("an idea", name="s", takes=1, offload=False)
    assert "--offload" not in captured_args[0]
