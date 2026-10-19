"""Every planted mutant still applies to the current model source (exactly one match), so the mutation run cannot
silently test nothing. The mutation run itself: python3 -B scripts/mutate_model.py."""
import pathlib

from mutants import MUTANTS

SRC = (pathlib.Path(__file__).parents[2] / "spex" / "refsim" / "model.py").read_text()


def test_each_mutant_applies_once():
    for name, _rule, old, new, _killer in MUTANTS:
        assert SRC.count(old) == 1, name
        assert old != new, name
