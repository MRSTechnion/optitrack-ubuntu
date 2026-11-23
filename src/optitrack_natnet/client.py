"""Receive rigid bodies from Motive over NatNet multicast.

Example::

    from optitrack_natnet import NatNetClient

    with NatNetClient() as client:
        for frame in client.frames():
            for rb in frame.rigid_bodies:
                print(rb.name, rb.position)
"""

from __future__ import annotations

import logging
import socket
import threading
import time
from typing import Callable, Iterator

from . import protocol as P

log = logging.getLogger(__name__)

# MRS lab defaults (Motive: Settings -> Streaming)
DEFAULT_SERVER_IP = "192.168.77.1"
DEFAULT_MULTICAST_GROUP = "239.255.42.99"
DEFAULT_COMMAND_PORT = 1510
DEFAULT_DATA_PORT = 1511


def local_ip_for(server_ip: str) -> str:
    """Return this machine's IP on the interface that routes to ``server_ip``.

    Opening a UDP socket toward the server sends no packets; it only asks the
    kernel which local address it would use.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect((server_ip, DEFAULT_COMMAND_PORT))
        return s.getsockname()[0]


class NatNetClient:
    """Connects to Motive and yields :class:`~optitrack_natnet.protocol.Frame` objects.

    Args:
        server_ip: Motive PC address.
        local_ip: this machine's address on the Motive network. By default it
            is found from the route to ``server_ip``. Set it when the machine
            has several network interfaces and the guess is wrong.
        multicast: True (default) for Motive's Multicast transmission type;
            False for Unicast, where Motive streams to the socket that sent it
            the connect request, as long as it sends keep-alives (once per second).
        multicast_group, command_port, data_port: must match Motive's
            streaming settings (the defaults are Motive's defaults).
        timeout: seconds to wait for Motive before raising ``TimeoutError``.
    """

    def __init__(
        self,
        server_ip: str = DEFAULT_SERVER_IP,
        local_ip: str | None = None,
        multicast_group: str = DEFAULT_MULTICAST_GROUP,
        command_port: int = DEFAULT_COMMAND_PORT,
        data_port: int = DEFAULT_DATA_PORT,
        timeout: float = 2.0,
        multicast: bool = True,
    ):
        self.server_ip = server_ip
        self.local_ip = local_ip or local_ip_for(server_ip)
        self.multicast_group = multicast_group
        self.command_port = command_port
        self.data_port = data_port
        self.timeout = timeout
        self.multicast = multicast

        self.server_info: P.ServerInfo | None = None
        self.names: dict[int, str] = {}
        self._cmd: socket.socket | None = None
        self._data: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._last_keepalive = 0.0

    # -- connection -------------------------------------------------------

    def connect(self) -> NatNetClient:
        """Open sockets, ask Motive for its version and the rigid body names."""
        self._cmd = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._cmd.bind((self.local_ip, 0))
        self._cmd.settimeout(self.timeout)
        if not self.multicast:
            # Unicast: Motive streams frames to the socket that sends the connect
            # request (one copy per such socket), so a single socket does
            # commands, keep-alives and frames.
            self._data = self._cmd

        payload = self._request(P.NAT_CONNECT, P.NAT_SERVERINFO, b"Ping\0")
        self.server_info = P.parse_server_info(payload)
        log.info("Connected to %s %s, NatNet %s", self.server_info.app_name,
                 ".".join(map(str, self.server_info.app_version)),
                 ".".join(map(str, self.server_info.natnet_version)))
        self.refresh_names()

        if self.multicast:
            self._data = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            self._data.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._data.bind(("", self.data_port))
            # Join the group on the Motive-side interface explicitly, so it works
            # even when another interface (e.g. Wi-Fi) holds the default route.
            mreq = socket.inet_aton(self.multicast_group) + socket.inet_aton(self.local_ip)
            self._data.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            self._data.settimeout(self.timeout)
        else:
            self._send_keepalive()
        return self

    def _send_keepalive(self) -> None:
        assert self._data is not None
        self._data.sendto(P.build_request(P.NAT_KEEPALIVE), (self.server_ip, self.command_port))
        self._last_keepalive = time.monotonic()

    def _send_unicast_connect(self) -> None:
        # Its NAT_SERVERINFO reply arrives with the frames and is skipped.
        assert self._data is not None
        self._data.sendto(P.build_request(P.NAT_CONNECT, b"Ping\0"),
                          (self.server_ip, self.command_port))
        self._last_keepalive = time.monotonic()

    def _unicast_keepalive(self) -> None:
        # Motive drops a unicast client ~10 s after its last keep-alive, and a
        # keep-alive does not restart it; only a new connect does. So after a
        # long pause (e.g. a breakpoint) connect again instead.
        idle = time.monotonic() - self._last_keepalive
        if idle > 5.0:
            self._send_unicast_connect()
        elif idle > 1.0:
            self._send_keepalive()

    def close(self) -> None:
        self.stop()
        if not self.multicast and self._cmd is not None:
            try:  # tell Motive to stop streaming to us
                self._cmd.sendto(P.build_request(P.NAT_DISCONNECT),
                                 (self.server_ip, self.command_port))
            except OSError:
                pass
        for s in {self._data, self._cmd} - {None}:
            s.close()
        self._data = self._cmd = None

    def __enter__(self) -> NatNetClient:  # noqa: PYI034  (stdlib only, no typing_extensions)
        return self.connect()

    def __exit__(self, *exc) -> None:
        self.close()

    def _request(self, msg_id: int, reply_id: int, payload: bytes = b"") -> memoryview:
        """Send a command and return the payload of its reply.

        Other packets on the command socket (e.g. frames, which Motive may also
        send there in unicast mode) are skipped.
        """
        assert self._cmd is not None, "call connect() first"
        self._cmd.sendto(P.build_request(msg_id, payload), (self.server_ip, self.command_port))
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                packet, _ = self._cmd.recvfrom(65535)
            except socket.timeout:
                packet = None
            if packet is not None:
                got_id, reply = P.split_header(packet)
                if got_id == reply_id:
                    return reply
            if packet is None or time.monotonic() > deadline:
                raise TimeoutError(
                    f"No reply from Motive at {self.server_ip}:{self.command_port} "
                    f"(local IP {self.local_ip}). Is Motive streaming? "
                    f"Run setup/check_network.sh")

    def refresh_names(self) -> dict[int, str]:
        """Ask Motive for the current rigid body names."""
        assert self.server_info is not None
        payload = self._request(P.NAT_REQUEST_MODELDEF, P.NAT_MODELDEF)
        self.names = P.parse_model_def(payload, self.server_info.version)
        log.info("Rigid bodies: %s", self.names)
        return self.names

    # -- receiving --------------------------------------------------------

    def receive(self) -> P.Frame:
        """Block until the next frame arrives and return it."""
        if self._data is None or self.server_info is None:
            raise RuntimeError("call connect() first")
        retried = False
        while True:
            if not self.multicast:
                self._unicast_keepalive()
            try:
                packet, _ = self._data.recvfrom(65535)
            except socket.timeout:
                if not self.multicast and not retried:
                    retried = True  # the registration may have expired: connect again
                    self._send_unicast_connect()
                    continue
                where = (f"{self.multicast_group}:{self.data_port}" if self.multicast
                         else f"unicast from {self.server_ip}")
                raise TimeoutError(
                    f"No frames ({where}, local IP {self.local_ip}). Does Motive's "
                    f"Transmission Type match ({'Multicast' if self.multicast else 'Unicast'})? "
                    f"Run setup/check_network.sh") from None
            msg_id, payload = P.split_header(packet)
            if msg_id != P.NAT_FRAMEOFDATA:
                continue
            frame = P.parse_frame(payload, self.server_info.version, self.names)
            unknown = any(rb.id not in self.names for rb in frame.rigid_bodies)
            if frame.models_changed or unknown:
                self.refresh_names()
                frame = P.parse_frame(payload, self.server_info.version, self.names)
            return frame

    def frames(self) -> Iterator[P.Frame]:
        """Yield frames forever (stop with Ctrl+C or ``break``)."""
        while True:
            yield self.receive()

    def start(self, callback: Callable[[P.Frame], None]) -> None:
        """Call ``callback(frame)`` for every frame, from a background thread.

        An exception in ``callback`` is logged (once per distinct error) and
        receiving continues, so one bad frame does not stop the stream.
        """
        self._stop.clear()

        def loop():
            reported = set()
            while not self._stop.is_set():
                try:
                    frame = self.receive()
                except TimeoutError as exc:
                    log.warning("%s", exc)
                    continue
                except OSError:
                    if self._stop.is_set():  # socket closed by close()
                        return
                    raise
                try:
                    callback(frame)
                except Exception as exc:
                    key = (type(exc), str(exc))
                    if key not in reported:
                        reported.add(key)
                        log.exception("Error in frame callback (receiving continues)")

        self._thread = threading.Thread(target=loop, name="natnet", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=self.timeout + 1)
        self._thread = None
