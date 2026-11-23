#!/usr/bin/env bash
# Configure this machine to receive OptiTrack data from Motive.
#
#   sudo setup/setup_network.sh            # interactive
#   setup/setup_network.sh --dry-run       # only print what would be done
#
# What it does (via NetworkManager, so it survives reboots):
#   1. sets your assigned static IP on the interface connected to the lab network
#      (skipped if the interface already has an address on that network);
#   2. routes multicast (224.0.0.0/4) through that interface;
#   3. if the ufw firewall is enabled, allows NatNet data (UDP 1511) from the lab network;
#   4. on Wi-Fi, turns power saving off for that connection (otherwise many frames are lost).

set -euo pipefail
SERVER_IP="${SERVER_IP:-192.168.77.1}"
DATA_PORT="${DATA_PORT:-1511}"
PREFIX="${SERVER_IP%.*}"            # 192.168.77
SUBNET="${PREFIX}.0/24"
MC_ROUTE="224.0.0.0/4"
DRY_RUN=0
CHANGED=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

run() {
    echo "  + $*"
    [ $DRY_RUN -eq 1 ] || "$@"
}

if [ $DRY_RUN -eq 0 ] && [ "$(id -u)" -ne 0 ]; then
    echo "Run with sudo:  sudo $0   (or '$0 --dry-run' to preview)"; exit 1
fi
command -v nmcli >/dev/null || { echo "nmcli not found: this script needs NetworkManager."; exit 1; }

echo "OptiTrack network setup  (Motive at $SERVER_IP, lab network $SUBNET)"
[ $DRY_RUN -eq 1 ] && echo "(dry run: nothing will be changed)"
echo

# 1. Choose the interface ---------------------------------------------------
DEFAULT_IF=$(ip -4 -o addr show | awk -v p="${PREFIX}." 'index($4, p) == 1 {print $2; exit}')
echo "Network interfaces:"
nmcli -t -f DEVICE,TYPE,STATE,CONNECTION device status \
    | awk -F: '$2 == "ethernet" || $2 == "wifi" {printf "  %-18s %-9s %-14s %s\n", $1, $2, $3, $4}'
if [ -n "$DEFAULT_IF" ]; then
    read -r -p "Interface connected to the lab network (press Enter for $DEFAULT_IF): " IFACE
else
    read -r -p "Interface connected to the lab network (type its name from the list): " IFACE
fi
IFACE="${IFACE:-$DEFAULT_IF}"
[ -n "$IFACE" ] || { echo "No interface given."; exit 1; }
CON=$(nmcli -g GENERAL.CONNECTION device show "$IFACE" 2>/dev/null || true)
[ -n "$CON" ] || { echo "$IFACE has no active connection. Connect it (cable / Wi-Fi) first."; exit 1; }
echo "Using $IFACE, connection '$CON'"
echo

# 2. Static IP --------------------------------------------------------------
CURRENT_IP=$(ip -4 -o addr show dev "$IFACE" | awk -v p="${PREFIX}." 'index($4, p) == 1 {print $4; exit}')
if [ -n "$CURRENT_IP" ]; then
    echo "1. IP address: $IFACE already has $CURRENT_IP (not changed)"
else
    read -r -p "Your assigned IP address (${PREFIX}.X): " MY_IP
    [[ "$MY_IP" =~ ^${PREFIX//./\\.}\.[0-9]{1,3}$ ]] || { echo "Expected ${PREFIX}.X"; exit 1; }
    if [ "$(nmcli -g ipv4.method connection show "$CON")" = "auto" ]; then
        echo "WARNING: '$CON' currently gets its address automatically (DHCP)."
        echo "         Switching it to $MY_IP removes its gateway: if this is your"
        echo "         internet connection (e.g. campus Wi-Fi), you picked the wrong interface."
        read -r -p "Continue? [y/N] " ANSWER
        [[ "$ANSWER" =~ ^[Yy] ]] || { echo "Nothing changed."; exit 1; }
    fi
    echo "1. IP address: setting $MY_IP/24 on '$CON'"
    run nmcli connection modify "$CON" ipv4.method manual ipv4.addresses "$MY_IP/24"
    CHANGED=1
fi

# 3. Multicast route --------------------------------------------------------
if nmcli -g ipv4.routes connection show "$CON" | grep -q "$MC_ROUTE"; then
    echo "2. Multicast route: already set on '$CON'"
else
    echo "2. Multicast route: sending $MC_ROUTE via $IFACE"
    run nmcli connection modify "$CON" +ipv4.routes "$MC_ROUTE"
    CHANGED=1
fi

# 4. Firewall ---------------------------------------------------------------
if command -v ufw >/dev/null && grep -q '^ENABLED=yes' /etc/ufw/ufw.conf 2>/dev/null; then
    echo "3. Firewall: allowing UDP $DATA_PORT from $SUBNET on $IFACE"
    run ufw allow in on "$IFACE" proto udp from "$SUBNET" to any port "$DATA_PORT" \
        comment "OptiTrack NatNet"
else
    echo "3. Firewall: ufw is off, nothing to do"
fi

# 5. Wi-Fi power saving -----------------------------------------------------
# With power saving on, the access point holds multicast for the laptop and
# sends it in bursts every ~100 ms: measured in the lab, 34% of frames arrived
# with power saving on vs ~82% with it off. Only this connection is changed.
if [ "$(nmcli -g connection.type connection show "$CON")" = "802-11-wireless" ]; then
    if [ "$(nmcli -g 802-11-wireless.powersave connection show "$CON")" = "2 (disable)" ] \
        || [ "$(nmcli -g 802-11-wireless.powersave connection show "$CON")" = "disable" ]; then
        echo "4. Wi-Fi power saving: already off for '$CON'"
    else
        echo "4. Wi-Fi power saving: turning it off for '$CON' (more OptiTrack frames arrive)"
        run nmcli connection modify "$CON" 802-11-wireless.powersave 2
        CHANGED=1
    fi
else
    echo "4. Wi-Fi power saving: not Wi-Fi, nothing to do"
fi

# 6. Apply ------------------------------------------------------------------
if [ $CHANGED -eq 1 ]; then
    echo "5. Applying changes (the connection restarts for a moment)"
    run nmcli connection up "$CON"
else
    echo "5. Nothing to apply, already configured"
fi
echo

if [ $DRY_RUN -eq 0 ]; then
    sleep 2
    # Run the check as the normal user (no sudo needed)
    CHECK="$(dirname "$0")/check_network.sh"
    if [ -n "${SUDO_USER:-}" ]; then
        sudo -u "$SUDO_USER" "$CHECK" "$SERVER_IP" || true
    else
        "$CHECK" "$SERVER_IP" || true
    fi
fi
