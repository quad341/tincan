#!/usr/bin/env python3
"""Voice-agent latency PoC — keyless skeleton.

The §3 fake-transport harness from docs/designs/voice-latency-testing.md, built
with ZERO API keys, no GPU, and pure stdlib (PulseAudio CLI for audio I/O so we
dodge all the cp314 audio-wheel risk).

It measures the metric that matters — EERL (end-to-end response latency): from the
moment the speaker stops (endpoint detected) to the first audio sample we emit back.

The pipeline is the real one:

    mic ─► VAD(energy) ─► STT ─► LLM ─► TTS ─► speaker
                            └──── per-stage timestamps ────┘

Every ML stage here is a STUB with a latency knob, so you can model a real cloud/
local backend ("what if LLM time-to-first-token is 400ms?") and watch EERL change.
Swapping in a real backend later is a one-function change — see stt()/llm()/tts().

The headline lever: --stream vs --batch. In --stream we hand the first sentence of
the LLM output to TTS the instant it's ready; in --batch we wait for the whole LLM
response first. Same components, very different EERL. That gap is the whole point.

Usage:
    # live: talk to it, it endpoints, replies via espeak, prints latency. Ctrl-C to stop.
    python spikes/voice_latency_poc.py mic

    # deterministic: run N canned turns, no mic, isolates STT+LLM+TTS from VAD.
    python spikes/voice_latency_poc.py synthetic -n 10

    # model a cloud stack and compare batch vs stream:
    python spikes/voice_latency_poc.py synthetic -n 20 --stt-delay 0.12 \
        --llm-ttft 0.35 --llm-inter-token 0.01 --stream
    python spikes/voice_latency_poc.py synthetic -n 20 --stt-delay 0.12 \
        --llm-ttft 0.35 --llm-inter-token 0.01 --batch
"""
from __future__ import annotations

import argparse
import math
import struct
import subprocess
import time
from dataclasses import dataclass

RATE = 16000          # Hz — matches HFP wideband (mSBC); narrowband would be 8000
FRAME_MS = 20
FRAME_SAMPLES = RATE * FRAME_MS // 1000
FRAME_BYTES = FRAME_SAMPLES * 2   # s16le mono

CANNED_REPLY = (
    "Sure, I can help with that. Tuesday the ninth at two in the afternoon works. "
    "Should I go ahead and book it?"
)


# ─────────────────────────────── config / knobs ───────────────────────────────
@dataclass
class Cfg:
    # VAD
    vad_threshold: float = 500.0     # RMS gate; tune to your mic/room
    start_frames: int = 3            # consecutive speech frames to latch "speaking"
    hangover_ms: int = 500           # trailing silence that ends an utterance
    # STT stub
    stt_delay: float = 0.0           # simulated STT latency (s) after endpoint
    # LLM stub
    llm_ttft: float = 0.0            # simulated time-to-first-token (s)
    llm_inter_token: float = 0.0     # simulated per-token delay (s)
    # pipeline shape
    stream: bool = True  # True: TTS starts on first sentence; False: waits for full reply
    voice: str = "en"


# ─────────────────────────────── timing record ────────────────────────────────
@dataclass
class Turn:
    t_endpoint: float = 0.0
    t_stt_done: float = 0.0
    t_llm_first: float = 0.0
    t_tts_first_audio: float = 0.0
    transcript: str = ""
    reply: str = ""

    @property
    def eerl(self) -> float:
        return self.t_tts_first_audio - self.t_endpoint

    def breakdown(self) -> dict[str, float]:
        return {
            "stt": self.t_stt_done - self.t_endpoint,
            "llm_ttft": self.t_llm_first - self.t_stt_done,
            "tts_ttfa": self.t_tts_first_audio - self.t_llm_first,
            "EERL": self.eerl,
        }


# ─────────────────────────────── stages (stubs) ───────────────────────────────
# Each stage is intentionally tiny and pluggable. To go real:
#   stt(): replace body with a streaming Deepgram/AssemblyAI / faster-whisper call.
#   llm(): replace with a streaming Claude / local-LLM call (yield tokens).
#   tts(): replace espeak-ng with Cartesia/ElevenLabs streaming / Piper.

def stt(_audio: bytes, cfg: Cfg) -> str:
    """STUB: pretend to transcribe. Real impl returns recognized text."""
    if cfg.stt_delay:
        time.sleep(cfg.stt_delay)
    return "I'd like to book an appointment next week."


def llm(_transcript: str, cfg: Cfg):
    """STUB: stream a canned reply token-by-token. Real impl streams model tokens."""
    first = True
    for tok in CANNED_REPLY.split(" "):
        if first:
            if cfg.llm_ttft:
                time.sleep(cfg.llm_ttft)
            first = False
        elif cfg.llm_inter_token:
            time.sleep(cfg.llm_inter_token)
        yield tok + " "


def _first_sentence(tokens, sink) -> str:
    """Pull tokens until a sentence boundary; return that sentence, stash the rest."""
    buf = ""
    for tok in tokens:
        buf += tok
        if tok.strip().endswith((".", "?", "!")):
            sink["rest"] = tokens   # remaining generator
            return buf
    return buf


def tts_speak(text: str, cfg: Cfg) -> float:
    """Synthesize via espeak-ng, return wall-clock when first audio bytes exist (TTFA),
    then play. Returns the first-audio timestamp."""
    proc = subprocess.Popen(
        ["espeak-ng", "-v", cfg.voice, "--stdout", text],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    first_chunk = proc.stdout.read(4096)        # blocks until first synthesized audio
    t_first = time.monotonic()
    rest = proc.stdout.read()
    proc.wait()
    # play it so you actually hear the reply (latency already recorded above)
    subprocess.run(["paplay"], input=first_chunk + rest,
                   stderr=subprocess.DEVNULL, check=False)
    return t_first


# ─────────────────────────────── pipeline ─────────────────────────────────────
def run_pipeline(audio: bytes, cfg: Cfg) -> Turn:
    """One full turn. t_endpoint is set by the caller (= now)."""
    turn = Turn(t_endpoint=time.monotonic())

    turn.transcript = stt(audio, cfg)
    turn.t_stt_done = time.monotonic()

    tokens = llm(turn.transcript, cfg)
    if cfg.stream:
        sink: dict = {}
        sentence = _first_sentence(tokens, sink)
        turn.t_llm_first = time.monotonic()        # first sentence ready
        turn.reply = sentence
        turn.t_tts_first_audio = tts_speak(sentence, cfg)
        for _ in sink.get("rest", []):             # drain remaining tokens (already counted)
            pass
    else:
        reply = "".join(tokens)                    # BATCH: wait for the whole thing
        turn.t_llm_first = time.monotonic()
        turn.reply = reply
        turn.t_tts_first_audio = tts_speak(reply, cfg)
    return turn


# ─────────────────────────────── VAD (energy) ─────────────────────────────────
def rms(frame: bytes) -> float:
    n = len(frame) // 2
    if not n:
        return 0.0
    samples = struct.unpack(f"<{n}h", frame)
    return math.sqrt(sum(s * s for s in samples) / n)


def _calibrate(rec, seconds: float = 1.5) -> float:
    """Sample ambient noise, return a VAD threshold comfortably above it."""
    frames = int(seconds * 1000 / FRAME_MS)
    levels = []
    for _ in range(frames):
        f = rec.stdout.read(FRAME_BYTES)
        if len(f) < FRAME_BYTES:
            break
        levels.append(rms(f))
    floor = (sum(levels) / len(levels)) if levels else 200.0
    return max(300.0, floor * 3 + 150)   # 3x ambient + margin


def mic_loop(cfg: Cfg) -> None:
    """Capture from default source, endpoint utterances, run the pipeline per turn."""
    hangover_frames = cfg.hangover_ms // FRAME_MS
    rec = subprocess.Popen(
        ["parec", "--format=s16le", f"--rate={RATE}", "--channels=1"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    print("⚙  calibrating ambient noise — stay quiet for ~1.5s ...", flush=True)
    cfg.vad_threshold = _calibrate(rec)
    mode = "STREAM" if cfg.stream else "BATCH"
    print(f"✅ VAD threshold = {cfg.vad_threshold:.0f}   mode = {mode}\n"
          f"{'─'*64}\n"
          f"  HOW TO USE:  say a sentence, then GO SILENT.\n"
          f"  Watch THIS terminal (ignore the robot voice — it's a throwaway stub).\n"
          f"  Ctrl-C when done.\n{'─'*64}\n", flush=True)
    turns: list[Turn] = []
    speaking = False
    speech_run = 0
    silence_run = 0
    buf = bytearray()
    print("🎙  listening...", flush=True)
    try:
        while True:
            frame = rec.stdout.read(FRAME_BYTES)
            if len(frame) < FRAME_BYTES:
                break
            energy = rms(frame)
            if energy >= cfg.vad_threshold:
                speech_run += 1
                silence_run = 0
                if not speaking and speech_run >= cfg.start_frames:
                    speaking = True
                    buf.clear()
                    print("🔴 hearing you speak...", flush=True)
                if speaking:
                    buf.extend(frame)
            else:
                speech_run = 0
                if speaking:
                    buf.extend(frame)
                    silence_run += 1
                    if silence_run >= hangover_frames:
                        # ENDPOINT — clock starts the instant we decide they stopped
                        print("⏳ you stopped → thinking...", flush=True)
                        turn = run_pipeline(bytes(buf), cfg)
                        turns.append(turn)
                        print(f"🔊 reply: \"{turn.reply.strip()}\"", flush=True)
                        _print_turn(turn)
                        print("\n🎙  listening...", flush=True)
                        speaking = False
                        buf.clear()
    except KeyboardInterrupt:
        pass
    finally:
        rec.terminate()
    _print_summary(turns, cfg)


def process_file(cfg: Cfg, path: str) -> None:
    """Run the real VAD + pipeline over a pre-recorded raw s16le/16k/mono clip.
    Fits a headless workflow: record a clip, process it, report — no live terminal."""
    data = open(path, "rb").read()
    hangover_frames = cfg.hangover_ms // FRAME_MS
    # auto-calibrate from the quietest 25 frames (robust to a clip that's mostly speech)
    frames = [data[i:i + FRAME_BYTES] for i in range(0, len(data) - FRAME_BYTES, FRAME_BYTES)]
    energies = [rms(f) for f in frames]
    floor = sorted(energies)[:25]
    cfg.vad_threshold = max(300.0, (sum(floor) / len(floor)) * 3 + 150) if floor else 500.0
    print(f"▶  file: {path}  ({len(frames)*FRAME_MS/1000:.1f}s)  "
          f"VAD threshold={cfg.vad_threshold:.0f}  {'STREAM' if cfg.stream else 'BATCH'}\n")
    turns: list[Turn] = []
    speaking = False
    speech_run = silence_run = 0
    buf = bytearray()
    for f in frames:
        if rms(f) >= cfg.vad_threshold:
            speech_run += 1
            silence_run = 0
            if not speaking and speech_run >= cfg.start_frames:
                speaking = True
                buf.clear()
            if speaking:
                buf.extend(f)
        else:
            speech_run = 0
            if speaking:
                buf.extend(f)
                silence_run += 1
                if silence_run >= hangover_frames:
                    turn = run_pipeline(bytes(buf), cfg)
                    turn.reply = turn.reply.strip()
                    turns.append(turn)
                    print(f"  utterance {len(turns)}: {len(buf)//FRAME_BYTES*FRAME_MS}ms audio "
                          f"→ reply \"{turn.reply}\"")
                    _print_turn(turn, idx=len(turns))
                    speaking = False
                    buf.clear()
    if not turns:
        print("  (no utterance detected — clip too quiet or all-silence)")
    _print_summary(turns, cfg)


def synthetic_loop(cfg: Cfg, n: int) -> None:
    """No mic: fire N canned turns. Isolates STT+LLM+TTS latency from VAD/room noise."""
    print(f"▶  synthetic: {n} turns, {'STREAM' if cfg.stream else 'BATCH'} mode\n")
    turns = []
    for i in range(n):
        turn = run_pipeline(b"", cfg)
        turns.append(turn)
        _print_turn(turn, idx=i + 1)
    _print_summary(turns, cfg)


# ─────────────────────────────── reporting ────────────────────────────────────
def _print_turn(turn: Turn, idx: int | None = None) -> None:
    b = turn.breakdown()
    tag = f"turn {idx}" if idx else "turn"
    print(f"  {tag:8}  stt={b['stt']*1000:6.0f}ms  "
          f"llm_ttft={b['llm_ttft']*1000:6.0f}ms  "
          f"tts_ttfa={b['tts_ttfa']*1000:6.0f}ms  "
          f"│ EERL={b['EERL']*1000:6.0f}ms")


def _pct(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    k = max(0, min(len(s) - 1, int(round((p / 100) * (len(s) - 1)))))
    return s[k]


def _print_summary(turns: list[Turn], cfg: Cfg) -> None:
    if not turns:
        print("\n(no turns recorded)")
        return
    eerls = [t.eerl * 1000 for t in turns]
    print(f"\n── EERL over {len(turns)} turns ({'STREAM' if cfg.stream else 'BATCH'}) ──")
    print(f"   p50={_pct(eerls,50):.0f}ms  p90={_pct(eerls,90):.0f}ms  "
          f"p99={_pct(eerls,99):.0f}ms  min={min(eerls):.0f}  max={max(eerls):.0f}")
    target = 800
    verdict = "✅ under" if _pct(eerls, 90) <= target else "❌ over"
    print(f"   target <{target}ms p90 → {verdict}")


# ─────────────────────────────── cli ──────────────────────────────────────────
def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="mode", required=True)
    pm = sub.add_parser("mic", help="live: talk to it")
    ps = sub.add_parser("synthetic", help="deterministic: N canned turns")
    ps.add_argument("-n", type=int, default=10)
    pf = sub.add_parser("file", help="process a recorded raw s16le/16k/mono clip")
    pf.add_argument("path")
    for sp in (pm, ps, pf):
        sp.add_argument("--vad-threshold", type=float, default=Cfg.vad_threshold)
        sp.add_argument("--hangover-ms", type=int, default=Cfg.hangover_ms)
        sp.add_argument("--stt-delay", type=float, default=Cfg.stt_delay)
        sp.add_argument("--llm-ttft", type=float, default=Cfg.llm_ttft)
        sp.add_argument("--llm-inter-token", type=float, default=Cfg.llm_inter_token)
        sp.add_argument("--voice", default=Cfg.voice)
        grp = sp.add_mutually_exclusive_group()
        grp.add_argument("--stream", dest="stream", action="store_true", default=True)
        grp.add_argument("--batch", dest="stream", action="store_false")
    a = p.parse_args()
    cfg = Cfg(
        vad_threshold=a.vad_threshold, hangover_ms=a.hangover_ms,
        stt_delay=a.stt_delay, llm_ttft=a.llm_ttft,
        llm_inter_token=a.llm_inter_token, stream=a.stream, voice=a.voice,
    )
    if a.mode == "mic":
        mic_loop(cfg)
    elif a.mode == "file":
        process_file(cfg, a.path)
    else:
        synthetic_loop(cfg, a.n)


if __name__ == "__main__":
    main()
