# HFP/SCO calls fail on Fedora — root cause: SELinux drops the SCO fd at dbus-broker

**Status:** Root cause **PROVEN** (2026-06-09). Exact SELinux rule + policy fix
pending verification (needs one test call — deferred to next session).
**Severity:** HFP phone-call audio is completely broken under SELinux Enforcing.

## Symptom

A HFP call sets up the service-level connection fine, then at SCO (audio)
setup ofono logs `System bus has disconnected!` and exits. No audio, call drops.
Reproduced on every attempt. WirePlumber then logs `Failed to start HFP/HSP
backend ofono` — but that is a *consequence* (it reacts to ofono vanishing).

## Root cause (proven)

1. On SCO setup, ofono passes the **SCO socket fd** to WirePlumber's audio
   agent via `org.ofono.HandsfreeAudioManager` → agent `NewConnection(card, fd,
   codec)`, sent over the **system bus** with the fd in `SCM_RIGHTS`.
   (ofono strace: `sendmsg(... NewConnection ... SCM_RIGHTS fd ...) = 161`.)
2. **dbus-broker** (the Fedora system bus, domain `system_dbusd_t`) must receive
   that fd to relay it. **SELinux refuses dbus-broker permission to receive the
   Bluetooth SCO socket fd.** The kernel silently **drops the fd and sets
   `MSG_CTRUNC`** on the broker's `recvmsg`.
3. dbus-broker treats any `MSG_CTRUNC` as an LSM fd-refusal and, per
   `src/dbus/socket.c:632` (`socket_recvmsg`), **closes the sender's connection**
   — i.e. it disconnects ofono. ofono sees EOF and exits.

The teardown stack (perf DWARF, `shutdown(fd=ofono, SHUT_WR)`):

```
__shutdown → socket_shutdown_now → socket_shutdown → socket_close
  → socket_recvmsg (+0x39f, the MSG_CTRUNC branch / socket.c:632)
  → socket_dispatch_read → connection_dispatch → peer_dispatch → main
```

socket.c:632 comment (verbatim): *"if an LSM refuses the D-Bus client to send
us an FD, the FD is just dropped and MSG_CTRUNC will be set ... Our only
possible way to deal with this is to disconnect the client."*

## Proof

`setenforce 0` (Permissive) → place a call → **the call connects, audio works.**
`setenforce 1` → fails again. Single-variable, reproduced. That is the proof.

## Why it took a full day to find (and the dbus-broker usability bug)

The SELinux denial is **`dontaudit`'d** — it produces **zero** AVC log entries,
even in Permissive. And dbus-broker's disconnect on `MSG_CTRUNC` is **completely
unlogged** (no journal, no `--audit` entry). So there was no log anywhere
pointing at the cause. It was only found by `perf record -e
syscalls:sys_enter_shutdown --call-graph dwarf -p <broker>` to get the teardown
stack, then reading `socket_recvmsg`, then the Permissive A/B test.

## What it is NOT (corrects earlier investigation)

- NOT ofono failing to negotiate fd-passing (it has `AGREE_UNIX_FD`).
- NOT WirePlumber unable to receive fds (its system-bus connection receives
  fds fine — observed 8 SCM_RIGHTS receives on the same connection).
- NOT a D-Bus `<deny>` policy issue (`ofono.conf` allows the
  `HandsfreeAudioAgent` interface; default policy allows `receive method_call`).
- NOT a dbus-broker "fd strictness" bug and NOT a message-malformation issue —
  the message is well-formed (`UNIX_FDS=1` + one real fd). The broker never even
  forwards it; ofono is killed in the broker's *receive* path.

## Fix (to verify next session)

1. `sudo semodule -DB`   # disable dontaudit so the denial logs
2. Place one call (one ring is enough to trigger the SCO fd pass).
3. `sudo ausearch -m AVC -ts recent`   # the exact denied perm (system_dbusd_t + the SCO socket class)
4. `sudo ausearch -m AVC -ts recent | audit2allow -M tincan_hfp_sco`
5. `sudo semodule -i tincan_hfp_sco.pp`
6. `sudo semodule -B`    # re-enable dontaudit
7. `sudo setenforce 1` and place a call — should now connect in Enforcing.

The proper upstream fix is in **fedora `selinux-policy`** (allow `system_dbusd_t`
to relay the bluetooth SCO socket fd). Same class as RH Bugzilla #183145.

## Where to report (after verification)

- **fedora-selinux/selinux-policy** (primary — the missing allow rule).
- **bus1/dbus-broker**: the `MSG_CTRUNC`→disconnect path is silent/undebuggable;
  relates to issue #192 (disconnect with no diagnostics). Suggest a log line.
- Note in **ofono** / **pipewire (wireplumber)** trackers as a known Fedora
  SELinux interaction for HFP-over-ofono.

## Environment

Fedora 44, `selinux-policy-44.2-1.fc44`, `dbus-broker-37-8.fc44`,
`ofono-2.19-2.fc44`, pipewire/wireplumber bluez5 ofono backend.
