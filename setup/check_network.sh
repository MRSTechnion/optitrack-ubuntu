#!/usr/bin/env bash
# Check that this machine can receive OptiTrack data from Motive.
# No sudo needed. Usage: setup/check_network.sh [motive_ip]
#
# Override defaults with environment variables:
#   MULTICAST_GROUP (239.255.42.99)  COMMAND_PORT (1510)  DATA_PORT (1511)

set -u
SERVER_IP="${1:-192.168.77.1}"
GROUP="${MULTICAST_GROUP:-239.255.42.99}"
CMD_PORT="${COMMAND_PORT:-1510}"
DATA_PORT="${DATA_PORT:-1511}"
SUBNET_PREFIX="${SERVER_IP%.*}."   # 192.168.77.

ok()   { printf '  \033[32m[ OK ]\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m[WARN]\033[0m %s\n' "$*"; }
fail() { printf '  \033[31m[FAIL]\033[0m %s\n' "$*"; FAILED=1; }
hint() { printf '         %s\n' "$*"; }
FAILED=0

echo "OptiTrack network check  (Motive at $SERVER_IP, multicast $GROUP:$DATA_PORT)"
echo

# 1. An address on the Motive network ---------------------------------------
echo "1. Network interface"
IFACE=$(ip -4 -o addr show | awk -v p="$SUBNET_PREFIX" 'index($4, p) == 1 {print $2; exit}')
LOCAL_IP=$(ip -4 -o addr show | awk -v p="$SUBNET_PREFIX" 'index($4, p) == 1 {split($4, a, "/"); print a[1]; exit}')
if [ -z "$IFACE" ]; then
    fail "No interface has an address in ${SUBNET_PREFIX}x"
    hint "Connect to the lab network and set your assigned static IP:"
    hint "  sudo setup/setup_network.sh"
    echo; echo "Result: cannot continue without an address on the Motive network."
    exit 1
fi
if [ -d "/sys/class/net/$IFACE/wireless" ]; then
    KIND="Wi-Fi"
else
    KIND="wired"
fi
ok "$IFACE ($KIND) has $LOCAL_IP"
[ "$KIND" = "Wi-Fi" ] && warn "Wi-Fi: multicast may be slow or lossy; check the rate in step 5."

# 2. Reach the Motive PC ----------------------------------------------------
echo "2. Motive PC"
if ping -c 2 -W 1 -I "$IFACE" "$SERVER_IP" >/dev/null 2>&1; then
    ok "$SERVER_IP answers ping"
else
    warn "$SERVER_IP does not answer ping (Windows often blocks ping; step 4 is the real test)"
fi

# 3. Multicast route and firewall -------------------------------------------
echo "3. Multicast route and firewall"
MC_DEV=$(ip route get "$GROUP" 2>/dev/null | grep -o 'dev [^ ]*' | head -1 | cut -d' ' -f2)
if [ "$MC_DEV" = "$IFACE" ]; then
    ok "Multicast traffic routes via $IFACE"
else
    warn "Multicast routes via ${MC_DEV:-nothing}, not $IFACE."
    hint "The Python client in this repo still works (it picks the interface itself),"
    hint "but other tools (NatNet C++ SDK, mocap4r2) may receive nothing. Fix with:"
    hint "  sudo setup/setup_network.sh"
fi
UFW_ON=0
if [ -r /etc/ufw/ufw.conf ] && grep -q '^ENABLED=yes' /etc/ufw/ufw.conf; then
    UFW_ON=1
    ok "ufw firewall is on (its rules need sudo to read; step 5 shows if data gets through)"
else
    ok "ufw firewall is off"
fi

# 4 + 5. Talk to Motive and count packets (Python standard library only) ----
PYTHON=$(command -v python3 || true)
if [ -z "$PYTHON" ]; then
    fail "python3 not found (sudo apt install python3)"; exit 1
fi
"$PYTHON" - "$SERVER_IP" "$LOCAL_IP" "$GROUP" "$CMD_PORT" "$DATA_PORT" "$UFW_ON" <<'EOF'
import socket, struct, sys, time
server, local, group, cmd_port, data_port = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5])
ufw_on = sys.argv[6] == "1"
G, Y, R, N = "\033[32m", "\033[33m", "\033[31m", "\033[0m"
failed = False

print("4. Motive command port")
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind((local, 0)); s.settimeout(2)
s.sendto(struct.pack("<HH", 0, 5) + b"Ping\0", (server, cmd_port))
try:
    d, _ = s.recvfrom(65535)
    name = d[4:260].split(b"\0")[0].decode()
    app = ".".join(map(str, d[260:264])); nn = ".".join(map(str, d[264:268]))
    print(f"  {G}[ OK ]{N} {name} {app}, NatNet {nn}")
    if tuple(d[264:266]) < (4, 1):
        print(f"  {Y}[WARN]{N} this toolkit needs NatNet 4.1+ (Motive 3.x)")
except socket.timeout:
    failed = True
    print(f"  {R}[FAIL]{N} no reply from {server}:{cmd_port}")
    print("         Is Motive running with streaming enabled (Settings > Streaming)?")
    print(f"         Is Motive's 'Local Interface' set to {server} (not loopback)?")

print("5. Multicast data (3 seconds)")
d = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
d.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
d.bind(("", data_port))
d.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(group) + socket.inet_aton(local))
d.settimeout(0.5)
n, first, last, t0 = 0, None, None, time.time()
while time.time() - t0 < 3:
    try:
        pkt, _ = d.recvfrom(65535)
    except socket.timeout:
        continue
    if struct.unpack_from("<H", pkt)[0] == 7:
        fn = struct.unpack_from("<i", pkt, 4)[0]
        first = fn if first is None else first
        last = fn; n += 1
if n == 0:
    failed = True
    print(f"  {R}[FAIL]{N} no frames on {group}:{data_port}")
    if ufw_on:
        print("         The ufw firewall is on: allow the data with  sudo setup/setup_network.sh")
    print("         Check Motive: Settings > Streaming > Transmission Type = Multicast.")
    print("         On Wi-Fi, the access point may drop multicast (see README, 'Wi-Fi users').")
else:
    rate = n / 3
    lost = (last - first + 1) - n
    loss = 100.0 * lost / (last - first + 1)
    colour, tag = (G, " OK ") if loss < 1 else (Y, "WARN")
    print(f"  {colour}[{tag}]{N} {n} frames, {rate:.0f} frames/s, {loss:.1f}% lost")
    if loss >= 1:
        print("         Frames are being dropped (typical on Wi-Fi). See README, 'Wi-Fi users'.")
sys.exit(1 if failed else 0)
EOF
PY_STATUS=$?
[ $PY_STATUS -ne 0 ] && FAILED=1

echo
if [ $FAILED -eq 0 ]; then
    echo "Result: OK, this machine receives OptiTrack data."
else
    echo "Result: problems found, see [FAIL] lines above."
fi
exit $FAILED
