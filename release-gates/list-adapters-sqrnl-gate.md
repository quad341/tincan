# Release Gate: list_adapters() + HFP/SCO capability detection

**Deploy bead:** tincan-sqrnl  
**Source bead:** tincan-qxg28 (review), tincan-hchsf (impl), tincan-azcok (tests)  
**Branch:** fix/call-setup-ready-z0qqo  
**Reviewed commit:** 9fdac45 (feat) + c2bad44 (tests)  
**Current HEAD:** 7d3af42  
**Gate date:** 2026-06-14

## Gate Result: FAIL

Criterion 3 (tests pass) fails due to 23 failing adapter picker GUI tests committed by a later TDD commit on this branch.

---

## Criteria

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-qxg28 verdict: PASS. Reviewer confirmed all 3 ACs met. |
| 2 | Acceptance criteria met | **PASS** | detect_adapter_hfp_sco_capability(modalias) ✓, _read_modalias(hci_name) ✓, list_adapters(bus=None) ✓. 17/17 adapter_check tests pass. |
| 3 | Tests pass | **FAIL** | `python -m pytest tests/` → 23 FAILED (tests/tincan_gui/test_adapter_picker.py), 1887 passed, 1 skipped, 6 xfailed. |
| 4 | No high-severity findings | **PASS** | Only LOW findings: ruff I001/F401/E501 in test file (CI non-blocking per continue-on-error: true). |
| 5 | Final branch clean | **PASS** | Branch is up to date with origin/fix/call-setup-ready-z0qqo. No uncommitted changes. |
| 6 | Branch diverges cleanly from main | **PASS** | Merge-base with origin/main: 8860622. No merge conflicts detected. |
| 7 | Single feature theme | **PASS** | This deploy bead covers a single theme: Bluetooth adapter enumeration + HFP/SCO capability detection. |

---

## Criterion 3 Detail — Failing Tests

**File:** `tests/tincan_gui/test_adapter_picker.py` (commit c5bd3ec, tincan-t53s7)

These are TDD behavioral tests for the GUI adapter picker UI. They fail because the GUI implementation is not yet built:
- `tincan-gu24r` (adapter-changed restart banner in settings_dialog.py) — OPEN
- `tincan-crfu9` (saved-adapter-unavailable banner in main.py) — OPEN

The 23 failures are AttributeErrors on `_adapter_combo`, `_adapter_unavailable_banner`, and `_adapter_restart_banner` attributes not yet present in `MainWindow`.

Commit `7d3af42` (tincan-0fq30: add get_adapters() in dbus_client) was present at gate time but did not fix the failures.

**Required fix:** Mark the 23 adapter picker tests with `@pytest.mark.xfail(reason="awaiting tincan-crfu9 and tincan-gu24r implementation")` until the GUI is built, OR remove commit c5bd3ec from this branch until the implementation is ready.

---

## 17/17 Adapter Check Tests (list_adapters scope)

All tests for the deployed work pass:

```
tests/tincand/test_adapter_check.py::TestListAdaptersEnumeration::test_zero_adapters_returns_empty_list PASSED
tests/tincand/test_adapter_check.py::TestListAdaptersEnumeration::test_single_adapter_returns_one_element_list PASSED
tests/tincand/test_adapter_check.py::TestListAdaptersEnumeration::test_two_adapters_returns_two_element_list PASSED
tests/tincand/test_adapter_check.py::TestListAdaptersErrorHandling::test_dbus_exception_returns_empty_list PASSED
tests/tincand/test_adapter_check.py::TestListAdaptersSingleCall::test_call_count_is_one_with_zero_adapters PASSED
tests/tincand/test_adapter_check.py::TestListAdaptersSingleCall::test_call_count_is_one_with_one_adapter PASSED
tests/tincand/test_adapter_check.py::TestListAdaptersSingleCall::test_call_count_is_one_with_two_adapters PASSED
tests/tincand/test_adapter_check.py::TestListAdaptersPathValidation::test_device_path_is_skipped PASSED
tests/tincand/test_adapter_check.py::TestListAdaptersPathValidation::test_non_digit_hci_suffix_is_skipped PASSED
tests/tincand/test_adapter_check.py::TestListAdaptersDictStructure::test_all_required_keys_present PASSED
tests/tincand/test_adapter_check.py::TestListAdaptersDictStructure::test_le_capable_true_when_le_adv_manager_present PASSED
tests/tincand/test_adapter_check.py::TestListAdaptersDictStructure::test_le_capable_false_when_le_adv_manager_absent PASSED
tests/tincand/test_adapter_check.py::TestDetectAdapterHfpScoCapability::test_known_good_usb_id_returns_true PASSED
tests/tincand/test_adapter_check.py::TestDetectAdapterHfpScoCapability::test_known_bad_usb_id_returns_false PASSED
tests/tincand/test_adapter_check.py::TestDetectAdapterHfpScoCapability::test_none_returns_none PASSED
tests/tincand/test_adapter_check.py::TestDetectAdapterHfpScoCapability::test_empty_string_returns_none PASSED
tests/tincand/test_adapter_check.py::TestDetectAdapterHfpScoCapability::test_non_usb_modalias_returns_none PASSED
```
