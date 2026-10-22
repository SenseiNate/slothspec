"""Regression tests. No model, no network, runs in about a second.

    python -m pytest tests          (if you have pytest)
    python tests/test_regression.py (if you don't)

If one fails after a change, either the change broke something or the
expected output needs updating on purpose. Never update the expected
file just to make a test pass without knowing why it changed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from slothspec.extract import extract  # noqa: E402
from slothspec.llm import clean_rewrite  # noqa: E402
from slothspec.rules import check  # noqa: E402

SAMPLE = ROOT / "examples" / "sample_spec.txt"
EXPECTED = Path(__file__).parent / "expected_sample_spec.json"


def test_sample_spec_extraction_and_rules_unchanged():
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
    got = [{"id": r.rid, "text": r.text, "rules": [[f.rule, f.match] for f in check(r.text)]}
           for r in extract(SAMPLE)]
    assert [g["id"] for g in got] == [e["id"] for e in expected], "requirement IDs changed"
    for g, e in zip(got, expected):
        assert g == e, f"{g['id']} changed:\n  expected {e}\n  got      {g}"


def test_verbs_filter():
    assert len(extract(SAMPLE)) == 20
    shall_only = extract(SAMPLE, ("shall",))
    assert len(shall_only) == 18  # SPF-004 (should) and SPF-011 (will) drop out
    assert {r.rid for r in shall_only}.isdisjoint({"SPF-004", "SPF-011"})


NUMBER_CASES = {
    # (text, should a unitless number be flagged?)
    "a drop of 1 onto a hard floor": True,
    "a load of 1,000 onto the frame": True,
    "store 72 hours of food": False,
    "a portion between 20 and 200 grams": False,
    "a minimum of 3 portions": False,
    "the criteria in Table 1": False,
    "the methodology in (see 6)": False,
    "as defined by NFPA 70, Article 500": False,
    "a criticality 1, 1S, 1R, or 2 condition": False,
    "used in Zones 3 or 4": False,
    "per MIL-HDBK-17, Volumes 1 through 5": False,
    "in accordance with SAE AMS 2759/9": False,
    "levels above 1,240 MPa (180 ksi)": False,
    "a factor of safety of 2 against yield": False,
    "comply with 29 CFR 1910": False,
}


def test_number_without_unit_rule():
    wrong = []
    for text, should_flag in NUMBER_CASES.items():
        flagged = any(f.rule == "number without unit" for f in check(f"X shall {text}."))
        if flagged != should_flag:
            wrong.append(f"{'missed' if should_flag else 'false alarm'}: {text}")
    assert not wrong, "\n".join(wrong)


def test_passive_only_when_actor_missing():
    assert any(f.rule == "passive voice" for f in check("Firmware updates shall be applied."))
    assert any(f.rule == "passive voice" for f in check("An FMEA shall be performed on all systems."))
    assert not any(f.rule == "passive voice" for f in check("GS shall be designed in accordance with KSC-STD-1."))
    assert not any(f.rule == "passive voice" for f in check("Updates shall be applied by the operator."))


def test_clean_rewrite_strips_leaked_fields():
    leaked = "The SPF shall store <<number>> days of food. (Test)\nhow_to_verify: Inspect the docs."
    assert clean_rewrite(leaked) == "The SPF shall store <<number>> days of food."
    assert clean_rewrite("The unit shall pass the (Test) defined in <<proc>>.") == "The unit shall pass the (Test) defined in <<proc>>."


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {t.__name__}\n{e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
