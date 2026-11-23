# Let the tests import optitrack_natnet from src/ without installing it
# (works with old pytest too, e.g. 6.2 on Ubuntu 22.04).
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
