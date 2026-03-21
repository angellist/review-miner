"""Shared fixtures for al-pr-review tests."""

import sys
from pathlib import Path

import pytest

# Add scripts/ to sys.path so tests can import the modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


@pytest.fixture(autouse=True)
def reset_config_cache():
    """Reset the cached config between tests."""
    import utils
    utils._config = None
    yield
    utils._config = None
