"""Shared fixtures for interwatch unit tests."""

import importlib.util
import sys
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def scan_module():
    """Import interwatch-scan.py as a module."""
    script = Path(__file__).resolve().parent.parent.parent / "scripts" / "interwatch-scan.py"
    spec = importlib.util.spec_from_file_location("interwatch_scan", str(script))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
