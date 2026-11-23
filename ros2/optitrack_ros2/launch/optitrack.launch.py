"""Start the OptiTrack node.

    ros2 launch optitrack_ros2 optitrack.launch.py
    ros2 launch optitrack_ros2 optitrack.launch.py rate:=100.0 frame_id:=map
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

ARGS = {
    "server_ip": ("192.168.77.1", str, "Motive PC address"),
    "local_ip": ("", str, "this machine's IP on the Motive network ('' = auto)"),
    "frame_id": ("world", str, "parent frame of the poses and TF"),
    "topic_prefix": ("optitrack", str, "topics are /<prefix>/<body>/pose"),
    "publish_tf": ("true", bool, "also broadcast TF frame_id -> body"),
    "rate": ("0.0", float, "max Hz per body (0 = every Motive frame)"),
}


def generate_launch_description():
    return LaunchDescription([
        *(DeclareLaunchArgument(name, default_value=default, description=desc)
          for name, (default, _, desc) in ARGS.items()),
        Node(
            package="optitrack_ros2",
            executable="optitrack_node",
            name="optitrack",
            output="screen",
            parameters=[{name: ParameterValue(LaunchConfiguration(name), value_type=typ)
                         for name, (_, typ, _) in ARGS.items()}],
        ),
    ])
