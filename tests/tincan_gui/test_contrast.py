"""
WCAG 2.1 AA contrast ratio tests — pure Python, no PySide6 required.
Design spec: tincan-s42 §4.1.
Bead: tincan-9ho.

These tests run immediately (no GUI dependency) and document the spec color values.
The companion file test_accessibility.py covers widget-level enforcement.
"""


def _linearize(c: int) -> float:
    s = c / 255.0
    return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4


def _relative_luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _linearize(r) + 0.7152 * _linearize(g) + 0.0722 * _linearize(b)


def _contrast_ratio(fg: str, bg: str) -> float:
    l1 = _relative_luminance(fg)
    l2 = _relative_luminance(bg)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


class TestContrastRatioSpec:
    """
    Verify the spec color pairs from tincan-s42 §4.1 satisfy WCAG 2.1 AA
    (4.5:1 for normal text ≤18pt / ≤14pt bold).
    """

    def test_fixed_timestamp_color_6b7280_passes_aa_on_white(self):
        # tincan-9ho fix: #9ca3af → #6b7280 for all metadata on white (#ffffff)
        ratio = _contrast_ratio("#6b7280", "#ffffff")
        assert ratio >= 4.5, f"Expected ≥4.5 for AA, got {ratio:.2f}"

    def test_old_timestamp_color_9ca3af_fails_aa_on_white(self):
        # Confirms the fix is necessary — the old value must fail.
        ratio = _contrast_ratio("#9ca3af", "#ffffff")
        assert ratio < 4.5, f"Old color must fail AA; got {ratio:.2f}"

    def test_conversation_name_passes_aa(self):
        # #111827 on #f3f4f6 (spec §4.1: ~14:1)
        assert _contrast_ratio("#111827", "#f3f4f6") >= 4.5

    def test_inbound_bubble_body_passes_aa(self):
        # #111827 on #f3f4f6 (spec §4.1: ~14:1)
        assert _contrast_ratio("#111827", "#f3f4f6") >= 4.5

    def test_outbound_bubble_body_passes_aa(self):
        # #ffffff on #1d4ed8 (spec §4.1: ~5.4:1)
        assert _contrast_ratio("#ffffff", "#1d4ed8") >= 4.5

    def test_warning_text_passes_aa(self):
        # #92400e on #fef9c3 (spec §4.1: ~4.8:1)
        assert _contrast_ratio("#92400e", "#fef9c3") >= 4.5

    def test_status_green_passes_aa(self):
        # #86efac on #1e3a5f (spec §4.1: ~4.5:1 borderline)
        assert _contrast_ratio("#86efac", "#1e3a5f") >= 4.5

    def test_status_red_passes_aa(self):
        # #fca5a5 on #1e3a5f (spec §4.1: ~4.3:1 borderline)
        assert _contrast_ratio("#fca5a5", "#1e3a5f") >= 4.5
