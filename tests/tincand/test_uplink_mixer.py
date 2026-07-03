"""Tests: tincand/call_audio.py — uplink TTS mixer.
Bead: tincan-rfb86

Coverage:
  UplinkMixerCtx dataclass:
  - Has fields: module_id, mixer_sink_name, mic_links, tts_links, out_links

  setup_uplink_mixer:
  - Returns None when no bluez_output ports found for MAC
  - Returns None when no mic capture ports found
  - Returns None when pactl load-module fails (rc != 0)
  - Returns UplinkMixerCtx on success
  - Calls pactl to create a null-sink node
  - Creates mic → null-sink links (mic_links populated)
  - Creates null-sink monitor → bluez_output links (out_links populated)
  - With tts_source_name: also creates tts → null-sink links (tts_links populated)
  - Without tts_source_name: tts_links is empty

  connect_tts_to_uplink:
  - Creates pw-link connections from tts source to mixer sink input
  - Returns True when all ports found and linked
  - Returns False when tts source port not found
  - Appends created links to mixer_ctx.tts_links

  teardown_uplink_mixer:
  - Calls pw-link -d for every link in mic_links, tts_links, out_links
  - Calls pactl unload-module <module_id>

  BargeInController:
  - update() returns False initially (TTS not muted)
  - update(rms > threshold) returns True (operator speaking — mute TTS)
  - update(rms < threshold) after speaking returns True during hangover
  - After hangover expires: update(rms < threshold) returns False (TTS restored)
  - is_muted() reflects current state
  - Can be reset: re-entering speech while in hangover restarts the hangover

All subprocess calls mocked — no real PipeWire or pactl required.
"""
from __future__ import annotations

import subprocess

import pytest

from tincand.call_audio import (
    BargeInController,
    UplinkMixerCtx,
    connect_tts_to_uplink,
    setup_uplink_mixer,
    teardown_uplink_mixer,
)

# ---------------------------------------------------------------------------
# Fake port data
# ---------------------------------------------------------------------------

_MAC = "ab_cd_ef_12_34_56"

_FAKE_OUTPUTS = "\n".join([
    # mic (default capture source)
    "alsa_input.pci.0.analog-stereo:capture_FL",
    "alsa_input.pci.0.analog-stereo:capture_FR",
    "alsa_input.pci.0.analog-stereo:capture_MONO",
    # bluez device input (phone → speaker)
    f"bluez_input.{_MAC}:capture_FL",
    f"bluez_input.{_MAC}:capture_MONO",
    # null-sink monitor output (after mixer creation)
    "tincan_iris_uplink_mix.monitor:capture_MONO",
    # fake TTS source
    "tincan_iris_tts:capture_MONO",
])

_FAKE_INPUTS = "\n".join([
    # default sink (speaker)
    "alsa_output.pci.0.analog-stereo:playback_FL",
    "alsa_output.pci.0.analog-stereo:playback_FR",
    "alsa_output.pci.0.analog-stereo:playback_MONO",
    # bluez device output (mic → phone uplink)
    f"bluez_output.{_MAC}:playback_MONO",
    # null-sink inputs (after mixer creation)
    "tincan_iris_uplink_mix:playback_MONO",
])

_NO_BLUEZ_OUTPUTS = "\n".join([
    "alsa_input.pci.0.analog-stereo:capture_MONO",
])
_NO_BLUEZ_INPUTS = "\n".join([
    "alsa_output.pci.0.analog-stereo:playback_MONO",
])
_NO_MIC_OUTPUTS = "\n".join([
    f"bluez_input.{_MAC}:capture_MONO",
])


def _cp(stdout="", returncode=0):
    """Make a fake subprocess.CompletedProcess."""
    r = subprocess.CompletedProcess(args=[], returncode=returncode)
    r.stdout = stdout
    r.stderr = ""
    return r


# ---------------------------------------------------------------------------
# §1 UplinkMixerCtx dataclass
# ---------------------------------------------------------------------------

class TestUplinkMixerCtx:
    def test_has_required_fields(self):
        ctx = UplinkMixerCtx(
            module_id=42,
            mixer_sink_name="tincan_iris_uplink_mix",
            mic_links=[],
            tts_links=[],
            out_links=[],
        )
        assert ctx.module_id == 42
        assert ctx.mixer_sink_name == "tincan_iris_uplink_mix"
        assert ctx.mic_links == []
        assert ctx.tts_links == []
        assert ctx.out_links == []

    def test_module_id_stored_correctly(self):
        ctx = UplinkMixerCtx(
            module_id=999,
            mixer_sink_name="mix",
            mic_links=[("src", "dst")],
            tts_links=[],
            out_links=[],
        )
        assert ctx.module_id == 999

    def test_links_are_independent(self):
        mic = [("m:capture_MONO", "mix:playback_MONO")]
        out = [("mix.monitor:capture_MONO", "bt:playback_MONO")]
        ctx = UplinkMixerCtx(
            module_id=1,
            mixer_sink_name="mix",
            mic_links=mic,
            tts_links=[],
            out_links=out,
        )
        assert ctx.mic_links is mic
        assert ctx.out_links is out


# ---------------------------------------------------------------------------
# Shared subprocess fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_subproc(monkeypatch):
    """Patch tincand.call_audio.subprocess.run; returns a call recorder."""
    calls_made: list[tuple] = []
    pactl_module_id = 17

    def _run(cmd, **kw):
        calls_made.append(cmd)
        if cmd[0] == "pw-link" and "-o" in cmd:
            return _cp(_FAKE_OUTPUTS)
        if cmd[0] == "pw-link" and "-i" in cmd:
            return _cp(_FAKE_INPUTS)
        if cmd[0] == "pw-link" and "-d" not in cmd and len(cmd) == 3:
            return _cp(returncode=0)
        if cmd[0] == "pw-link" and "-d" in cmd:
            return _cp(returncode=0)
        if cmd[0] == "pactl" and "load-module" in cmd:
            return _cp(stdout=str(pactl_module_id), returncode=0)
        if cmd[0] == "pactl" and "unload-module" in cmd:
            return _cp(returncode=0)
        return _cp(returncode=0)

    import tincand.call_audio as ca
    monkeypatch.setattr(ca, "subprocess", type("FakeSubproc", (), {
        "run": staticmethod(_run),
        "CompletedProcess": subprocess.CompletedProcess,
    })())
    return calls_made


@pytest.fixture
def no_bluez_subproc(monkeypatch):
    """Subprocess returning ports with NO bluez_output for the given MAC."""
    def _run(cmd, **kw):
        if cmd[0] == "pw-link" and "-o" in cmd:
            return _cp(_NO_BLUEZ_OUTPUTS)
        if cmd[0] == "pw-link" and "-i" in cmd:
            return _cp(_NO_BLUEZ_INPUTS)
        if cmd[0] == "pactl":
            return _cp(stdout="17", returncode=0)
        return _cp(returncode=0)

    import tincand.call_audio as ca
    monkeypatch.setattr(ca, "subprocess", type("FakeSubproc", (), {
        "run": staticmethod(_run),
        "CompletedProcess": subprocess.CompletedProcess,
    })())


@pytest.fixture
def no_mic_subproc(monkeypatch):
    """Subprocess returning ports with NO mic capture for the given MAC."""
    def _run(cmd, **kw):
        if cmd[0] == "pw-link" and "-o" in cmd:
            return _cp(_NO_MIC_OUTPUTS)
        if cmd[0] == "pw-link" and "-i" in cmd:
            return _cp(_FAKE_INPUTS)
        if cmd[0] == "pactl":
            return _cp(stdout="17", returncode=0)
        return _cp(returncode=0)

    import tincand.call_audio as ca
    monkeypatch.setattr(ca, "subprocess", type("FakeSubproc", (), {
        "run": staticmethod(_run),
        "CompletedProcess": subprocess.CompletedProcess,
    })())


@pytest.fixture
def pactl_fail_subproc(monkeypatch):
    """Subprocess where pactl load-module fails."""
    def _run(cmd, **kw):
        if cmd[0] == "pw-link" and "-o" in cmd:
            return _cp(_FAKE_OUTPUTS)
        if cmd[0] == "pw-link" and "-i" in cmd:
            return _cp(_FAKE_INPUTS)
        if cmd[0] == "pactl" and "load-module" in cmd:
            return _cp(stdout="", returncode=1)
        return _cp(returncode=0)

    import tincand.call_audio as ca
    monkeypatch.setattr(ca, "subprocess", type("FakeSubproc", (), {
        "run": staticmethod(_run),
        "CompletedProcess": subprocess.CompletedProcess,
    })())


# ---------------------------------------------------------------------------
# §2 setup_uplink_mixer
# ---------------------------------------------------------------------------

class TestSetupUplinkMixer:
    def test_returns_none_when_no_bluez_output_ports(self, no_bluez_subproc):
        assert setup_uplink_mixer(_MAC) is None

    def test_returns_none_when_no_mic_capture_ports(self, no_mic_subproc):
        assert setup_uplink_mixer(_MAC) is None

    def test_returns_none_when_pactl_fails(self, pactl_fail_subproc):
        assert setup_uplink_mixer(_MAC) is None

    def test_returns_none_on_empty_mac_without_loading_module(self, mock_subproc):
        assert setup_uplink_mixer("") is None
        pactl_loads = [
            c for c in mock_subproc
            if c and c[0] == "pactl" and "load-module" in c
        ]
        assert not pactl_loads, "must not load null-sink on empty MAC"

    def test_returns_uplink_mixer_ctx_on_success(self, mock_subproc):
        ctx = setup_uplink_mixer(_MAC)
        assert isinstance(ctx, UplinkMixerCtx)

    def test_pactl_load_module_called(self, mock_subproc):
        setup_uplink_mixer(_MAC)
        pactl_calls = [c for c in mock_subproc if c and c[0] == "pactl"]
        assert any("load-module" in " ".join(c) for c in pactl_calls), (
            "expected pactl load-module call to create null-sink"
        )

    def test_pactl_null_sink_module_name(self, mock_subproc):
        setup_uplink_mixer(_MAC)
        pactl_calls = [c for c in mock_subproc if c and c[0] == "pactl"]
        load_calls = [c for c in pactl_calls if "load-module" in c]
        assert any("module-null-sink" in " ".join(c) for c in load_calls)

    def test_ctx_module_id_from_pactl_output(self, mock_subproc):
        ctx = setup_uplink_mixer(_MAC)
        assert ctx is not None
        assert ctx.module_id == 17

    def test_mic_links_populated(self, mock_subproc):
        ctx = setup_uplink_mixer(_MAC)
        assert ctx is not None
        assert len(ctx.mic_links) >= 1
        # mic links: source is a non-bluez capture port, dest is the mixer input
        for src, dst in ctx.mic_links:
            assert "capture" in src
            assert "bluez" not in src.lower()
            assert ctx.mixer_sink_name in dst

    def test_out_links_to_bluez_output(self, mock_subproc):
        ctx = setup_uplink_mixer(_MAC)
        assert ctx is not None
        assert len(ctx.out_links) >= 1
        # out links: source is the mixer monitor, dest is bluez_output
        for src, dst in ctx.out_links:
            assert ctx.mixer_sink_name in src or "monitor" in src
            assert f"bluez_output.{_MAC}" in dst

    def test_tts_links_empty_without_tts_source(self, mock_subproc):
        ctx = setup_uplink_mixer(_MAC)
        assert ctx is not None
        assert ctx.tts_links == []

    def test_tts_links_populated_with_tts_source_name(self, mock_subproc):
        ctx = setup_uplink_mixer(_MAC, tts_source_name="tincan_iris_tts")
        assert ctx is not None
        assert len(ctx.tts_links) >= 1
        for src, dst in ctx.tts_links:
            assert "tincan_iris_tts" in src
            assert ctx.mixer_sink_name in dst

    def test_mixer_sink_name_set(self, mock_subproc):
        ctx = setup_uplink_mixer(_MAC)
        assert ctx is not None
        assert ctx.mixer_sink_name  # non-empty string


# ---------------------------------------------------------------------------
# §3 connect_tts_to_uplink
# ---------------------------------------------------------------------------

class TestConnectTtsToUplink:
    def test_returns_true_when_tts_port_found(self, mock_subproc):
        ctx = setup_uplink_mixer(_MAC)
        assert ctx is not None
        ok = connect_tts_to_uplink(ctx, "tincan_iris_tts")
        assert ok is True

    def test_appends_to_tts_links(self, mock_subproc):
        ctx = setup_uplink_mixer(_MAC)
        assert ctx is not None
        initial_count = len(ctx.tts_links)
        connect_tts_to_uplink(ctx, "tincan_iris_tts")
        assert len(ctx.tts_links) > initial_count

    def test_returns_false_when_tts_port_not_found(self, mock_subproc):
        ctx = setup_uplink_mixer(_MAC)
        assert ctx is not None
        ok = connect_tts_to_uplink(ctx, "nonexistent_tts_source")
        assert ok is False

    def test_tts_link_src_is_tts_port(self, mock_subproc):
        ctx = setup_uplink_mixer(_MAC)
        assert ctx is not None
        ctx.tts_links.clear()
        connect_tts_to_uplink(ctx, "tincan_iris_tts")
        for src, dst in ctx.tts_links:
            assert "tincan_iris_tts" in src
            assert ctx.mixer_sink_name in dst


# ---------------------------------------------------------------------------
# §4 teardown_uplink_mixer
# ---------------------------------------------------------------------------

class TestTeardownUplinkMixer:
    def test_disconnects_all_mic_links(self, mock_subproc):
        ctx = setup_uplink_mixer(_MAC)
        assert ctx is not None
        teardown_uplink_mixer(ctx)
        unlink_calls = [c for c in mock_subproc if c and c[0] == "pw-link" and "-d" in c]
        mic_unlinked = [c for c in unlink_calls if any(p in " ".join(c) for p, _ in ctx.mic_links)]
        assert len(mic_unlinked) >= len(ctx.mic_links)

    def test_disconnects_all_out_links(self, mock_subproc):
        ctx = setup_uplink_mixer(_MAC)
        assert ctx is not None
        teardown_uplink_mixer(ctx)
        unlink_calls = [c for c in mock_subproc if c and c[0] == "pw-link" and "-d" in c]
        out_unlinked = [c for c in unlink_calls if any(p in " ".join(c) for p, _ in ctx.out_links)]
        assert len(out_unlinked) >= len(ctx.out_links)

    def test_disconnects_tts_links_when_present(self, mock_subproc):
        ctx = setup_uplink_mixer(_MAC, tts_source_name="tincan_iris_tts")
        assert ctx is not None
        assert ctx.tts_links
        teardown_uplink_mixer(ctx)
        unlink_calls = [c for c in mock_subproc if c and c[0] == "pw-link" and "-d" in c]
        tts_unlinked = [c for c in unlink_calls if "tincan_iris_tts" in " ".join(c)]
        assert tts_unlinked

    def test_calls_pactl_unload_module(self, mock_subproc):
        ctx = setup_uplink_mixer(_MAC)
        assert ctx is not None
        mock_subproc.clear()
        teardown_uplink_mixer(ctx)
        pactl_unload = [c for c in mock_subproc if c and c[0] == "pactl" and "unload-module" in c]
        assert pactl_unload, "expected pactl unload-module call"

    def test_pactl_unload_uses_correct_module_id(self, mock_subproc):
        ctx = setup_uplink_mixer(_MAC)
        assert ctx is not None
        mock_subproc.clear()
        teardown_uplink_mixer(ctx)
        pactl_unload = [c for c in mock_subproc if c and c[0] == "pactl" and "unload-module" in c]
        assert pactl_unload
        assert str(ctx.module_id) in " ".join(pactl_unload[0])


# ---------------------------------------------------------------------------
# §5 BargeInController
# ---------------------------------------------------------------------------

class TestBargeInController:
    _THRESHOLD = 500.0
    _HANGOVER = 5

    def _make(self) -> BargeInController:
        return BargeInController(threshold_rms=self._THRESHOLD, hangover_frames=self._HANGOVER)

    def test_initially_not_muted(self):
        ctrl = self._make()
        assert ctrl.is_muted() is False

    def test_update_returns_false_for_silence(self):
        ctrl = self._make()
        result = ctrl.update(mic_rms=10.0)
        assert result is False

    def test_update_returns_true_when_rms_exceeds_threshold(self):
        ctrl = self._make()
        result = ctrl.update(mic_rms=self._THRESHOLD + 1.0)
        assert result is True

    def test_is_muted_true_after_speech_frame(self):
        ctrl = self._make()
        ctrl.update(mic_rms=self._THRESHOLD + 50.0)
        assert ctrl.is_muted() is True

    def test_stays_muted_during_hangover(self):
        ctrl = self._make()
        ctrl.update(mic_rms=self._THRESHOLD + 100.0)
        for i in range(self._HANGOVER - 1):
            result = ctrl.update(mic_rms=0.0)
            assert result is True, f"expected muted during hangover frame {i}"

    def test_unmuted_after_hangover_expires(self):
        ctrl = self._make()
        ctrl.update(mic_rms=self._THRESHOLD + 100.0)
        for _ in range(self._HANGOVER):
            ctrl.update(mic_rms=0.0)
        result = ctrl.update(mic_rms=0.0)
        assert result is False

    def test_is_muted_false_after_hangover(self):
        ctrl = self._make()
        ctrl.update(mic_rms=self._THRESHOLD + 100.0)
        for _ in range(self._HANGOVER + 1):
            ctrl.update(mic_rms=0.0)
        assert ctrl.is_muted() is False

    def test_re_entering_speech_resets_hangover(self):
        ctrl = self._make()
        ctrl.update(mic_rms=self._THRESHOLD + 100.0)
        for _ in range(self._HANGOVER - 2):
            ctrl.update(mic_rms=0.0)
        ctrl.update(mic_rms=self._THRESHOLD + 100.0)
        for _ in range(self._HANGOVER - 1):
            result = ctrl.update(mic_rms=0.0)
            assert result is True, "hangover should restart after re-entering speech"

    def test_at_exact_threshold_triggers_mute(self):
        ctrl = self._make()
        result = ctrl.update(mic_rms=self._THRESHOLD)
        assert result is True

    def test_just_below_threshold_no_mute(self):
        ctrl = self._make()
        result = ctrl.update(mic_rms=self._THRESHOLD - 0.001)
        assert result is False
