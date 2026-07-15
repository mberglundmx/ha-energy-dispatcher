"""Test configuration."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

for module_name in (
    "homeassistant",
    "homeassistant.config_entries",
    "homeassistant.core",
):
    if module_name not in sys.modules:
        sys.modules[module_name] = MagicMock()
