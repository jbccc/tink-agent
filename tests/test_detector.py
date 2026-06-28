import wave
import numpy as np
from pathlib import Path
from tink_agent.detector import goertzel, ToneDetector
from tink_agent.config import Config

FIX = Path(__file__).parent / "fixtures" / "tones.wav"
SPEECH_FIX = Path(__file__).parent / "fixtures" / "speech.wav"


def _read_wav(path):
    w = wave.open(str(path), "rb")
    n, sr = w.getnframes(), w.getframerate()
    data = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float64)
    return data, sr


def test_goertzel_peaks_at_tone_frequency():
    sr = 16000
    t = np.arange(0, 0.05, 1 / sr)
    sig = (np.sin(2 * np.pi * 1500 * t) * 10000).astype(np.float64)
    assert goertzel(sig, 1500, sr) > goertzel(sig, 2300, sr) * 10


def test_detects_four_slots_in_order_from_fixture():
    data, sr = _read_wav(FIX)
    det = ToneDetector(
        tones={1: 1500, 2: 2300, 3: 3100, 4: 3900},
        rms_min=1000, dominance_min=0.9, debounce_ms=300, sample_rate=sr,
    )
    block = 800
    bursts = []
    for i in range(0, len(data) - block, block):
        slot = det.process(data[i:i + block])
        if slot is not None:
            bursts.append(slot)
    assert bursts[:4] == [1, 2, 3, 4]


def test_real_speech_fires_no_slots():
    # Regression: broadband speech must not trigger any button action.
    # speech.wav is a real recording of spoken words through the mic path.
    data, sr = _read_wav(SPEECH_FIX)
    det = ToneDetector(
        tones={1: 1500, 2: 2300, 3: 3100, 4: 3900},
        rms_min=1000, dominance_min=0.9, debounce_ms=300, sample_rate=sr,
        tonality_min=0.5,
    )
    block = 800
    fires = []
    for i in range(0, len(data) - block, block):
        slot = det.process(data[i:i + block])
        if slot is not None:
            fires.append(slot)
    assert fires == []


def test_debounce_collapses_one_burst_to_one_event():
    sr = 16000
    block = 800
    t = np.arange(0, block / sr, 1 / sr)[:block]
    tone = (np.sin(2 * np.pi * 1500 * t) * 12000).astype(np.float64)
    det = ToneDetector({1: 1500, 2: 2300, 3: 3100, 4: 3900},
                       1000, 0.9, 300, sr)
    events = [det.process(tone) for _ in range(10)]  # 10 blocks = 500 ms continuous
    assert events.count(1) == 1  # only the first block fires


def _make_tone_block(freq, sr=16000, block=800, amp=12000.0):
    t = np.arange(block) / sr
    return (np.sin(2 * np.pi * freq * t) * amp).astype(np.float64)


def test_eight_synthetic_tones_detect_in_slot_order():
    sr, block = 16000, 800
    tones = Config().tones  # {1:1500 ... 8:7153}
    det = ToneDetector(tones=tones, rms_min=1000, dominance_min=0.9,
                       debounce_ms=300, sample_rate=sr, tonality_min=0.5)
    fires = []
    for slot in sorted(tones):                     # 1..8
        tone = _make_tone_block(tones[slot], sr, block)
        for _ in range(8):                         # ~400 ms burst
            r = det.process(tone)
            if r is not None:
                fires.append(r)
        for _ in range(6):                         # silence gap resets press state
            det.process(np.zeros(block))
    assert fires == [1, 2, 3, 4, 5, 6, 7, 8]


def test_real_speech_fires_no_slots_with_eight_bins():
    data, sr = _read_wav(SPEECH_FIX)
    det = ToneDetector(tones=Config().tones, rms_min=1000, dominance_min=0.9,
                       debounce_ms=300, sample_rate=sr, tonality_min=0.5)
    block = 800
    fires = []
    for i in range(0, len(data) - block, block):
        slot = det.process(data[i:i + block])
        if slot is not None:
            fires.append(slot)
    assert fires == []
