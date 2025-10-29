#!/usr/bin/env python3
"""Entry point for running flex as a module.

Usage:
    python -m opt.flex --subject 101 --goal mean ...
"""

from __future__ import annotations

import sys

from .flex import main

if __name__ == "__main__":
    sys.exit(main())

