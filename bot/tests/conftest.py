"""Make ``bot/bot.py`` importable as the top-level ``bot`` module.

The bot/ directory is a sibling project to src/, not a package — pytest
needs the path entry to discover bot.py without a setup.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

_BOT_DIR = Path(__file__).resolve().parents[1]
if str(_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(_BOT_DIR))
