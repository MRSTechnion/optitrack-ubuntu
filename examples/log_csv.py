"""Record every frame of every rigid body to a CSV file until Ctrl+C.

    python examples/log_csv.py run1.csv
    python examples/log_csv.py run1.csv --duration 30 --body cf232

Columns: motive_time, frame, name, id, x, y, z, qx, qy, qz, qw, tracked, error
(motive_time is in seconds on Motive's clock; positions in metres, Z up.)
"""

import argparse
import csv
import time

from optitrack_natnet import NatNetClient

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("output", help="CSV file to write")
parser.add_argument("--duration", type=float, default=0, help="seconds to record (0 = until Ctrl+C)")
parser.add_argument("--body", action="append", help="only this rigid body (repeatable)")
parser.add_argument("--server-ip", default="192.168.77.1")
args = parser.parse_args()

rows = 0
with NatNetClient(args.server_ip) as client, open(args.output, "w", newline="") as f:
    missing = set(args.body or []) - set(client.names.values())
    if missing:
        raise SystemExit(f"Not streamed by Motive: {', '.join(sorted(missing))}. "
                         f"Available: {', '.join(client.names.values())}")
    writer = csv.writer(f)
    writer.writerow(["motive_time", "frame", "name", "id", "x", "y", "z",
                     "qx", "qy", "qz", "qw", "tracked", "error"])
    print(f"Recording {', '.join(args.body or client.names.values())} to {args.output} "
          "... Ctrl+C to stop")
    start = time.monotonic()
    try:
        for frame in client.frames():
            for rb in frame.rigid_bodies:
                if args.body and rb.name not in args.body:
                    continue
                writer.writerow([f"{frame.timestamp:.6f}", frame.frame_number, rb.name, rb.id,
                                 *(f"{v:.6f}" for v in rb.position),
                                 *(f"{v:.6f}" for v in rb.orientation),
                                 int(rb.tracking_valid), f"{rb.error:.6f}"])
                rows += 1
            if args.duration and time.monotonic() - start >= args.duration:
                break
    except KeyboardInterrupt:
        pass
print(f"Wrote {rows} rows to {args.output}")
