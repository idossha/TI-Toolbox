#!/usr/bin/env simnibs_python
"""Entry point for running flex as a module.

Usage:
    python -m tit.opt.flex --subject 101 --goal mean ...
"""

from __future__ import annotations

import sys

from .flex import main

if __name__ == "__main__":
    sys.exit(main())
