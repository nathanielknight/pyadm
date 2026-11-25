"""Compare pyadm with real yadm via recorded snapshots. See harness.py."""

import pytest

import harness
from scenarios import SCENARIOS

names = pytest.mark.parametrize("name", sorted(SCENARIOS))


@names
def test_snapshot_matches_yadm(name, yadm, tmp_path, request):
    """The committed snapshots are what real yadm does (or re-record them)."""
    record = harness.play(SCENARIOS[name], yadm, tmp_path)
    if request.config.getoption("--update-snapshots"):
        harness.save_snapshot(name, record)
    assert record == harness.load_snapshot(name)


@names
def test_pyadm_matches_snapshot(name, tmp_path):
    """pyadm behaves as yadm did when the snapshot was recorded."""
    record = harness.play(SCENARIOS[name], harness.PYADM, tmp_path)
    expected = harness.load_snapshot(name)
    assert harness.comparable(record) == harness.comparable(expected)
