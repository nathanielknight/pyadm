import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import harness  # noqa: E402


def pytest_addoption(parser):
    parser.addoption(
        "--update-snapshots",
        action="store_true",
        help="re-record tests/snapshots from real yadm instead of verifying them",
    )


@pytest.fixture(scope="session")
def yadm():
    tool = harness.find_yadm()
    if tool is None:
        if os.environ.get("PYADM_REQUIRE_YADM"):
            pytest.fail("yadm is required (PYADM_REQUIRE_YADM) but is not available")
        pytest.skip("real yadm is not available here (needs bash, and network or YADM_BIN)")
    return tool
