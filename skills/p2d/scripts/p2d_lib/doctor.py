from __future__ import annotations

import argparse
import platform
import sys
from typing import Callable, List

HINT = "python3 -m pip install --user pillow numpy"


def cmd_doctor(_: argparse.Namespace) -> int:
    reasons: List[str] = []
    print("PYTHON: %s" % platform.python_version())
    if sys.version_info < (3, 9):
        reasons.append("python 3.9+ required")
    try:
        import PIL

        print("PILLOW: %s" % PIL.__version__)
    except ImportError:
        reasons.append("Pillow missing: " + HINT)
    try:
        import numpy

        print("NUMPY: %s" % numpy.__version__)
    except ImportError:
        reasons.append("numpy missing: " + HINT)
    for reason in reasons:
        print("FAIL_REASON: %s" % reason)
    print("RESULT: %s" % ("FAIL" if reasons else "PASS"))
    return 1 if reasons else 0


def configure(name: str, parser: argparse.ArgumentParser) -> Callable[[argparse.Namespace], int]:
    return cmd_doctor
