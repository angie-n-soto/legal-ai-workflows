import json
from datetime import date

from conftest import SAMPLE_INPUTS
from legal_workflows.efiling.renamer import (
    HIGH, LOW, MEDIUM, clean_part, date_code, rename_all, rename_document,
)

CLIENTS = [{"first_name": "Maria", "last_name": "Rivera", "claim_id": 1},
           {"first_name": "Derek", "last_name": "Johnson", "claim_id": 2}]


def doc(plaintiffs, received="2026-10-07", **caption):
    base = {"plaintiffs": plaintiffs, "defendants": ["Example Transport LLC"], "cause_number": "DC-1",
            "court": "District Court", "description": "Motion for Continuance", "legible": True}
    return {"original_filename": "x.pdf", "received": received, "caption": {**base, **caption}}


def test_date_code_is_yyyymmdd_with_leading_zeros():
    assert date_code(date(2026, 10, 8)) == "20261008"
    assert date_code(date(2026, 1, 5)) == "20260105"
    assert date_code(date(2026, 11, 1)) != date_code(date(2026, 1, 11))  # no two dates share a code


def test_clean_part_caps_and_strips_punctuation():
    assert clean_part("Plaintiff's  Original-Petition!") == "PLAINTIFFS ORIGINAL PETITION"


def test_single_known_plaintiff_is_high():
    r = rename_document(doc(["Maria Rivera"]), CLIENTS)
    assert r.confidence == HIGH
    assert r.new_filename == "20261007 RIVERA MARIA MOTION FOR CONTINUANCE"


def test_uses_received_date_not_document_date():
    assert rename_document(doc(["Maria Rivera"], received="2026-10-14"), CLIENTS).new_filename.startswith("20261014 ")


def test_multiple_plaintiffs_is_low_and_says_why():
    r = rename_document(doc(["Derek Johnson", "Tanya Johnson"]), CLIENTS)
    assert r.confidence == LOW
    assert any("Multiple plaintiffs" in reason for reason in r.reasons)


def test_last_name_only_match_is_medium():
    assert rename_document(doc(["M. Rivera"]), CLIENTS).confidence == MEDIUM


def test_unknown_plaintiff_and_illegible_caption_are_low():
    assert rename_document(doc(["Pat Stranger"]), CLIENTS).confidence == LOW
    r = rename_document(doc([], legible=False, description=""), CLIENTS)
    assert r.confidence == LOW and "UNKNOWN CLIENT" in r.new_filename


def test_sample_inbox_sorted_low_and_medium_first(client):
    docs = json.loads((SAMPLE_INPUTS / "efiling_inbox.json").read_text())["documents"]
    order = [r.confidence for r in rename_all(docs, client.list_clients())]
    assert order == sorted(order, key=[LOW, MEDIUM, HIGH].index)
    assert order.count(HIGH) == 2
