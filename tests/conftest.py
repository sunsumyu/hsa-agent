"""
tests/conftest.py
=================
Global pytest fixtures and test environment bootstrap.
Ensures ServiceProvider has default service definitions available for all test suites.
"""

import pytest
from app.core.bootstrap import register_services


@pytest.fixture(scope="session", autouse=True)
def setup_test_di():
    """Ensure DI container has services registered for all tests."""
    register_services()
