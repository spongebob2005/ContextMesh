"""Add narration + music to the ContextMesh walkthrough video.

Pipeline:
  1. narration per scene via edge-tts (neural voice, free, no API key) —
     each line is speed-fit to its scene window
  2. music bed synthesized locally with numpy: ambient pad over a slow chord
     progression, soft arpeggio, transition shimmers, low booms on the logo
     reveals — side-chain ducked under the voice
  3. mix -> 16-bit WAV -> mux into the MP4 (video stream copied, AAC audio)

Run:  python -m scripts.add_audio
Needs: edge-tts (pip), network for the voice; ffmpeg via imageio-ffmpeg.
"""
from __future__ import annotations

import asyncio
import random
import subprocess
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / "brand" / "contextmesh_walkthrough.mp4"
WAV = ROOT / "brand" / "contextmesh_audio.wav"
CACHE = Path("/tmp/opencode/cm_audio")

SR = 44100
VOICE = "en-US-AndrewNeural"

# (scene, start_s, dur_s) — must match SCENES in scripts/render_video.py
SCENES = [
    ("intro", 0.0, 6.0),
    ("problem", 6.0, 6.5),
    ("graph", 12.5, 6.0),
    ("plan", 18.5, 6.5),
    ("learn", 25.0, 6.5),
    ("results", 31.5, 6.5),
    ("outro", 38.0, 5.0),
]
TOTAL = sum(d for _, _, d in SCENES)

# narration: (scene name, line, start offset inside the scene, window seconds)
LINES = [
    ("intro", "This is ContextMesh — a memory layer for AI agents, built on HydraDB.", 1.0, 5.0),
    ("problem", "Today, agents load every tool on every step — and pay for it on every turn.", 0.35, 5.85),
    ("graph", "Instead, keep skills, tools, servers and entities as a graph inside HydraDB.", 0.5, 5.3),
    ("plan", "One call before the model runs: two round trips, five tools instead of sixteen, every mention already resolved.", 0.5, 5.8),
    ("learn", "Every session writes back usage and new aliases — so the graph gets sharper the more it is used.", 0.6, 5.7),
    ("results", "Same model, same tasks: four of five correct versus zero. One twenty-eight concurrent sessions, no errors.", 0.6, 5.7),
    ("outro", "ContextMesh. Agent memory, as a graph.", 2.4, 2.5),
]
RATES = [0, 8, 16, 20, 24, 28, 32]  # % speed-up candidates, first that fits its window wins


def ffmpeg() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def tts(line: str, rate: int, out: Path) -> None:
    import edge_tts

    async def run() -> None:
        kwargs = {"rate": f"+{rate}%"} if rate else {}
        c = edge_tts.Communicate(line, VOICE, **kwargs)
        await c.save(str(out))

    last: Exception | None = None
    for attempt in range(8):  # the endpoint throttles bursts; back off and retry
        try:
            asyncio.run(run())
            if out.stat().st_size > 2000:
                return
            raise RuntimeError("empty audio")
        except Exception as exc:  # noqa: BLE001
            last = exc
            out.unlink(missing_ok=True)
            time.sleep(1.0 * (attempt + 1) + random.random() * 0.7)
    raise RuntimeError(f"tts failed for rate {rate}%: {last}")


def decode(path: Path) -> np.ndarray:
    wav_tmp = path.with_suffix(".wav")
    subprocess.run(
        [ffmpeg(), "-y", "-loglevel", "error", "-i", str(path),
         "-ar", str(SR), "-ac", "1", "-f", "wav", str(wav_tmp)],
        check=True,
    )
    with wave.open(str(wav_tmp), "rb") as w:
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return data.astype(np.float32) / 32768.0


def fit_line(index: int, line: str, window: float) -> np.ndarray:
    """Synthesize narration, speeding it up until it fits the scene window."""
    CACHE.mkdir(parents=True, exist_ok=True)
    chosen: tuple[int, np.ndarray] | None = None
    for rate in RATES:
        mp3 = CACHE / f"line{index}_{rate}.mp3"
        if not mp3.exists() or mp3.stat().st_size < 2000:
            try:
                tts(line, rate, mp3)
            except RuntimeError:  # service kept refusing this rate; try the next
                continue
        try:
            audio = decode(mp3)
        except subprocess.CalledProcessError:  # truncated cache entry — rebuild once
            mp3.unlink(missing_ok=True)
            try:
                tts(line, rate, mp3)
                audio = decode(mp3)
            except (RuntimeError, subprocess.CalledProcessError):
                continue
        chosen = (rate, audio)
        if len(audio) / SR <= window:
            break
        time.sleep(0.4)
    assert chosen is not None
    return chosen[1]


# ----------------------------------------------------------------- music bed

CHORDS = [
    [110.00, 164.81, 261.63],  # Am
    [87.31, 174.61, 261.63],   # F
    [130.81, 196.00, 329.63],  # C
    [98.00, 196.00, 293.66],   # G
]


def synth_music() -> np.ndarray:
    n = int(SR * TOTAL)
    t = np.arange(n) / SR
    music = np.zeros(n, dtype=np.float64)

    seg = TOTAL / 8.0
    for k in range(8):
        chord = CHORDS[k % len(CHORDS)]
        start = k * seg
        end = start + seg
        # gentle window, overlapping neighbours
        a0 = max(0.0, start - 0.7)
        a1 = min(TOTAL, end + 0.7)
        i0, i1 = int(a0 * SR), int(a1 * SR)
        tt = np.arange(i1 - i0) / SR
        env = np.ones_like(tt)
        atk = int(1.0 * SR)
        rel = int(1.2 * SR)
        env[:atk] = np.linspace(0, 1, atk) ** 1.5
        env[-rel:] *= np.linspace(1, 0, rel) ** 1.5
        lfo = 0.85 + 0.15 * np.sin(2 * np.pi * 0.07 * (t[i0:i1] + start))
        pad = np.zeros_like(tt)
        for f in chord:
            pad += np.sin(2 * np.pi * f * tt)
            pad += 0.33 * np.sin(2 * np.pi * 2 * f * tt + 0.6)
            pad += 0.12 * np.sin(2 * np.pi * 3 * f * tt + 1.2)
            pad += 0.5 * np.sin(2 * np.pi * (f + 0.4) * tt)
        music[i0:i1] += pad * env * lfo * (0.16 / len(chord))

        # sub bass on the root
        root = chord[0] / 2
        music[i0:i1] += np.sin(2 * np.pi * root * tt) * env * 0.10

    # soft arpeggio (8th notes at 96 bpm), chord tones an octave up
    eighth = 0.3125
    note_t = 0.0
    j = 0
    while note_t < TOTAL - 0.4:
        chord = CHORDS[int(note_t / seg) % len(CHORDS)]
        f = chord[j % len(chord)] * 2
        i0 = int(note_t * SR)
        dur = int(0.5 * SR)
        tt = np.arange(min(dur, n - i0)) / SR
        env = np.exp(-tt / 0.18) * 0.5
        tone = np.sin(2 * np.pi * f * tt) + 0.25 * np.sin(2 * np.pi * 2 * f * tt)
        music[i0:i0 + len(tt)] += tone * env * 0.05
        note_t += eighth
        j += 1

    # transition shimmers: filtered noise swell just before each scene cut
    rng = np.random.default_rng(7)
    for _, start, _ in SCENES[1:]:
        length = int(0.8 * SR)
        i0 = max(0, int(start * SR) - length)
        noise = rng.standard_normal(length)
        kernel = np.ones(24) / 24  # cheap low-pass
        noise = np.convolve(noise, kernel, mode="same")
        tt = np.linspace(0, 1, length)
        music[i0:i0 + length] += noise * (tt ** 2) * 0.045

    # low booms on the two logo/title reveals
    for at in (3.2, 38.0 + 2.0):
        length = int(1.6 * SR)
        i0 = max(0, min(n - length, int(at * SR)))
        tt = np.arange(length) / SR
        sweep = 55.0 - 18.0 * np.clip(tt / 1.2, 0, 1)
        boom = np.sin(2 * np.pi * sweep * tt) * np.exp(-tt / 0.45)
        music[i0:i0 + length] += boom * 0.20

    # global fades
    fin, fout = int(1.0 * SR), int(1.4 * SR)
    music[:fin] *= np.linspace(0, 1, fin)
    music[-fout:] *= np.linspace(1, 0, fout)
    return music


# ---------------------------------------------------------------------- mix


def smooth(x: np.ndarray, win: int = 4410) -> np.ndarray:
    kernel = np.ones(win) / win
    return np.convolve(x, kernel, mode="same")


def main() -> int:
    print(f"voice: {VOICE} · {TOTAL:.1f}s timeline")

    voice = np.zeros(int(SR * TOTAL), dtype=np.float32)
    starts = {name: s for name, s, _ in SCENES}
    for idx, (scene, line, offset, window) in enumerate(LINES):
        clip = fit_line(idx, line, window)
        at = int((starts[scene] + offset) * SR)
        clip = clip.copy()
        ramp = int(0.005 * SR)
        clip[:ramp] *= np.linspace(0, 1, ramp)
        clip[-ramp:] *= np.linspace(1, 0, ramp)
        end = min(len(voice), at + len(clip))
        voice[at:end] += clip[: end - at]
        print(f"  {scene:<8} {len(clip) / SR:5.2f}s at {starts[scene] + offset:5.1f}s")

    peak = float(np.max(np.abs(voice))) or 1.0
    voice *= 0.90 / peak

    music = synth_music().astype(np.float32)
    env = smooth(np.abs(voice), 4410)
    duck = 1.0 - 0.5 * np.clip(env / 0.05, 0, 1)
    music *= duck * 0.30
    mpeak = float(np.max(np.abs(music))) or 1.0
    music *= 0.12 / mpeak

    mix = voice + music
    m = float(np.max(np.abs(mix)))
    if m > 0.98:
        mix *= 0.98 / m

    stereo = np.stack([mix, mix], axis=1)
    CACHE.mkdir(parents=True, exist_ok=True)
    with wave.open(str(WAV), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(stereo, -1, 1) * 32767).astype(np.int16).tobytes())
    print(f"audio -> {WAV}")

    tmp = VIDEO.with_suffix(".mux.mp4")
    subprocess.run(
        [ffmpeg(), "-y", "-loglevel", "error", "-i", str(VIDEO), "-i", str(WAV),
         "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", str(tmp)],
        check=True,
    )
    tmp.replace(VIDEO)
    print(f"muxed -> {VIDEO}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
