"""ROS 2 node: OptiTrack rigid bodies -> PoseStamped topics + TF.

    ros2 run optitrack_ros2 optitrack_node
    ros2 launch optitrack_ros2 optitrack.launch.py

For each rigid body streamed by Motive it publishes
``/<topic_prefix>/<name>/pose`` (geometry_msgs/PoseStamped) and, if
``publish_tf`` is true, the transform ``<frame_id> -> <name>``.
Poses are in Motive's frame, passed through unchanged (lab: Z up, metres).
"""

from __future__ import annotations

import re
import time

import rclpy
from geometry_msgs.msg import PoseStamped, TransformStamped
from rclpy._rclpy_pybind11 import RCLError
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from tf2_ros import TransformBroadcaster

from optitrack_natnet import DEFAULT_SERVER_IP, Frame, NatNetClient


def ros_name(name: str) -> str:
    """Make a Motive rigid body name valid as a ROS topic / TF frame name.

    'Rigid Body 1' -> 'Rigid_Body_1', '2drone' -> 'rb_2drone'.
    """
    clean = re.sub(r"[^A-Za-z0-9_]", "_", name.strip()) or "unnamed"
    return clean if clean[0].isalpha() else "rb_" + clean


class OptiTrackNode(Node):
    def __init__(self):
        super().__init__("optitrack")
        self.declare_parameter("server_ip", DEFAULT_SERVER_IP)
        self.declare_parameter("local_ip", "")  # "" = auto (interface routing to server_ip)
        self.declare_parameter("frame_id", "world")
        self.declare_parameter("topic_prefix", "optitrack")
        self.declare_parameter("publish_tf", True)
        self.declare_parameter("rate", 0.0)  # max Hz per body; 0 = every Motive frame
        self.declare_parameter("bodies", [""])  # only these Motive names; [""] = all

        p = self.get_parameter
        self.frame_id = p("frame_id").value
        self.prefix = p("topic_prefix").value.strip("/")
        self.publish_tf = p("publish_tf").value
        rate = p("rate").value
        self.min_period = 1.0 / rate if rate > 0 else 0.0
        self.only = {b for b in p("bodies").value if b}

        self._pubs = {}
        self._next_pub = {}  # name -> monotonic time of next publish (rate limit)
        self._tracked = {}  # name -> last tracking state, to log changes only
        self._tf = TransformBroadcaster(self) if self.publish_tf else None

        self.client = NatNetClient(p("server_ip").value, p("local_ip").value or None)
        self.client.connect()
        info = self.client.server_info
        self.get_logger().info(
            f"Connected to {info.app_name} {'.'.join(map(str, info.app_version))} at "
            f"{self.client.server_ip} (local {self.client.local_ip}); "
            f"rigid bodies: {', '.join(self.client.names.values()) or 'none'}")
        missing = self.only - set(self.client.names.values())
        if missing:
            self.get_logger().warning(f"Not streamed by Motive (yet): {', '.join(sorted(missing))}")

        # Publishers must be created on the ROS thread: create_publisher() from the
        # NatNet thread deadlocks against a spinning executor. A timer picks up
        # bodies added in Motive later; the client refreshes the names itself.
        self._sync_publishers()
        self.create_timer(1.0, self._sync_publishers)
        self.client.start(self._on_frame)

    def _sync_publishers(self) -> None:
        for name in list(self.client.names.values()):
            if name in self._pubs or (self.only and name not in self.only):
                continue
            topic = f"/{self.prefix}/{ros_name(name)}/pose" if self.prefix \
                else f"/{ros_name(name)}/pose"
            self._pubs[name] = self.create_publisher(PoseStamped, topic, 10)
            self.get_logger().info(f"Publishing {name} on {topic}")

    def _on_frame(self, frame: Frame) -> None:
        stamp = self.get_clock().now().to_msg()
        now = time.monotonic()
        transforms = []
        for rb in frame.rigid_bodies:
            pub = self._pubs.get(rb.name)
            if pub is None:  # filtered out, or new and not set up yet (within 1 s)
                continue
            # Lost by Motive (markers hidden / out of view): publish nothing rather
            # than a stale pose, and say so once per loss so an empty topic is explained.
            if rb.tracking_valid != self._tracked.get(rb.name):
                self._tracked[rb.name] = rb.tracking_valid
                if rb.tracking_valid:
                    self.get_logger().info(f"{rb.name}: tracked, publishing")
                else:
                    self.get_logger().warning(
                        f"{rb.name}: not tracked by Motive (markers not visible?); "
                        "not publishing until it is tracked again")
            if not rb.tracking_valid:
                continue
            if self.min_period:
                # Fixed schedule (not "period since last"), so e.g. 50 Hz from
                # 180 Hz Motive frames averages 50 Hz instead of rounding down.
                due = self._next_pub.get(rb.name, 0.0)
                if now < due:
                    continue
                nxt = due + self.min_period
                # first publish, or behind schedule (e.g. after tracking loss): restart
                self._next_pub[rb.name] = nxt if nxt > now else now + self.min_period

            msg = PoseStamped()
            msg.header.stamp = stamp
            msg.header.frame_id = self.frame_id
            pos, q = msg.pose.position, msg.pose.orientation
            pos.x, pos.y, pos.z = rb.position
            q.x, q.y, q.z, q.w = rb.orientation
            pub.publish(msg)

            if self._tf is not None:
                t = TransformStamped()
                t.header = msg.header
                t.child_frame_id = ros_name(rb.name)
                tr = t.transform.translation
                tr.x, tr.y, tr.z = rb.position
                t.transform.rotation = msg.pose.orientation
                transforms.append(t)
        if transforms:
            self._tf.sendTransform(transforms)

    def destroy_node(self):
        self.client.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    try:
        node = OptiTrackNode()
    except TimeoutError as exc:
        print(f"Error: {exc}")
        rclpy.try_shutdown()
        raise SystemExit(1) from None
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    except RCLError:
        # Ctrl+C shuts the context down; on some distros (seen on Lyrical) spin()
        # then raises RCLError instead of ExternalShutdownException.
        if rclpy.ok():
            raise
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
