"""Decoding of NatNet packets: rigid bodies only.

Pure functions over ``bytes``, with no sockets, so they can be tested against
recorded packets. Written for NatNet 4.1 (Motive 3.x). That version puts a byte
count after every section count, so sections we do not use are skipped
without decoding them.

Packet layout reference: the NatNet SDK sample ``NatNetClient.py``
(Apache-2.0, NaturalPoint).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Tuple

# Message IDs (first uint16 of every packet)
NAT_CONNECT = 0
NAT_SERVERINFO = 1
NAT_REQUEST_MODELDEF = 4
NAT_MODELDEF = 5
NAT_FRAMEOFDATA = 7
NAT_KEEPALIVE = 10

# Description types in a NAT_MODELDEF packet
_DESC_RIGID_BODY = 1

_HEADER = struct.Struct("<HH")  # message id, payload size
_RIGID_BODY = struct.Struct("<i3f4ffh")  # id, x y z, qx qy qz qw, error, params
_SUFFIX = struct.Struct("<IIdQQQIIh")  # timecode, sub, timestamp, 3 stamps, prec s, frac, params

Version = Tuple[int, int]


class NatNetError(ValueError):
    """A packet could not be decoded."""


@dataclass
class ServerInfo:
    app_name: str
    app_version: tuple[int, int, int, int]
    natnet_version: tuple[int, int, int, int]

    @property
    def version(self) -> Version:
        return self.natnet_version[0], self.natnet_version[1]


@dataclass
class RigidBody:
    id: int
    name: str
    position: tuple[float, float, float]  # metres, Motive frame (lab: Z-up)
    orientation: tuple[float, float, float, float]  # quaternion qx, qy, qz, qw
    tracking_valid: bool
    error: float  # mean marker error, metres


@dataclass
class Frame:
    frame_number: int
    timestamp: float | None  # seconds since Motive started streaming
    rigid_bodies: list[RigidBody] = field(default_factory=list)
    models_changed: bool = False  # Motive asks clients to re-request names


def split_header(packet: bytes) -> tuple[int, memoryview]:
    """Return ``(message_id, payload)``."""
    if len(packet) < _HEADER.size:
        raise NatNetError("packet shorter than its header")
    msg_id, size = _HEADER.unpack_from(packet)
    return msg_id, memoryview(packet)[_HEADER.size:_HEADER.size + size]


def build_request(msg_id: int, payload: bytes = b"") -> bytes:
    return _HEADER.pack(msg_id, len(payload)) + payload


def parse_server_info(payload: bytes) -> ServerInfo:
    payload = bytes(payload)
    name = payload[:256].split(b"\0", 1)[0].decode("utf-8", "replace")
    app = tuple(payload[256:260])
    natnet = tuple(payload[260:264])
    return ServerInfo(name, app, natnet)  # type: ignore[arg-type]


def _cstring(buf: memoryview, offset: int) -> tuple[str, int]:
    raw = bytes(buf[offset:])
    end = raw.find(b"\0")
    if end < 0:
        raise NatNetError("unterminated string")
    return raw[:end].decode("utf-8", "replace"), offset + end + 1


def parse_model_def(payload: bytes, version: Version) -> dict[int, str]:
    """Return ``{rigid body id: name}`` from a NAT_MODELDEF payload."""
    if version < (4, 1):
        raise NatNetError(f"NatNet {version[0]}.{version[1]} is not supported (need 4.1+)")
    buf = memoryview(payload)
    (count,) = struct.unpack_from("<i", buf, 0)
    offset = 4
    names: dict[int, str] = {}
    for _ in range(count):
        desc_type, size = struct.unpack_from("<ii", buf, offset)
        offset += 8
        if desc_type == _DESC_RIGID_BODY:
            name, after_name = _cstring(buf, offset)
            (rb_id,) = struct.unpack_from("<i", buf, after_name)
            names[rb_id] = name
        offset += size
    return names


def _skip_section(buf: memoryview, offset: int) -> int:
    """Skip a 4.1 frame section: ``count, byte_size, data``."""
    _count, size = struct.unpack_from("<ii", buf, offset)
    return offset + 8 + size


def parse_frame(payload: bytes, version: Version,
                names: dict[int, str] | None = None) -> Frame:
    """Decode a NAT_FRAMEOFDATA payload.

    ``names`` maps rigid body ids to names (from :func:`parse_model_def`).
    A body with an unknown id is named ``rigid_body_<id>``.
    """
    if version < (4, 1):
        raise NatNetError(f"NatNet {version[0]}.{version[1]} is not supported (need 4.1+)")
    names = names or {}
    buf = memoryview(payload)
    try:
        (frame_number,) = struct.unpack_from("<i", buf, 0)
        offset = _skip_section(buf, 4)  # marker sets
        offset = _skip_section(buf, offset)  # legacy "other" markers

        rb_count, _size = struct.unpack_from("<ii", buf, offset)
        offset += 8
        bodies = []
        for _ in range(rb_count):
            rb_id, x, y, z, qx, qy, qz, qw, err, params = _RIGID_BODY.unpack_from(buf, offset)
            offset += _RIGID_BODY.size
            bodies.append(RigidBody(
                id=rb_id,
                name=names.get(rb_id, f"rigid_body_{rb_id}"),
                position=(x, y, z),
                orientation=(qx, qy, qz, qw),
                tracking_valid=bool(params & 0x01),
                error=err,
            ))

        # skeletons, assets, labeled markers, force plates, devices
        for _ in range(5):
            offset = _skip_section(buf, offset)

        suffix = _SUFFIX.unpack_from(buf, offset)  # followed by a 4-byte end-of-data tag
    except struct.error as exc:
        raise NatNetError(f"truncated frame: {exc}") from exc

    timestamp, params = suffix[2], suffix[8]
    return Frame(frame_number, timestamp, bodies, models_changed=bool(params & 0x02))
