from glob import glob

from setuptools import setup

package_name = "optitrack_ros2"

setup(
    name=package_name,
    version="0.1.0",
    # optitrack_natnet is a symlink to the repo's src/optitrack_natnet (one copy of the code)
    packages=[package_name, "optitrack_natnet"],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", glob("launch/*.launch.py")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="MRS Lab, Technion",
    maintainer_email="noreply@example.com",
    description="Publishes OptiTrack/Motive rigid bodies as PoseStamped and TF.",
    license="MIT",
    entry_points={
        "console_scripts": [
            "optitrack_node = optitrack_ros2.node:main",
        ],
    },
)
