"""Pytest configuration and common fixtures.

This module contains pytest configuration and common fixtures used across
test modules. It also ensures the src package is in the Python path.
"""

import os
import sys
from pathlib import Path

# Add the project root directory to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Configure pytest-asyncio
def pytest_configure(config):
    """Configure pytest-asyncio to use function scope for event loops."""
    config.option.asyncio_mode = "strict"
    config.option.asyncio_default_fixture_loop_scope = "function" 