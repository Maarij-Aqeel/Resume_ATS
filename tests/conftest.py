import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("OPENROUTER_API_KEY", "test-key-for-unit-tests")


def pytest_addoption(parser):
    parser.addoption(
        "--benchmark",
        action="store_true",
        default=False,
        help="run accuracy benchmark tests (requires fixtures)",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--benchmark"):
        return
    import pytest
    skip = pytest.mark.skip(reason="need --benchmark to run")
    for item in items:
        if "benchmark" in item.keywords:
            item.add_marker(skip)
