#!/bin/bash
# Install the tincan HFP/SCO SELinux policy module.
# Fixes: dbus-broker drops oFono SCO fd (MSG_CTRUNC) under Enforcing,
# killing HFP call audio.  See tincan-jekiq for full root-cause analysis.
#
# Usage (needs sudo):
#   cd packaging/selinux && sudo ./install.sh
#
# After install, place a live call and verify SCO audio works.
# If audio fails, see verification steps below.

set -euo pipefail

POLICY_NAME=tincan_hfp_sco
TE_FILE="${POLICY_NAME}.te"

if [[ $EUID -ne 0 ]]; then
    echo "ERROR: run with sudo" >&2
    exit 1
fi

echo "Building ${POLICY_NAME} SELinux policy module..."
checkmodule -M -m -o "${POLICY_NAME}.mod" "${TE_FILE}"
semodule_package -o "${POLICY_NAME}.pp" -m "${POLICY_NAME}.mod"

echo "Installing ${POLICY_NAME}.pp..."
semodule -i "${POLICY_NAME}.pp"
# Copy to the standard SELinux packages dir so unprivileged detection works.
# tincand's hfp_capability._check_module_loaded() looks here when semodule -l
# is unavailable (denied for non-root on some Fedora kernel/policy combos).
install -m 644 "${POLICY_NAME}.pp" "/usr/share/selinux/packages/${POLICY_NAME}.pp"
echo "Done.  Verify with: semodule -l | grep ${POLICY_NAME}"

echo ""
echo "--- Verification steps ---"
echo "1. Connect your paired iPhone and place a live call"
echo "2. Confirm SCO audio works (bidirectional)"
echo "3. If still failing, capture AVC with:"
echo "   sudo semodule -DB && <place call> && sudo ausearch -m AVC | audit2allow -M ${POLICY_NAME}_extra"
echo "   sudo semodule -B"
