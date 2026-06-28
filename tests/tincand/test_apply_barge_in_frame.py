"""Tests: tincand/call_audio.py — apply_barge_in_frame actuator.
Bead: tincan-c8ttg

Coverage:
  apply_barge_in_frame:
  - False→True transition calls _pw_unlink for every pair in ctx.tts_links.
  - True→False transition calls _pw_link for every pair in ctx.tts_links.
  - No pw calls when state stays False (silence frames, controller not muted).
  - No pw calls when state stays True (speech frames, controller already muted).
  - Returns True when TTS is muted after the frame.
  - Returns False when TTS is not muted after the frame.
  - Empty tts_links: no crash and no pw calls even on a False→True transition.

_pw_link/_pw_unlink are patched at the module level; no PipeWire calls made.
"""
from __future__ import annotations

from unittest.mock import call, patch

from tincand.call_audio import BargeInController, UplinkMixerCtx, apply_barge_in_frame

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(tts_links: list[tuple[str, str]] | None = None) -> UplinkMixerCtx:
    ctx = UplinkMixerCtx(module_id=1, mixer_sink_name="tincan_iris_uplink_mix")
    if tts_links:
        ctx.tts_links.extend(tts_links)
    return ctx


def _muted_controller(hangover_frames: int = 10) -> BargeInController:
    ctrl = BargeInController(threshold_rms=500.0, hangover_frames=hangover_frames)
    ctrl.update(1000.0)
    return ctrl


_TTS_PAIRS = [
    ("iris:capture_FL", "mix:playback_FL"),
    ("iris:capture_FR", "mix:playback_FR"),
]


# ---------------------------------------------------------------------------
# §1 apply_barge_in_frame
# ---------------------------------------------------------------------------

class TestApplyBargeInFrame:
    """apply_barge_in_frame — actuates TTS pw-links on VAD state transitions."""

    def test_false_to_true_calls_pw_unlink_for_each_pair(self):
        ctx = _make_ctx(_TTS_PAIRS)
        ctrl = BargeInController(threshold_rms=500.0)

        with patch("tincand.call_audio._pw_unlink") as mock_unlink, \
                patch("tincand.call_audio._pw_link") as mock_link:
            apply_barge_in_frame(ctx, ctrl, mic_rms=1000.0)

        mock_unlink.assert_has_calls(
            [call("iris:capture_FL", "mix:playback_FL"),
             call("iris:capture_FR", "mix:playback_FR")],
        )
        assert mock_unlink.call_count == len(_TTS_PAIRS)
        mock_link.assert_not_called()

    def test_true_to_false_calls_pw_link_for_each_pair(self):
        ctx = _make_ctx(_TTS_PAIRS)
        ctrl = _muted_controller(hangover_frames=1)

        with patch("tincand.call_audio._pw_link") as mock_link, \
                patch("tincand.call_audio._pw_unlink") as mock_unlink:
            apply_barge_in_frame(ctx, ctrl, mic_rms=0.0)

        mock_link.assert_has_calls(
            [call("iris:capture_FL", "mix:playback_FL"),
             call("iris:capture_FR", "mix:playback_FR")],
        )
        assert mock_link.call_count == len(_TTS_PAIRS)
        mock_unlink.assert_not_called()

    def test_no_pw_calls_silence_stays_unmuted(self):
        ctx = _make_ctx(_TTS_PAIRS)
        ctrl = BargeInController(threshold_rms=500.0)

        with patch("tincand.call_audio._pw_unlink") as mock_unlink, \
                patch("tincand.call_audio._pw_link") as mock_link:
            apply_barge_in_frame(ctx, ctrl, mic_rms=0.0)

        mock_unlink.assert_not_called()
        mock_link.assert_not_called()

    def test_no_pw_calls_speech_stays_muted(self):
        ctx = _make_ctx(_TTS_PAIRS)
        ctrl = _muted_controller()

        with patch("tincand.call_audio._pw_unlink") as mock_unlink, \
                patch("tincand.call_audio._pw_link") as mock_link:
            apply_barge_in_frame(ctx, ctrl, mic_rms=1000.0)

        mock_unlink.assert_not_called()
        mock_link.assert_not_called()

    def test_returns_true_when_muted(self):
        ctx = _make_ctx()
        ctrl = BargeInController(threshold_rms=500.0)

        with patch("tincand.call_audio._pw_unlink"), patch("tincand.call_audio._pw_link"):
            result = apply_barge_in_frame(ctx, ctrl, mic_rms=1000.0)

        assert result is True

    def test_returns_false_when_not_muted(self):
        ctx = _make_ctx()
        ctrl = BargeInController(threshold_rms=500.0)

        result = apply_barge_in_frame(ctx, ctrl, mic_rms=0.0)

        assert result is False

    def test_empty_tts_links_no_crash_on_false_to_true_transition(self):
        ctx = _make_ctx([])
        ctrl = BargeInController(threshold_rms=500.0)

        with patch("tincand.call_audio._pw_unlink") as mock_unlink, \
                patch("tincand.call_audio._pw_link") as mock_link:
            result = apply_barge_in_frame(ctx, ctrl, mic_rms=1000.0)

        assert result is True
        mock_unlink.assert_not_called()
        mock_link.assert_not_called()
