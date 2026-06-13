"""Tests: Iris spike unit tests — handoff detection, empty-STT, truncation, API retry, session summary.
Bead: tincan-bbpih.1

Coverage:
  §1 HANDOFF_SIGNALS detection — 4 tests
     - Transcript containing "get jim" → HANDOFF_SIGNALS matches (DEGRADED mode triggered in loop)
     - Transcript containing "don't want to talk to an ai" → matches
     - Normal transcript → no match
     - Case-insensitive matching ("Get Jim" matches)

  §2 Empty STT guard — 3 tests
     - Transcript "" → no LLM call, stats.empty_stt_count incremented
     - Transcript "  ok  " (≤2 non-whitespace words) → no LLM call, count incremented
     - Transcript "hello" → LLM call IS made, count NOT incremented
     NOTE: current impl uses word count (len(words) ≤ 2); spec says ≤2 non-whitespace
     chars. "hello" is 1 word ≤ 2, so it is skipped by the current guard. The third
     test documents this bug: it will FAIL until the guard uses char-count ≤ 2.

  §3 STT hallucination guard (>200 words) — 3 tests
     - 300-word whisper output → _transcribe returns 200 words + " […]"
     - 199-word whisper output → returned unchanged
     - 200-word whisper output → returned unchanged

  §4 API retry logic (mock anthropic client, 5xx/4xx) — 4 tests
     - 5xx on first LLM call → 1 retry fires; second call succeeds → not degraded
     - 5xx on both calls → recovery dialogue triggered, stats.degraded == True
     - 4xx on first call → no retry, stats.degraded == True, call_count == 1
     - _llm_stream wraps any exception as _ApiError with the original status_code

  §5 Session summary calculation — 3 tests
     - 3 turns with EERL [0.9, 1.1, 1.3] s → avg=1100ms, min=900ms, max=1300ms in output
     - 0 turns → "0 conversation turn(s)" reported, no EERL line
     - empty_stt_count field printed correctly

No real Bluetooth, PipeWire, or Anthropic API calls in any test.
All tests deterministic — no real timing, monkeypatched sleep, injected audio frames.
"""
from __future__ import annotations

import struct
import sys
import time
from unittest.mock import MagicMock

import pytest

import iris_spike as iris  # conftest.py adds spikes/ to sys.path

# ─────────────────────────── audio frame helpers ──────────────────────────────

_FRAME_SAMPLES = iris.FRAME_SAMPLES   # 160  (8 kHz × 20 ms)
_FRAME_BYTES = iris.FRAME_BYTES       # 320  (s16le)


def _high_frame(rms: int = 2000) -> bytes:
    """20 ms frame with energy well above the default VAD threshold (500 RMS)."""
    return struct.pack(f"<{_FRAME_SAMPLES}h", *([rms] * _FRAME_SAMPLES))


def _zero_frame() -> bytes:
    return b"\x00" * _FRAME_BYTES


def _make_rec_mock(frames: list[bytes]) -> MagicMock:
    """Mock pw-record Popen: stdout.read returns frames in sequence, then b''."""
    rec = MagicMock()
    it = iter(frames)
    rec.stdout.read = lambda n: next(it, b"")
    return rec


def _utterance_frames(cfg: iris.Cfg) -> list[bytes]:
    """Minimal frame sequence that triggers one VAD utterance then EOF.

    5 high-energy frames: speech_run reaches 3 → speaking=True, 2 more accumulate.
    (hangover_frames + 1) zero frames: silence_run exceeds the hangover → processing.
    b"" EOF: exits the read loop.
    """
    return [_high_frame()] * 5 + [_zero_frame()] * (cfg.hangover_frames + 1) + [b""]


def _make_mock_anthropic_module(mock_client: MagicMock) -> MagicMock:
    """Return a fake `anthropic` module whose Anthropic() returns mock_client."""
    mock_anthropic = MagicMock()
    mock_anthropic.Anthropic.return_value = mock_client
    return mock_anthropic


def _run_loop(
    monkeypatch,
    transcript: str,
    mock_client: MagicMock,
    cfg: iris.Cfg | None = None,
) -> iris.SessionStats:
    """Drive _iris_loop with one synthetic utterance and a controlled transcript.

    Patches out all hardware I/O:
      - subprocess.Popen → mock pw-record yielding synthetic frames
      - _transcribe → returns `transcript` immediately
      - _tts_speak → no-op returning 0.0
      - _load_whisper → mock (warm-up call in _iris_loop)
      - time.sleep → no-op (skip 0.5 s retry delay)
      - anthropic module → mock returning mock_client
      - _status → raises KeyboardInterrupt when degraded text is detected,
        so the degraded spin-loop exits cleanly instead of running forever
    """
    if cfg is None:
        cfg = iris.Cfg(no_calibrate=True)

    rec_mock = _make_rec_mock(_utterance_frames(cfg))
    monkeypatch.setattr(iris.subprocess, "Popen", lambda *a, **kw: rec_mock)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(iris, "_transcribe", lambda *a: transcript)
    monkeypatch.setattr(iris, "_tts_speak", lambda text, sink: 0.0)
    monkeypatch.setattr(iris, "_load_whisper", lambda name: MagicMock())
    monkeypatch.setattr(iris.time, "sleep", lambda s: None)

    def _mock_status(msg: str) -> None:
        if "DEGRADED" in msg:
            raise KeyboardInterrupt  # exit the degraded spin-loop

    monkeypatch.setattr(iris, "_status", _mock_status)

    # anthropic is not installed in the test venv; inject via sys.modules
    monkeypatch.setitem(sys.modules, "anthropic", _make_mock_anthropic_module(mock_client))

    return iris._iris_loop(cfg, "mock_source", "mock_sink")


def _normal_client() -> MagicMock:
    """Mock anthropic client that streams "Hello!" successfully."""
    client = MagicMock()
    stream = MagicMock()
    stream.text_stream = iter(["Hello!"])
    client.messages.stream.return_value.__enter__.return_value = stream
    client.messages.stream.return_value.__exit__.return_value = False
    return client


# ─────────────────────────── §1 HANDOFF_SIGNALS detection ────────────────────

class TestHandoffSignals:
    """HANDOFF_SIGNALS constant + matching predicate."""

    def _matches(self, transcript: str) -> bool:
        return any(sig in transcript.lower() for sig in iris.HANDOFF_SIGNALS)

    def test_get_jim_triggers_handoff(self):
        assert self._matches("Could you get jim please?")

    def test_dont_want_ai_triggers_handoff(self):
        assert self._matches("I don't want to talk to an ai right now")

    def test_normal_transcript_no_handoff(self):
        assert not self._matches("What time does the meeting start tomorrow?")

    def test_handoff_matching_is_case_insensitive(self):
        assert self._matches("Get Jim now please")


# ─────────────────────────── §2 Empty STT guard ──────────────────────────────

class TestEmptySTTGuard:
    """Empty-STT guard increments empty_stt_count and skips the LLM call."""

    def test_empty_string_skips_llm(self, monkeypatch):
        client = MagicMock()
        stats = _run_loop(monkeypatch, "", client)
        assert stats.empty_stt_count == 1
        client.messages.stream.assert_not_called()

    def test_two_char_word_ok_skips_llm(self, monkeypatch):
        client = MagicMock()
        stats = _run_loop(monkeypatch, "  ok  ", client)
        assert stats.empty_stt_count == 1
        client.messages.stream.assert_not_called()

    def test_hello_makes_llm_call(self, monkeypatch):
        # Spec: "hello" (5 non-whitespace chars) → LLM call IS made, count unchanged.
        # BUG: current guard uses word count (len(words) ≤ 2); "hello" is 1 word ≤ 2
        # so the current code also skips it. This test documents the spec and will
        # FAIL until the guard is corrected to use non-whitespace char count ≤ 2.
        client = _normal_client()
        stats = _run_loop(monkeypatch, "hello", client)
        assert stats.empty_stt_count == 0
        client.messages.stream.assert_called_once()


# ─────────────────────────── §3 STT hallucination guard ──────────────────────

class TestSTTTruncation:
    """_transcribe() truncates transcripts whose word count exceeds MAX_STT_WORDS."""

    def _transcribe_mock(self, monkeypatch, whisper_text: str) -> str:
        monkeypatch.setitem(sys.modules, "numpy", MagicMock())

        cfg = iris.Cfg()

        mock_run = MagicMock()
        mock_run.return_value.stdout = b"\x00\x00\x00\x00"

        mock_model = MagicMock()
        seg = MagicMock()
        seg.text = whisper_text
        mock_model.transcribe.return_value = ([seg], None)

        monkeypatch.setattr(iris.subprocess, "run", mock_run)
        monkeypatch.setattr(iris, "_load_whisper", lambda name: mock_model)

        return iris._transcribe(b"\x00\x02", cfg)

    def test_300_word_transcript_truncated_to_200(self, monkeypatch):
        words_300 = " ".join(f"word{i}" for i in range(300))
        result = self._transcribe_mock(monkeypatch, words_300)
        result_words = result.split()
        assert len(result_words) == 201  # 200 words + "[…]"
        assert result.endswith("[…]")

    def test_199_word_transcript_unchanged(self, monkeypatch):
        words_199 = " ".join(f"word{i}" for i in range(199))
        result = self._transcribe_mock(monkeypatch, words_199)
        assert result == words_199

    def test_200_word_transcript_unchanged(self, monkeypatch):
        words_200 = " ".join(f"word{i}" for i in range(200))
        result = self._transcribe_mock(monkeypatch, words_200)
        assert result == words_200


# ─────────────────────────── §4 API retry logic ──────────────────────────────

class TestAPIRetry:
    """LLM retry behavior: 5xx → 1 retry; 4xx → no retry; failure → DEGRADED."""

    def _make_5xx_then_success_client(self) -> MagicMock:
        """Client that raises 5xx on the first stream call, succeeds on the second."""
        client = MagicMock()
        exc = Exception("Service unavailable")
        exc.status_code = 503

        success_stream = MagicMock()
        success_stream.text_stream = iter(["Hello!"])

        # side_effect list: first call raises exc, second call returns success_stream
        client.messages.stream.return_value.__enter__.side_effect = [exc, success_stream]
        client.messages.stream.return_value.__exit__.return_value = False
        return client

    def _make_both_5xx_client(self) -> MagicMock:
        """Client that raises 5xx on every stream call."""
        client = MagicMock()
        exc1 = Exception("Service unavailable")
        exc1.status_code = 503
        exc2 = Exception("Service still unavailable")
        exc2.status_code = 503
        client.messages.stream.return_value.__enter__.side_effect = [exc1, exc2]
        client.messages.stream.return_value.__exit__.return_value = False
        return client

    def _make_4xx_client(self) -> MagicMock:
        """Client that raises 4xx on the first stream call."""
        client = MagicMock()
        exc = Exception("Rate limit exceeded")
        exc.status_code = 429
        client.messages.stream.return_value.__enter__.side_effect = exc
        client.messages.stream.return_value.__exit__.return_value = False
        return client

    # transcript must have > 2 words to pass the empty-STT guard and reach the LLM
    _REAL_TRANSCRIPT = "how are you doing today sir"

    def test_5xx_first_then_success_not_degraded(self, monkeypatch):
        client = self._make_5xx_then_success_client()
        stats = _run_loop(monkeypatch, self._REAL_TRANSCRIPT, client)
        assert not stats.degraded
        assert stats.api_errors == 1
        assert client.messages.stream.call_count == 2

    def test_5xx_on_both_calls_enters_degraded(self, monkeypatch):
        client = self._make_both_5xx_client()
        stats = _run_loop(monkeypatch, self._REAL_TRANSCRIPT, client)
        assert stats.degraded
        assert stats.api_errors == 2

    def test_4xx_no_retry_enters_degraded(self, monkeypatch):
        client = self._make_4xx_client()
        stats = _run_loop(monkeypatch, self._REAL_TRANSCRIPT, client)
        assert stats.degraded
        assert stats.api_errors == 1
        assert client.messages.stream.call_count == 1

    def test_llm_stream_wraps_exception_as_api_error(self):
        exc = Exception("Internal server error")
        exc.status_code = 500
        client = MagicMock()
        client.messages.stream.return_value.__enter__.side_effect = exc
        client.messages.stream.return_value.__exit__.return_value = False

        with pytest.raises(iris._ApiError) as exc_info:
            list(iris._llm_stream([{"role": "user", "content": "hi"}], client))

        assert exc_info.value.status_code == 500


# ─────────────────────────── §5 Session summary ──────────────────────────────

class TestSessionSummary:
    """Turn.eerl property, SessionStats, and _print_summary output."""

    def test_three_turns_eerl_avg_min_max(self, capsys):
        stats = iris.SessionStats()
        # Three turns: EERL = t_tts_first_audio - t_endpoint = 0.9, 1.1, 1.3 s
        for eerl_s in [0.9, 1.1, 1.3]:
            t = iris.Turn(
                t_endpoint=0.0,
                t_stt_done=0.3,
                t_llm_first=0.7,
                t_tts_first_audio=eerl_s,
            )
            stats.turns.append(t)

        iris._print_summary(stats)
        out = capsys.readouterr().out

        assert "3 conversation turn(s)" in out
        assert "avg=1100ms" in out
        assert "min=900ms" in out
        assert "max=1300ms" in out

    def test_zero_turns_summary_no_eerl_line(self, capsys):
        stats = iris.SessionStats()
        iris._print_summary(stats)
        out = capsys.readouterr().out

        assert "0 conversation turn(s)" in out
        assert "EERL" not in out

    def test_empty_stt_count_reported_in_summary(self, capsys):
        stats = iris.SessionStats()
        stats.empty_stt_count = 5
        iris._print_summary(stats)
        out = capsys.readouterr().out

        assert "Empty STT count:  5" in out
