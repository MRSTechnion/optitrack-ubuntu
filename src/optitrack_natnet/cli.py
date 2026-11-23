"""``optitrack-print``: print live rigid body poses."""

from __future__ import annotations

import argparse
import logging
import time

from .client import DEFAULT_SERVER_IP, NatNetClient


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Print OptiTrack rigid body poses.")
    parser.add_argument("--server-ip", default=DEFAULT_SERVER_IP, help="Motive PC address")
    parser.add_argument("--local-ip", default=None,
                        help="this machine's IP on the Motive network (default: auto)")
    parser.add_argument("--rate", type=float, default=10.0,
                        help="lines printed per second (default 10; Motive may stream faster)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    period = 1.0 / args.rate if args.rate > 0 else 0.0
    last = 0.0
    try:
        with NatNetClient(args.server_ip, args.local_ip) as client:
            for frame in client.frames():
                now = time.monotonic()
                if now - last < period:
                    continue
                last = now
                for rb in frame.rigid_bodies:
                    x, y, z = rb.position
                    qx, qy, qz, qw = rb.orientation
                    flag = "" if rb.tracking_valid else "  (not tracked)"
                    print(f"{frame.frame_number:>9}  {rb.name:<16} "
                          f"pos=({x:+.3f}, {y:+.3f}, {z:+.3f})  "
                          f"quat=({qx:+.3f}, {qy:+.3f}, {qz:+.3f}, {qw:+.3f}){flag}", flush=True)
    except KeyboardInterrupt:
        pass
    except TimeoutError as exc:
        raise SystemExit(f"Error: {exc}") from None


if __name__ == "__main__":
    main()
