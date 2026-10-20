"""Independence rule: oracles never import from spec/ or spex/. The scanner's own planted bug is the synthetic source below."""
import pathlib
import re

FORBIDDEN = re.compile(r"^\s*(from|import)\s+(spec|spex)\b", re.M)


def offending(src: str) -> bool:
    return bool(FORBIDDEN.search(src))


def test_scanner_catches_planted_import():
    assert offending("import os\nfrom spex.refsim import Spex\n")
    assert offending("    import spec.uart_8n1\n")
    assert not offending("import uart\n# spex is mentioned in a comment\n")


def test_oracles_do_not_import_spec_or_spex():
    here = pathlib.Path(__file__).parent
    bad = [p.name for p in here.glob("*.py") if p.name != "test_independence.py" and offending(p.read_text())]
    assert bad == []
