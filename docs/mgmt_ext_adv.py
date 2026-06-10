#!/usr/bin/env python3
"""Raw MGMT probe for extended-advertising add (0x0054 params + 0x0055 data).
Bypasses BlueZ so we control the exact bytes. Run as root.
Usage: mgmt_ext_adv.py <hci_index>   (default 1 = dongle)
"""
import ctypes, ctypes.util, socket, struct, sys, time, select, os

AF_BLUETOOTH = 31
BTPROTO_HCI = 1
SOCK_RAW = 3
HCI_DEV_NONE = 0xFFFF
HCI_CHANNEL_CONTROL = 3

OP_REMOVE_ADVERTISING = 0x003F
OP_ADD_EXT_ADV_PARAMS = 0x0054
OP_ADD_EXT_ADV_DATA   = 0x0055
EV_CMD_COMPLETE = 0x0001
EV_CMD_STATUS   = 0x0002
STATUS = {0: "Success", 0x0d: "INVALID-PARAMS", 0x0a: "Busy", 0x11: "NotSupported",
          0x09: "AlreadyPending", 0x0c: "NotPowered", 0x07: "InvalidIndex", 0x0b: "Rejected"}


def mgmt_open():
    s = socket.socket(AF_BLUETOOTH, SOCK_RAW, BTPROTO_HCI)
    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    addr = struct.pack("<HHH", AF_BLUETOOTH, HCI_DEV_NONE, HCI_CHANNEL_CONTROL)
    buf = ctypes.create_string_buffer(addr, len(addr))
    if libc.bind(s.fileno(), buf, len(addr)) != 0:
        e = ctypes.get_errno(); raise OSError(e, os.strerror(e))
    s.setblocking(False)
    return s


def cmd(s, opcode, index, params=b""):
    s.send(struct.pack("<HHH", opcode, index, len(params)) + params)
    end = time.time() + 2.0
    while time.time() < end:
        r, _, _ = select.select([s], [], [], max(0, end - time.time()))
        if not r:
            break
        data = s.recv(2048)
        if len(data) < 6:
            continue
        ev, idx, plen = struct.unpack("<HHH", data[:6])
        p = data[6:6 + plen]
        if ev in (EV_CMD_COMPLETE, EV_CMD_STATUS) and len(p) >= 3:
            cop, stt = struct.unpack("<HB", p[:3])
            if cop == opcode:
                return stt
    return None


def st(x):
    return STATUS.get(x, f"0x{x:02x}") if x is not None else "NO-REPLY"


def params_0054(instance=1, flags=0x0001):
    return struct.pack("<BIHHIIb", instance, flags, 0, 0, 0, 0, 0x7f)  # 18 bytes


ADV_SOLICIT = bytes([0x11, 0x15]) + bytes.fromhex("d0002d121e4b0fa4994eceb531f40579")  # 18B
SCAN_NAME = bytes([0x07, 0x09]) + b"tincan"  # 8B


def case(s, index, label, adv_len, scan_len, payload, flags=0x0001):
    cmd(s, OP_REMOVE_ADVERTISING, index, struct.pack("<B", 1))
    pst = cmd(s, OP_ADD_EXT_ADV_PARAMS, index, params_0054(1, flags))
    body = struct.pack("<BBB", 1, adv_len, scan_len) + payload
    dst = cmd(s, OP_ADD_EXT_ADV_DATA, index, body)
    print(f"  {label:46} 0x0054={st(pst):14} 0x0055(plen={len(body):2})={st(dst)}")
    cmd(s, OP_REMOVE_ADVERTISING, index, struct.pack("<B", 1))


def main():
    index = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    s = mgmt_open()
    print(f"=== raw MGMT ext-adv probe on hci{index} (no bluez) ===")
    case(s, index, "A correct full (adv18+scan8, declared right)", 18, 8, ADV_SOLICIT + SCAN_NAME)
    case(s, index, "B empty (0/0)", 0, 0, b"")
    case(s, index, "C bluez-style oversize (declared 18/8 +8 extra)", 18, 8, ADV_SOLICIT + SCAN_NAME + b"\x00" * 8)
    case(s, index, "D adv-only correct (18/0)", 18, 0, ADV_SOLICIT)
    case(s, index, "E scan-only correct (0/8)", 0, 8, SCAN_NAME)
    case(s, index, "F tiny adv flags 020106 (3/0)", 3, 0, bytes([0x02, 0x01, 0x06]))


if __name__ == "__main__":
    main()
