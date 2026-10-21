"""Shared test configuration."""

import os

import pytest


def pytest_collection_modifyitems(config, items):
    """Skip the ``live`` tests unless ``ANDROID_MCP_LIVE=1``: they drive a real device."""
    if os.environ.get("ANDROID_MCP_LIVE") == "1":
        return
    skip = pytest.mark.skip(reason="drives a device; set ANDROID_MCP_LIVE=1 to run")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)
