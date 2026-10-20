"""Every planted mutant still applies to the current source (exactly one match), so the mutation run cannot
silently test nothing. The mutation run itself: python3 -B scripts/mutate_model.py."""
import pathlib

from mutants import MUTANTS

ROOT = pathlib.Path(__file__).parents[2]


def test_each_mutant_applies_once():
    for f, name, _rule, old, new, _killer in MUTANTS:
        src = (ROOT / f).read_text()
        assert src.count(old) == 1, name
        assert old != new, name
