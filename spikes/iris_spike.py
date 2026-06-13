#!/usr/bin/env python3
"""Iris — AI voice agent on an active HFP call.

Pipeline:
    pw-record(bluez_input) → VAD(energy) → STT(faster-whisper)
    → Claude Haiku 4.5 (streaming) → TTS(espeak-ng) → pw-play(bluez_output)

Usage:
    python spikes/iris_spike.py --device-mac <bt-mac>
    python spikes/iris_spike.py --device-mac <bt-mac> --no-calibrate --vad-threshold 600
    python spikes/iris_spike.py --device-mac <bt-mac> --model base.en --hangover-ms 700

Prerequisites (see startup check output for install commands):
    pip install faster-whisper anthropic
    dnf install espeak-ng sox pipewire-utils
    ANTHROPIC_API_KEY must be set in the environment.
"""
from __future__ import annotations

import argparse
import importlib
import math
import os
import shutil
import struct
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterator

# ──────────────────────────── audio constants ──────────────────────────────────

RATE = 8000           # CVSD narrowband HFP — 8 kHz
CHANNELS = 1
FRAME_MS = 20
FRAME_SAMPLES = RATE * FRAME_MS // 1000   # 160 samples per frame
FRAME_BYTES = FRAME_SAMPLES * 2            # 320 bytes (s16le mono)

# ──────────────────────────── Iris persona ─────────────────────────────────────

# espeak-ng flags tuned for 8 kHz narrowband clarity
ESPEAK_ARGS = ["espeak-ng", "--stdout", "-v", "en-us", "-s", "135", "-p", "55"]

SYSTEM_PROMPT = """You are Iris, a warm and concise AI assistant helping Jim on a phone call.

Constraints:
- Every reply must be 1–2 short sentences. Telephone attention span — be crisp.
- No lists, no preamble, no "Sure!" filler. Get to the point.
- Contractions are good. Sound conversational, not robotic.
- You relay information and take notes for Jim. You cannot take autonomous action.
- You have already introduced yourself. Do not re-introduce unless directly asked.
- Never mention Claude, Anthropic, or any underlying technology by name.
- Do not discuss politics, religion, health advice, or sensitive personal matters \
— redirect: "That's something Jim can help with."

Identity questions:
- "Who are you?" / "What are you?" → "I'm Iris, an AI assistant helping Jim with this call."
- "Are you a robot?" / "Is this AI?" → "Yes — I'm Iris, an AI.\
 Jim's here if you'd prefer to speak with him."

Handoff triggers — speak the handoff line, then signal DEGRADED mode:
- "Get Jim" / "I want to talk to Jim" → "Of course — I'll let Jim know right away. One moment."
- "I don't want to talk to an AI" → "Totally understandable. I'll hand you to Jim now."

Scope boundaries:
- Anything requiring real-world action: "That's something Jim can help you with directly."
- Caller seems distressed or confused: "Let me get Jim for you."
"""

DISCLOSURE = "Hi, I'm Iris — an AI helping Jim; mind if I chat a moment?"
RECOVERY_LINE = "I'm having trouble right now — let me hand you to Jim."
HANDOFF_LINE = "Of course — I'll let Jim know right away. One moment."

HANDOFF_SIGNALS = [
    "get jim",
    "talk to jim",
    "speak to jim",
    "i want jim",
    "don't want to talk to an ai",
    "prefer to speak to",
]

MAX_HISTORY = 20
MAX_STT_WORDS = 200

# ──────────────────────────── config ───────────────────────────────────────────


@dataclass
class Cfg:
    device_mac: str = ""
    vad_threshold: float = 500.0
    hangover_ms: int = 500
    model_name: str = "tiny.en"
    no_calibrate: bool = False

    @property
    def mac_fragment(self) -> str:
        """Lowercase MAC with colons → underscores: d0_6b_78_33_46_20"""
        return self.device_mac.replace(":", "_").lower()

    @property
    def hangover_frames(self) -> int:
        return self.hangover_ms // FRAME_MS


# ──────────────────────────── timing / EERL ────────────────────────────────────


@dataclass
class Turn:
    t_endpoint: float = 0.0        # when far-end speech ended (silence hangover)
    t_stt_done: float = 0.0        # when faster-whisper returned transcript
    t_llm_first: float = 0.0       # when first LLM sentence was ready
    t_tts_first_audio: float = 0.0 # when pw-play started consuming first audio

    @property
    def eerl(self) -> float:
        return self.t_tts_first_audio - self.t_endpoint

    def breakdown(self) -> dict[str, float]:
        return {
            "stt":      self.t_stt_done - self.t_endpoint,
            "llm_ttft": self.t_llm_first - self.t_stt_done,
            "tts_ttfa": self.t_tts_first_audio - self.t_llm_first,
            "EERL":     self.eerl,
        }


@dataclass
class SessionStats:
    turns: list[Turn] = field(default_factory=list)
    empty_stt_count: int = 0
    api_errors: int = 0
    degraded: bool = False


# ──────────────────────────── prerequisites ────────────────────────────────────


def _check_prereqs(cfg: Cfg) -> tuple[str, str]:
    """Print ✓/✗ prereq lines, discover PipeWire nodes. Returns (source_node, sink_node)."""
    print("Checking prerequisites...")
    all_ok = True

    def chk(label: str, ok: bool, fix: str) -> bool:
        print(f"  {'✓' if ok else '✗'} {label}")
        if not ok:
            print(f"      → {fix}")
        return ok

    all_ok &= chk(
        "ANTHROPIC_API_KEY set",
        bool(os.environ.get("ANTHROPIC_API_KEY")),
        "export ANTHROPIC_API_KEY=sk-ant-...",
    )
    all_ok &= chk(
        "espeak-ng installed",
        bool(shutil.which("espeak-ng")),
        "dnf install espeak-ng   # or: apt install espeak-ng",
    )
    all_ok &= chk(
        "sox installed",
        bool(shutil.which("sox")),
        "dnf install sox   # or: apt install sox",
    )
    all_ok &= chk(
        "pw-record installed",
        bool(shutil.which("pw-record")),
        "dnf install pipewire-utils",
    )
    all_ok &= chk(
        "pw-play installed",
        bool(shutil.which("pw-play")),
        "dnf install pipewire-utils",
    )

    try:
        importlib.import_module("faster_whisper")
        fw_ok = True
    except ImportError:
        fw_ok = False
    all_ok &= chk(
        "faster-whisper installed",
        fw_ok,
        "pip install faster-whisper",
    )

    try:
        importlib.import_module("anthropic")
        anth_ok = True
    except ImportError:
        anth_ok = False
    all_ok &= chk(
        "anthropic SDK installed",
        anth_ok,
        "pip install anthropic",
    )

    if not all_ok:
        print("\nResolve the above issues, then retry.")
        sys.exit(1)

    # Node discovery
    print(f"\nDiscovering PipeWire nodes for {cfg.device_mac} ...")
    source_node = _find_pw_node(cfg.mac_fragment, "outputs", "bluez_input")
    sink_node   = _find_pw_node(cfg.mac_fragment, "inputs",  "bluez_output")
    print(f"  {'✓' if source_node else '✗'} Source (bluez_input):  {source_node or 'NOT FOUND'}")
    print(f"  {'✓' if sink_node   else '✗'} Sink   (bluez_output): {sink_node   or 'NOT FOUND'}")

    if not (source_node and sink_node):
        print(
            "\nBluetooth HFP nodes not found. Ensure:\n"
            "  - An active HFP call is in progress on the device\n"
            f"  - Device {cfg.device_mac} is connected via HFP (hci1)\n"
            "  - PipeWire is running with BlueZ backend\n"
            "  - Try: pactl list sources | grep bluez"
        )
        sys.exit(1)

    return source_node, sink_node


def _find_pw_node(mac_frag: str, direction: str, keyword: str) -> str | None:
    """Find a PipeWire node name from pw-link --list-{direction} output.

    Matches lines containing both `keyword` and the lowercase MAC fragment.
    Extracts the node name (the part before the colon in node:port).
    """
    try:
        r = subprocess.run(
            ["pw-link", f"--list-{direction}"],
            capture_output=True, text=True, timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

    for line in r.stdout.splitlines():
        lo = line.lower()
        if keyword in lo and mac_frag in lo:
            for tok in line.split():
                if keyword in tok.lower() and ":" in tok:
                    return tok.split(":")[0]
    return None


# ──────────────────────────── VAD (energy) ─────────────────────────────────────


def _rms(frame: bytes) -> float:
    n = len(frame) // 2
    if not n:
        return 0.0
    samples = struct.unpack(f"<{n}h", frame)
    return math.sqrt(sum(s * s for s in samples) / n)


def _calibrate_vad(rec: subprocess.Popen, seconds: float = 1.5) -> tuple[float, float]:
    """Sample ambient audio. Returns (noise_floor_rms, vad_threshold_rms)."""
    n_frames = int(seconds * 1000 / FRAME_MS)
    levels = []
    for _ in range(n_frames):
        f = rec.stdout.read(FRAME_BYTES)
        if len(f) < FRAME_BYTES:
            break
        levels.append(_rms(f))
    floor = (sum(levels) / len(levels)) if levels else 200.0
    threshold = max(300.0, floor * 3.0 + 150.0)
    return floor, threshold


# ──────────────────────────── STT ──────────────────────────────────────────────

_whisper_cache: dict[str, object] = {}


def _load_whisper(model_name: str):
    if model_name not in _whisper_cache:
        from faster_whisper import WhisperModel
        _whisper_cache[model_name] = WhisperModel(
            model_name, device="cpu", compute_type="int8"
        )
    return _whisper_cache[model_name]


def _transcribe(audio_bytes: bytes, cfg: Cfg) -> str:
    """Resample 8 kHz s16le → 16 kHz float32 via sox, transcribe via faster-whisper."""
    import numpy as np

    # sox: raw s16le 8 kHz → raw s16le 16 kHz (2× upsample with proper resampling)
    sox_proc = subprocess.run(
        [
            "sox",
            "-r", "8000", "-e", "signed-integer", "-b", "16", "-c", "1", "-t", "raw", "-",
            "-r", "16000", "-e", "signed-integer", "-b", "16", "-c", "1", "-t", "raw", "-",
        ],
        input=audio_bytes,
        capture_output=True,
    )
    audio_f32 = (
        np.frombuffer(sox_proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    )

    model = _load_whisper(cfg.model_name)
    segments, _ = model.transcribe(audio_f32, language="en", beam_size=1)
    text = " ".join(seg.text.strip() for seg in segments).strip()

    # Hallucination guard: truncate absurdly long transcripts
    words = text.split()
    if len(words) > MAX_STT_WORDS:
        print(f"\r  [warn] STT truncated {len(words)} → {MAX_STT_WORDS} words", flush=True)
        text = " ".join(words[:MAX_STT_WORDS]) + " […]"

    return text


# ──────────────────────────── LLM ──────────────────────────────────────────────


class _ApiError(Exception):
    def __init__(self, status_code: int | None, msg: str) -> None:
        self.status_code = status_code
        super().__init__(msg)


def _llm_stream(messages: list[dict], client) -> Iterator[str]:
    """Stream text tokens from Claude Haiku 4.5. Raises _ApiError on failure."""
    try:
        with client.messages.stream(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            system=SYSTEM_PROMPT,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                yield text
    except Exception as exc:
        code = getattr(exc, "status_code", None)
        raise _ApiError(code, str(exc)) from exc


def _sentence_stream(tokens: Iterator[str]) -> Iterator[str]:
    """Buffer streamed tokens and yield complete sentences (ends with . ? !)."""
    buf = ""
    for tok in tokens:
        buf += tok
        stripped = buf.rstrip()
        if stripped and stripped[-1] in ".?!":
            s = buf.strip()
            if s:
                yield s
            buf = ""
    remainder = buf.strip()
    if remainder:
        yield remainder


# ──────────────────────────── TTS ──────────────────────────────────────────────


def _tts_speak(text: str, sink_node: str) -> float:
    """Synthesize `text` → espeak-ng WAV → sox 8 kHz raw → pw-play to HFP sink.

    Returns a monotonic timestamp approximating when pw-play started consuming
    audio (used as t_tts_first_audio for EERL).
    """
    espeak = subprocess.Popen(
        ESPEAK_ARGS + [text],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    # espeak-ng --stdout emits WAV; sox converts to raw s16le 8 kHz
    sox = subprocess.Popen(
        [
            "sox", "-t", "wav", "-",
            "-r", "8000", "-c", "1", "-e", "signed-integer", "-b", "16", "-t", "raw", "-",
        ],
        stdin=espeak.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    espeak.stdout.close()
    play = subprocess.Popen(
        [
            "pw-play", "--target", sink_node,
            "--rate", str(RATE), "--channels", "1", "--format", "s16", "-",
        ],
        stdin=sox.stdout,
        stderr=subprocess.DEVNULL,
    )
    sox.stdout.close()
    t_first = time.monotonic()   # pw-play is launched and consuming
    play.wait()
    sox.wait()
    espeak.wait()
    return t_first


# ──────────────────────────── terminal output ──────────────────────────────────


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _log_iris(text: str) -> None:
    print(f"\r[{_ts()}]  Iris  »  {text}", flush=True)


def _log_far(text: str) -> None:
    print(f"\r[{_ts()}]  Far   «  {text}", flush=True)


def _status(msg: str) -> None:
    print(f"\r{msg}  ", end="", flush=True)


def _log_eerl(turn: Turn) -> None:
    b = turn.breakdown()
    print(
        f"  EERL: stt={b['stt']*1000:.0f}ms "
        f"llm_ttft={b['llm_ttft']*1000:.0f}ms "
        f"tts_ttfa={b['tts_ttfa']*1000:.0f}ms "
        f"│ total={b['EERL']*1000:.0f}ms",
        flush=True,
    )


# ──────────────────────────── main conversation loop ───────────────────────────


def _iris_loop(cfg: Cfg, source_node: str, sink_node: str) -> SessionStats:
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    stats = SessionStats()
    history: deque[dict] = deque(maxlen=MAX_HISTORY)
    degraded = False

    # Start recording from HFP source
    rec = subprocess.Popen(
        [
            "pw-record",
            "--target", source_node,
            "--rate", str(RATE),
            "--channels", "1",
            "--format", "s16",
            "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )

    try:
        # VAD calibration
        if cfg.no_calibrate:
            print(f"  VAD calibration skipped (threshold: {cfg.vad_threshold:.0f} RMS)")
        else:
            _status("  Calibrating VAD... stay quiet for ~1.5s")
            floor, threshold = _calibrate_vad(rec)
            cfg.vad_threshold = threshold
            print(
                f"\r  Calibrating VAD... done "
                f"(baseline: {floor:.0f} RMS, threshold: {threshold:.0f})",
                flush=True,
            )

        # Disclosure — plays before STT model loads (keeps startup < 2s)
        print("\n  Playing disclosure ...", flush=True)
        _tts_speak(DISCLOSURE, sink_node)
        _log_iris(DISCLOSURE)

        # STT model warm-up (after disclosure so far end hears us promptly)
        print("  Loading STT model (first response may be slower) ...", flush=True)
        _load_whisper(cfg.model_name)

        print(f"\n{'─'*64}", flush=True)

        # VAD state
        speaking = False
        speech_run = 0
        silence_run = 0
        buf = bytearray()

        while True:
            if degraded:
                _status("⚠  DEGRADED — Ctrl-C to exit")
                time.sleep(0.1)
                continue

            frame = rec.stdout.read(FRAME_BYTES)
            if len(frame) < FRAME_BYTES:
                break

            energy = _rms(frame)
            _status(f"🎙 LISTENING  VAD: {energy:.0f} RMS")

            if energy >= cfg.vad_threshold:
                speech_run += 1
                silence_run = 0
                if not speaking and speech_run >= 3:
                    speaking = True
                    buf.clear()
                    _status("🔴 HEARING")
                if speaking:
                    buf.extend(frame)
            else:
                speech_run = 0
                if speaking:
                    buf.extend(frame)
                    silence_run += 1
                    if silence_run >= cfg.hangover_frames:
                        _status("⏳ PROCESSING")
                        turn = Turn(t_endpoint=time.monotonic())
                        speaking = False
                        silence_run = 0
                        audio_snapshot = bytes(buf)
                        buf.clear()

                        # STT
                        transcript = _transcribe(audio_snapshot, cfg)
                        turn.t_stt_done = time.monotonic()

                        # Empty STT — re-enter VAD loop silently
                        # Guard on non-whitespace char count (≤2), not word count.
                        non_ws_chars = len(transcript.strip().replace(" ", ""))
                        if non_ws_chars <= 2:
                            stats.empty_stt_count += 1
                            print(
                                f"\r  [debug] empty STT ({non_ws_chars} chars): "
                                f"{repr(transcript)}",
                                flush=True,
                            )
                            continue

                        _log_far(transcript)

                        # Handoff detection on far-end transcript (skip LLM entirely)
                        if any(sig in transcript.lower() for sig in HANDOFF_SIGNALS):
                            _status("🔊 IRIS SPEAKING")
                            _tts_speak(HANDOFF_LINE, sink_node)
                            _log_iris(HANDOFF_LINE)
                            print(
                                "\n  ⚠  DEGRADED: caller requested handoff. "
                                "Ctrl-C to exit.",
                                flush=True,
                            )
                            degraded = True
                            stats.degraded = True
                            continue

                        # LLM (streaming) with retry: 5xx → 1 retry at 0.5s; 4xx → no retry
                        messages = list(history) + [
                            {"role": "user", "content": transcript}
                        ]
                        full_reply_parts: list[str] = []
                        first_sent = True
                        api_ok = True

                        for attempt in range(2):
                            try:
                                token_gen = _llm_stream(messages, client)
                                _status("⏳ PROCESSING")
                                for sentence in _sentence_stream(token_gen):
                                    full_reply_parts.append(sentence)
                                    _status("🔊 IRIS SPEAKING")
                                    if first_sent:
                                        turn.t_llm_first = time.monotonic()
                                    t_first = _tts_speak(sentence, sink_node)
                                    if first_sent:
                                        turn.t_tts_first_audio = t_first
                                        first_sent = False
                                break  # success
                            except _ApiError as exc:
                                stats.api_errors += 1
                                code = exc.status_code
                                if code is not None and 400 <= code < 500:
                                    api_ok = False
                                    break  # no retry for 4xx (auth / rate limit)
                                if attempt == 0:
                                    full_reply_parts.clear()
                                    first_sent = True
                                    time.sleep(0.5)
                                else:
                                    api_ok = False

                        if not api_ok:
                            _status("🔊 IRIS SPEAKING")
                            _tts_speak(RECOVERY_LINE, sink_node)
                            _log_iris(RECOVERY_LINE)
                            print(
                                "\n  ⚠  DEGRADED: API error. Ctrl-C to exit.",
                                flush=True,
                            )
                            degraded = True
                            stats.degraded = True
                            continue

                        full_reply = " ".join(full_reply_parts)
                        if full_reply:
                            _log_iris(full_reply)
                            # Append successful turn to conversation history
                            history.append({"role": "user", "content": transcript})
                            history.append({"role": "assistant", "content": full_reply})

                        # Post-reply handoff detection (LLM may have used handoff language)
                        if any(sig in full_reply.lower() for sig in HANDOFF_SIGNALS):
                            print(
                                "  ⚠  DEGRADED: handoff signaled in reply. "
                                "Ctrl-C to exit.",
                                flush=True,
                            )
                            degraded = True
                            stats.degraded = True

                        if not first_sent:
                            stats.turns.append(turn)
                            _log_eerl(turn)

    except KeyboardInterrupt:
        print("\n  Exiting cleanly (Ctrl-C).", flush=True)
    finally:
        rec.terminate()
        try:
            rec.wait(timeout=2)
        except subprocess.TimeoutExpired:
            rec.kill()

    return stats


# ──────────────────────────── session summary ──────────────────────────────────


def _pct(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    k = max(0, min(len(s) - 1, int(round((p / 100) * (len(s) - 1)))))
    return s[k]


def _print_summary(stats: SessionStats) -> None:
    turns = stats.turns
    print(f"\n{'═'*64}")
    print(f"  Session summary — {len(turns)} conversation turn(s)")
    if turns:
        eerls = [t.eerl * 1000 for t in turns]
        avg = sum(eerls) / len(eerls)
        print(
            f"  EERL  avg={avg:.0f}ms  min={min(eerls):.0f}ms  "
            f"max={max(eerls):.0f}ms  p90={_pct(eerls, 90):.0f}ms"
        )
    print(f"  Empty STT count:  {stats.empty_stt_count}")
    print(f"  API errors:       {stats.api_errors}")
    if stats.degraded:
        print("  Final state:      DEGRADED (handoff or API failure)")
    print(f"{'═'*64}", flush=True)


# ──────────────────────────── CLI ──────────────────────────────────────────────


def main() -> None:
    p = argparse.ArgumentParser(
        description="Iris — AI voice agent on an active HFP call",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--device-mac",
        required=True,
        help="Bluetooth MAC address of the paired iPhone (e.g. AA:BB:CC:DD:EE:FF)",
    )
    p.add_argument(
        "--vad-threshold",
        type=float,
        default=500.0,
        help="VAD energy threshold in RMS; auto-calibrated unless --no-calibrate (default: 500)",
    )
    p.add_argument(
        "--hangover-ms",
        type=int,
        default=500,
        help="Silence duration in ms to end an utterance (default: 500)",
    )
    p.add_argument(
        "--model",
        dest="model_name",
        default="tiny.en",
        help="faster-whisper model name: tiny.en, base.en, small.en (default: tiny.en)",
    )
    p.add_argument(
        "--no-calibrate",
        action="store_true",
        help="Skip VAD auto-calibration; use --vad-threshold directly",
    )
    args = p.parse_args()

    cfg = Cfg(
        device_mac=args.device_mac,
        vad_threshold=args.vad_threshold,
        hangover_ms=args.hangover_ms,
        model_name=args.model_name,
        no_calibrate=args.no_calibrate,
    )

    source_node, sink_node = _check_prereqs(cfg)
    stats = _iris_loop(cfg, source_node, sink_node)
    _print_summary(stats)


if __name__ == "__main__":
    main()
