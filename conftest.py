"""Ensure the project root is importable so `import config` and `src.*` resolve."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
