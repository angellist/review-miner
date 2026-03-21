"""Entry point for `python -m bot`."""

import sys
from pathlib import Path

# Ensure scripts/ is importable before any bot modules load
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from bot.review import main

main()
