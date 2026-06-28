import json
from pathlib import Path

CFG = Path(__file__).resolve().parent.parent / "ting-config" / "config.json"


def test_ting_config_is_valid_json_with_two_clean_presets():
    cfg = json.loads(CFG.read_text())  # strict JSON; raises if malformed
    presets = {p["pos"]: p for p in cfg["presets"]}
    assert set(presets) >= {0, 1}, "need orange pos 0 (mode A) and pos 1 (mode B)"
    for pos, expected_pitch in ((0, 0.0), (1, 10.5)):
        p = presets[pos]
        # Voice must stay clean: no modulation keys, only a SAMPLE effect.
        assert "handle" not in p and "shake" not in p and "lfo" not in p
        effects = [e["effect"] for e in p["list"]]
        assert effects == ["SAMPLE"], f"pos {pos} must be SAMPLE-only, got {effects}"
        assert p["list"][0]["pitch"] == expected_pitch
