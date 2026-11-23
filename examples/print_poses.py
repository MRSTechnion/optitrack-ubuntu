"""Print the pose of every rigid body, 10 times per second.

    python examples/print_poses.py

The smallest useful program: copy it as a starting point for your own code.
"""

import time

from optitrack_natnet import NatNetClient

with NatNetClient() as client:  # Motive at 192.168.77.1 by default
    last = 0.0
    for frame in client.frames():  # one frame per Motive frame (e.g. 180 per second)
        if time.monotonic() - last < 0.1:
            continue
        last = time.monotonic()
        for rb in frame.rigid_bodies:
            x, y, z = rb.position  # metres, Z up
            qx, qy, qz, qw = rb.orientation
            print(f"{rb.name}: x={x:.3f} y={y:.3f} z={z:.3f}  "
                  f"q=({qx:.3f}, {qy:.3f}, {qz:.3f}, {qw:.3f})  tracked={rb.tracking_valid}")
