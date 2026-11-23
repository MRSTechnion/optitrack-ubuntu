# OptiTrack on Ubuntu

[![CI](https://github.com/MRSTechnion/optitrack-ubuntu/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/MRSTechnion/optitrack-ubuntu/actions/workflows/ci.yml)

Receive live rigid body poses from the lab's OptiTrack system (Motive) on any
Ubuntu computer, in plain Python or in ROS 2.

- Works on Ubuntu **20.04, 22.04, 24.04 and 26.04** (Python 3.8+).
- ROS 2 **Humble** and **Lyrical** (other distros with `rclpy` should work too).
- No OptiTrack software to install on Ubuntu: the Python package uses only the
  standard library.

```
Motive PC (Windows, 192.168.77.1) ──multicast──▶ your Ubuntu computer (192.168.77.x)
                                                   ├─ Python:  optitrack_natnet
                                                   └─ ROS 2:   /optitrack/<body>/pose + TF
```

## Contents

1. [Quick start](#1-quick-start)
2. [Network setup](#2-network-setup)
3. [Check the connection](#3-check-the-connection)
4. [Python](#4-python)
5. [ROS 2](#5-ros-2)
6. [Coordinates](#6-coordinates)
7. [Troubleshooting](#7-troubleshooting)
8. [Motive settings (lab staff)](#8-motive-settings-lab-staff)

---

## 1. Quick start

You need a cable to the lab network (or the lab Wi‑Fi) and **your assigned
IP address** (`192.168.77.x`, ask the lab staff).

```bash
git clone https://github.com/MRSTechnion/optitrack-ubuntu.git
cd optitrack-ubuntu
sudo setup/setup_network.sh      # once per computer
setup/check_network.sh           # should end with "Result: OK"
```

Then continue with [Python](#4-python) or [ROS 2](#5-ros-2).

## 2. Network setup

Run once on each computer:

```bash
sudo setup/setup_network.sh
```

It asks for the network interface connected to the lab (press **Enter** to
accept the one it detected) and, if needed, your assigned IP. Then it:

1. sets your static IP on that interface (only if it has none on `192.168.77.x`);
2. routes multicast traffic through that interface, which matters when the
   computer also has another connection, e.g. campus Wi‑Fi;
3. if the `ufw` firewall is on, allows traffic from the lab network on that
   interface: the OptiTrack data and ROS 2 between lab computers;
4. on Wi‑Fi, turns **power saving** off for the lab Wi‑Fi connection only
   (see below).

The settings are saved in NetworkManager and survive a reboot. Running the
script again is safe: it changes nothing that is already set. To preview
without changing anything: `setup/setup_network.sh --dry-run`.

### Wi-Fi users

OptiTrack data is sent as multicast, which Wi‑Fi delivers less reliably than a
cable. Measured on the lab Wi‑Fi (`mrs`) with Motive at 180 frames/s:

| Laptop Wi‑Fi power saving | Frames received | Typical delay | Occasional pauses |
|---|---|---|---|
| On (Ubuntu's default) | ~35% | ~90 ms | up to 0.6 s |
| **Off** (set by `setup_network.sh`) | **80–99%** | **~10 ms** | up to 0.3 s |

So on Wi‑Fi:

- **Run `sudo setup/setup_network.sh` while connected to the lab Wi‑Fi**, so
  power saving is turned off for that network.
- Wi‑Fi is fine for **monitoring, visualisation and slow robots**.
- For **control loops** (e.g. flying drones), use a **cable**, or run the
  OptiTrack ROS 2 node on a wired computer and subscribe to its topics (see
  [ROS 2 on several computers](#ros-2-on-several-computers)).

## 3. Check the connection

```bash
setup/check_network.sh
```

No `sudo` needed. A healthy result:

```
1. Network interface
  [ OK ] enx00e04c141968 (wired) has 192.168.77.30
2. Motive PC
  [ OK ] 192.168.77.1 answers ping
3. Multicast route and firewall
  [ OK ] Multicast traffic routes via enx00e04c141968
  [ OK ] ufw firewall is off
4. Motive command port
  [ OK ] Motive 3.1.0.1, NatNet 4.1.0.0
5. Multicast data (3 seconds)
  [ OK ] 541 frames, 180 frames/s, 0.0% lost

Result: OK, this machine receives OptiTrack data.
```

Every `[FAIL]` line is followed by what to do. See also
[Troubleshooting](#7-troubleshooting).

## 4. Python

### Install

Use a virtual environment (on Ubuntu 24.04 and later, `pip install` outside one
is blocked):

```bash
sudo apt install python3-venv              # if not installed yet
cd optitrack-ubuntu
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip                  # needed on Ubuntu 20.04
pip install -e .
```

### Try it

```bash
optitrack-print
```

```
Connected to Motive 3.1.0.1, NatNet 4.1.0.0
Rigid bodies: {8: 'TestBody', 1: 'cf232'}
 16540138  TestBody         pos=(+0.102, -0.207, +0.003)  quat=(-0.000, -0.000, +0.000, +1.000)
 16540138  cf232            pos=(-0.044, -0.489, +0.567)  quat=(-0.022, +0.019, +0.039, +0.999)  (not tracked)
```

### Use it in your code

```python
from optitrack_natnet import NatNetClient

with NatNetClient() as client:            # Motive at 192.168.77.1 by default
    for frame in client.frames():         # every Motive frame (e.g. 180 per second)
        for rb in frame.rigid_bodies:
            if rb.tracking_valid:
                x, y, z = rb.position             # metres
                qx, qy, qz, qw = rb.orientation   # quaternion
                print(rb.name, x, y, z)
```

If Motive's Transmission Type is **Unicast** instead of Multicast (not the
lab's setting), use `NatNetClient(multicast=False)` or `optitrack-print --unicast`.

Each rigid body has `id`, `name`, `position`, `orientation`,
`tracking_valid` and `error` (mean marker error, metres). Each frame has
`frame_number` and `timestamp` (seconds, Motive's clock).

To receive in the background instead of a loop:

```python
client = NatNetClient().connect()
client.start(lambda frame: print(frame.rigid_bodies))   # runs in its own thread
...
client.close()
```

### Examples

| Script | What it does |
|---|---|
| [`examples/print_poses.py`](examples/print_poses.py) | The smallest program: print poses 10 times per second. Copy it as a starting point. |
| [`examples/log_csv.py`](examples/log_csv.py) | Record to CSV: `python examples/log_csv.py run1.csv --duration 30 --body cf232` |

## 5. ROS 2

### Build

Clone into your workspace and build as usual:

```bash
source /opt/ros/humble/setup.bash          # or lyrical, jazzy, ...
mkdir -p ~/ros2_ws/src && cd ~/ros2_ws/src
git clone https://github.com/MRSTechnion/optitrack-ubuntu.git
cd ~/ros2_ws
colcon build --packages-select optitrack_ros2
source install/setup.bash
```

(Do the [network setup](#2-network-setup) too, from `~/ros2_ws/src/optitrack-ubuntu`.)

### Run

```bash
ros2 launch optitrack_ros2 optitrack.launch.py
```

```
[optitrack]: Connected to Motive 3.1.0.1 at 192.168.77.1 (local 192.168.77.30); rigid bodies: TestBody, cf232
[optitrack]: Publishing TestBody on /optitrack/TestBody/pose
[optitrack]: TestBody: tracked, publishing
[optitrack]: cf232: not tracked by Motive (markers not visible?); not publishing until it is tracked again
```

For every rigid body streamed by Motive:

| Output | Type |
|---|---|
| `/optitrack/<body>/pose` | `geometry_msgs/PoseStamped`, `frame_id` = `world` |
| TF `world` → `<body>` | `tf2_msgs/TFMessage` on `/tf` |

A body that Motive cannot see is **not published** (no stale poses). The node
logs when this starts and stops.

```bash
ros2 topic echo /optitrack/TestBody/pose
ros2 topic hz /optitrack/TestBody/pose
```

### Options

```bash
ros2 launch optitrack_ros2 optitrack.launch.py rate:=100.0 frame_id:=map
```

| Argument | Default | Meaning |
|---|---|---|
| `rate` | `0.0` | Max messages per second per body; `0` = every Motive frame |
| `frame_id` | `world` | Parent frame of the poses and TF |
| `publish_tf` | `true` | Also broadcast TF |
| `topic_prefix` | `optitrack` | Topics are `/<prefix>/<body>/pose` |
| `server_ip` | `192.168.77.1` | Motive PC |
| `local_ip` | auto | This computer's IP on the lab network, if auto-detection picks the wrong interface |

Rigid body names are made valid for ROS: `Rigid Body 1` → `Rigid_Body_1`,
`2drone` → `rb_2drone`.

### ROS 2 on several computers

Run **one** OptiTrack node on a wired lab computer; every computer with the
same `ROS_DOMAIN_ID` sees its topics. Tested between two lab computers: the
full 180 Hz pose and TF arrive, also between **Humble and Lyrical**.

**Use your own domain ID.** ROS 2 discovery goes out on *every* network a
computer is connected to, so a computer that is also on the campus network
sees other groups' topics on the default domain 0 (and they see yours):

```bash
export ROS_DOMAIN_ID=17       # agree on a number with your group; add it to ~/.bashrc
```

**Firewall:** if `ufw` is on, it blocks ROS 2 traffic between computers.
`sudo setup/setup_network.sh` allows the lab network on the lab interface,
which covers both OptiTrack and ROS 2.

## 6. Coordinates

- **Units:** metres.
- **Axes:** the lab's Motive streams **Z up**. Poses are passed through
  unchanged, so they already match the ROS convention (Z up).
- **Origin:** the ground plane set during Motive calibration.
- **Orientation:** quaternion `(x, y, z, w)`.

## 7. Troubleshooting

Start with `setup/check_network.sh`; it shows which step fails.

| Symptom | Likely cause | Fix |
|---|---|---|
| Check step 1 fails: no `192.168.77.x` address | Not connected to the lab network, or no static IP | Plug in the cable / join the lab Wi‑Fi, then `sudo setup/setup_network.sh` |
| Step 4 fails: no reply from Motive | Motive not running or not streaming | Ask lab staff to check [Motive settings](#8-motive-settings-lab-staff) |
| **Step 4 OK but step 5 fails** (Motive answers, no frames) | Firewall blocks the data | `sudo setup/setup_network.sh` (adds the ufw rule) |
| Step 3 warns about the multicast route | Another connection (e.g. campus Wi‑Fi) gets the multicast traffic | `sudo setup/setup_network.sh`. The Python client works anyway, but other tools may not |
| Step 1 warns "Wi‑Fi power saving is on" | Ubuntu's default; makes the access point send multicast in bursts | `sudo setup/setup_network.sh` while on the lab Wi‑Fi |
| Step 5: frames lost, or a low rate | Wi‑Fi drops multicast | See [Wi-Fi users](#wi-fi-users); for control, use a cable |
| A body is missing or shows `(not tracked)`; its ROS topic is silent | Motive cannot see its markers, or the body is not set to stream | Check that the body is visible and enabled in Motive's Assets pane |
| **Orientation looks wrong** (rotated 90°, "up" points sideways) | Motive's Up Axis changed | In Motive: Settings → Streaming → **Up Axis = Z Axis** |
| ROS 2 topics from another computer don't arrive (`does not appear to be published`) | `ufw` firewall on the receiving computer | `sudo setup/setup_network.sh` (allows the lab network) |
| You see other people's topics (e.g. `/joy`, `/cf…`) | Everyone on the default `ROS_DOMAIN_ID` 0 | Set your own `ROS_DOMAIN_ID` |
| `TimeoutError` when connecting | Wrong IP, or wrong interface on a computer with several networks | Run the check; pass `local_ip` (`NatNetClient(local_ip=...)` / `local_ip:=...`) |
| `pip install -e .` fails on Ubuntu 20.04 | Old pip | `pip install --upgrade pip` inside the venv first |
| `externally-managed-environment` error from pip | Ubuntu 24.04+ blocks pip outside a venv | Use the venv steps in [Install](#install) |

## 8. Motive settings (lab staff)

On the Motive PC, **Settings → Streaming**:

| Setting | Value |
|---|---|
| Enable (NatNet) | On |
| Local Interface | `192.168.77.1` (not loopback) |
| Transmission Type | **Multicast** |
| Multicast Interface | `239.255.42.99` (default) |
| Command / Data port | `1510` / `1511` (default) |
| Rigid Bodies | On |
| Up Axis | **Z Axis** |

Only rigid bodies enabled for streaming in the Assets pane are sent.
Requires Motive 3.x (NatNet 4.1 or newer).

---

## For developers

```
src/optitrack_natnet/   Python package: protocol.py (packet decoding), client.py (sockets)
ros2/optitrack_ros2/    ROS 2 package (uses src/optitrack_natnet through a symlink)
setup/                  network setup and check scripts
examples/               plain Python examples
tests/                  unit tests on packets recorded from the lab's Motive
```

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

MIT licence, MRS – Multi-Robot Systems Lab, Technion.
