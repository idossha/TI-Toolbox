#!/usr/bin/env python3
"""Synthesize the job-notification sounds shipped with the desktop app.

Writes ``desktop/src/renderer/assets/sounds/<id>.wav`` (22.05 kHz, 16-bit mono) for every id in
``TI_SOUNDS`` of ``desktop/src/shared/jobNotifications.ts``. Every sound is made here from sines
(additive bells or pulses), so the files carry no third-party licence. Each has a raised-cosine
attack and release and is normalized to -3 dBFS peak. The output is byte-deterministic: no noise,
no timestamps; run it twice and the sha256 sums match.

Usage: ``python3 dev/generate_notification_sounds.py``
"""

import math
import struct
import wave
from pathlib import Path

RATE = 22050
PEAK = 10 ** (-3 / 20)  # -3 dBFS
OUT = Path(__file__).resolve().parent.parent / "desktop/src/renderer/assets/sounds"

# Inharmonic bell partials (ratio, relative amplitude, decay per second).
BELL = ((1.0, 1.0, 5.0), (2.0, 0.45, 8.0), (2.76, 0.3, 11.0), (5.4, 0.12, 18.0))


def bell(freq: float, t: float, partials=BELL) -> float:
    return sum(a * math.exp(-d * t) * math.sin(2 * math.pi * freq * r * t) for r, a, d in partials)


def notes(t: float, onsets, voice) -> float:
    """Sum of `voice(freq, t - onset)` for every (onset, freq) already sounding."""
    return sum(voice(f, t - on) for on, f in onsets if t >= on)


SOUNDS = {
    # Two rising bell notes, G5 then D6.
    "chime": (0.8, lambda t: notes(t, ((0.0, 784.0), (0.12, 1174.7)), bell)),
    # Two soft sine pulses at E5, the second a touch quieter.
    "pulse": (0.45, lambda t: sum(g * math.sin(math.pi * min(1.0, max(0.0, (t - on) / 0.14))) ** 2 * math.sin(2 * math.pi * 659.3 * t) for on, g in ((0.0, 1.0), (0.2, 0.7)))),
    # A short woodblock-like knock.
    "tick": (0.18, lambda t: bell(1760.0, t, ((1.0, 1.0, 30.0), (2.4, 0.4, 45.0)))),
}


def render(duration: float, fn) -> bytes:
    n = int(duration * RATE)
    attack, release = int(0.006 * RATE), int(0.04 * RATE)
    samples = []
    for i in range(n):
        s = fn(i / RATE)
        if i < attack:
            s *= 0.5 - 0.5 * math.cos(math.pi * i / attack)
        if i >= n - release:
            s *= 0.5 + 0.5 * math.cos(math.pi * (i - (n - release)) / release)
        samples.append(s)
    scale = PEAK * 32767 / max(abs(s) for s in samples)
    return b"".join(struct.pack("<h", round(s * scale)) for s in samples)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for sound_id, (duration, fn) in SOUNDS.items():
        path = OUT / f"{sound_id}.wav"
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(render(duration, fn))
        print(f"{path.relative_to(OUT.parents[4])}  {path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
