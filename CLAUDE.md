# optitrack-ubuntu

A simple guide plus a small toolkit for receiving OptiTrack/Motive data on any
Ubuntu machine (20.04 or later) in the MRS lab. ROS 2 is the main user, but
the core must not depend on ROS.

## Lab setup (fixed facts)

- **Motive PC:** Windows, Motive 3.1.0, IP `192.168.77.1`. It streams NatNet 4.x.
- **Network:** MRS lab network, `192.168.77.0/24`.
  - Lab machines connect by cable.
  - Personal laptops may connect over the lab's internal Wi‑Fi.
  - Every machine and user has an assigned **static IP**.
- **Streaming:** Multicast with the defaults:
  - group `239.255.42.99`
  - command port UDP `1510` (unicast handshake and model definitions)
  - data port UDP `1511` (multicast frames)
- **Up Axis:** Motive streams **Z-up**. Do not convert axes; pass the data
  through. The README troubleshooting section must say: if orientation looks
  wrong (rotated 90°, "up" pointing sideways), check Motive → Settings →
  Streaming → Up Axis = Z Axis.
- **ROS 2:** the lab uses **Humble** (Ubuntu 22.04). The maintainer uses
  **Lyrical** (Ubuntu 26.04). Both must work. A shared Docker image is a
  possible future step, not current scope.

## Architecture (agreed)

1. **`src/optitrack_natnet/`** — pure-Python NatNet 4.1+ receiver.
   - `protocol.py`: packet decoding (no sockets), tested on `tests/fixtures/`
     recorded from the lab's Motive. `client.py`: sockets + handshake.
   - Standard library only; no compiled code.
   - Python 3.8+ so it runs on Ubuntu 20.04.
   - Yields rigid bodies as `id, name, position, quaternion, timestamp`.
2. **`examples/`** — plain scripts: `print_poses.py`, `log_csv.py`.
3. **`ros2/optitrack_ros2/`** — thin `rclpy` node on top of layer 1.
   - Publishes `PoseStamped` per rigid body, plus TF.
   - `rclpy` only, so the same code builds on Humble and Lyrical.
4. **`setup/`** — shell scripts:
   - `setup_network.sh`: uses `nmcli`; adds the `224.0.0.0/4` multicast route
     on the chosen interface and `ufw` rules for 192.168.77.0/24.
   - `check_network.sh`: diagnostics — IP, route, firewall, and whether
     packets arrive and at what rate.
5. **`README.md`** — the guide: Motive checklist → network → verify packets →
   Python → ROS 2 → troubleshooting table.

## Wi‑Fi users

Multicast over Wi‑Fi may be unreliable. The guide tells Wi‑Fi users to run
`check_network.sh` first. If it fails, they have two fallbacks:

- subscribe to ROS 2 topics published by a wired lab machine
  (`ROS_DOMAIN_ID`, plus a discovery server or Zenoh if needed);
- use a small unicast UDP relay script running on a wired machine.

## Reference repo

`/home/Ayalon/Projects/optitrack-obstacle-builder` (by the same maintainer;
GitHub `MRSTechnion/optitrack-obstacle-builder`). It is worth reusing:

- `src/obstacle_builder/natnet/client.py`: a wrapper around the vendored
  OptiTrack `NatNetClient.py`, with the defaults `DEFAULT_SERVER_IP`,
  `DEFAULT_STREAM_UP_AXIS = "z"`, and `_local_ip_for()` to pick the local
  interface.
- `src/obstacle_builder/adapters/ros2.py` and `ros2_node.py`: its ROS 2 node.
- Repo conventions: `pyproject.toml` (setuptools, src layout), ruff with
  line-length 100, pytest, GitHub Actions CI, MIT licence.

Note: that repo requires Python 3.10+. This repo targets 3.8+ for Ubuntu 20.04,
so avoid `X | None` syntax at runtime, or use `from __future__ import annotations`.

## Repo / publishing

- Start on the maintainer's personal GitHub; transfer to the lab GitHub
  (`MRSTechnion`) when finished.
- Keep the guide simple; the audience is lab students.
