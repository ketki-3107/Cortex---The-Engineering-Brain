"""
Pytest configuration for CORTEX integration tests.

These tests call live Anthropic and GitLab APIs.  They are intended for
local development only and are automatically skipped in CI environments
where ANTHROPIC_API_KEY is not set.
"""

import os
import pytest


def pytest_collection_modifyitems(items):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        skip = pytest.mark.skip(
            reason="integration test — requires ANTHROPIC_API_KEY (run locally)"
        )
        for item in items:
            item.add_marker(skip)
