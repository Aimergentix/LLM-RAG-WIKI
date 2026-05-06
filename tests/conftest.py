"""Pytest bootstrap.

Adds ``src/`` to ``sys.path`` so test modules can import the layer
packages (``rag``, ``wiki``, ``persona_mcp``) without per-file shims.
The same path is also declared in ``pyproject.toml``
(``[tool.pytest.ini_options] pythonpath``); this conftest keeps tests
runnable when invoked outside pytest (e.g. ``python tests/test_x.py``).
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
