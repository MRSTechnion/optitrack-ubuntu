"""Minimal NatNet 4.1+ receiver for OptiTrack Motive rigid bodies."""

from .client import DEFAULT_SERVER_IP, NatNetClient, local_ip_for
from .protocol import Frame, NatNetError, RigidBody, ServerInfo

__all__ = [
    "DEFAULT_SERVER_IP",
    "Frame",
    "NatNetClient",
    "NatNetError",
    "RigidBody",
    "ServerInfo",
    "local_ip_for",
]
__version__ = "0.1.0"
