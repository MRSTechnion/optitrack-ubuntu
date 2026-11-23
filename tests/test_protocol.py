"""Decode packets recorded from the lab's Motive 3.1.0.1 (NatNet 4.1)."""

import struct
from pathlib import Path

import pytest

from optitrack_natnet import protocol as P

FIXTURES = Path(__file__).parent / "fixtures"


def payload(name):
    return P.split_header((FIXTURES / name).read_bytes())


def test_server_info():
    msg_id, data = payload("server_info.bin")
    assert msg_id == P.NAT_SERVERINFO
    info = P.parse_server_info(data)
    assert info.app_name == "Motive"
    assert info.app_version == (3, 1, 0, 1)
    assert info.version == (4, 1)


def test_model_def_names():
    msg_id, data = payload("model_def.bin")
    assert msg_id == P.NAT_MODELDEF
    assert P.parse_model_def(data, (4, 1)) == {1: "cf232"}


@pytest.mark.parametrize("i", range(5))
def test_frame(i):
    msg_id, data = payload(f"frame_{i}.bin")
    assert msg_id == P.NAT_FRAMEOFDATA
    frame = P.parse_frame(data, (4, 1), {1: "cf232"})
    assert len(frame.rigid_bodies) == 1
    rb = frame.rigid_bodies[0]
    assert rb.name == "cf232" and rb.tracking_valid
    # The drone was resting on the floor: Z-up, ~3 cm high, upright.
    assert rb.position[2] == pytest.approx(0.031, abs=0.002)
    qx, qy, qz, qw = rb.orientation
    assert qx * qx + qy * qy + qz * qz + qw * qw == pytest.approx(1.0, abs=1e-4)
    assert qw > 0.99
    assert frame.timestamp > 0


def test_consecutive_frames_at_180hz():
    frames = [P.parse_frame(payload(f"frame_{i}.bin")[1], (4, 1)) for i in range(5)]
    numbers = [f.frame_number for f in frames]
    assert numbers == list(range(numbers[0], numbers[0] + 5))
    dt = frames[1].timestamp - frames[0].timestamp
    assert dt == pytest.approx(1 / 180, rel=1e-3)


def test_unknown_id_gets_placeholder_name():
    frame = P.parse_frame(payload("frame_0.bin")[1], (4, 1), {})
    assert frame.rigid_bodies[0].name == "rigid_body_1"


def test_truncated_frame_raises():
    data = payload("frame_0.bin")[1]
    with pytest.raises(P.NatNetError):
        P.parse_frame(data[:60], (4, 1))


def test_old_natnet_rejected():
    with pytest.raises(P.NatNetError, match="need 4.1"):
        P.parse_frame(payload("frame_0.bin")[1], (3, 1))


def test_build_request():
    assert P.build_request(P.NAT_REQUEST_MODELDEF) == struct.pack("<HH", 4, 0)


def test_callback_error_does_not_stop_thread(monkeypatch):
    """A failing callback is logged once and the receive thread keeps running."""
    import logging
    import time

    from optitrack_natnet import NatNetClient
    from optitrack_natnet import client as client_module

    # Own handler instead of caplog: old pytest (6.2, Ubuntu 22.04) misses
    # records logged from background threads.
    records = []
    handler = logging.Handler()
    handler.emit = records.append
    client_module.log.addHandler(handler)

    frame = P.parse_frame(payload("frame_0.bin")[1], (4, 1))
    client = NatNetClient(server_ip="127.0.0.1", local_ip="127.0.0.1")
    monkeypatch.setattr(client, "receive", lambda: (time.sleep(0.001), frame)[1])
    calls = []

    def bad(f):
        calls.append(f)
        raise ValueError("boom")

    try:
        client.start(bad)
        time.sleep(0.1)
        client.stop()
    finally:
        client_module.log.removeHandler(handler)
    assert len(calls) > 10
    assert sum("Error in frame callback" in r.getMessage() for r in records) == 1
