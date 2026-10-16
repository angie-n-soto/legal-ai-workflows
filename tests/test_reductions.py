import json
import shutil
from datetime import date
from decimal import Decimal

import pytest
from docx import Document

from conftest import SAMPLE_INPUTS
from legal_workflows.reductions.letters import (
    LOAN, PROVIDER, NeedsInputError, draft_letters, output_filename, plan_letter,
)

AS_OF = date(2026, 10, 16)


@pytest.fixture
def case(client):
    return client.get_claim(10001), {c["contact_id"]: c for c in client.get_claim_contacts(10001)}, client.get_ledger(10001)


def test_percentage_reduction_math(case):
    claim, contacts, ledger = case
    letter = plan_letter(claim, contacts[50012], ledger, {"ledger_id": 7002, "reduction_percent": 85}, AS_OF, "[Attorney Name]")
    assert letter.kind == PROVIDER
    assert letter.payoff == Decimal("315.08")  # 15% of 2,100.50, rounded to cents


def test_duplicate_ledger_entries_need_the_user_to_choose(case):
    claim, contacts, ledger = case
    with pytest.raises(NeedsInputError, match="2 ledger entries"):
        plan_letter(claim, contacts[50012], ledger, {"reduction_percent": 33}, AS_OF, "[Attorney Name]")


def test_entered_reduction_used_only_when_marked(case):
    claim, contacts, ledger = case
    letter = plan_letter(claim, contacts[50013], ledger, {"use_ledger_current_due": True}, AS_OF, "X")
    assert letter.payoff == Decimal("2400.00") and letter.reduction_percent == Decimal("33.33")
    assert any("Address conflict" in f for f in letter.flags)
    with pytest.raises(NeedsInputError, match="No target reduction"):
        plan_letter(claim, contacts[50013], ledger, {}, AS_OF, "X")


def test_loan_letter_reduces_interest_only_and_never_invents_the_split(case):
    claim, contacts, ledger = case
    letter = plan_letter(claim, contacts[50030], ledger, {"interest_reduction_percent": 50}, AS_OF, "X")
    assert letter.kind == LOAN
    assert letter.values["PROPOSED_PAYOFF"] == ""
    assert any("not broken out" in f for f in letter.flags)
    assert any("expired" in f for f in letter.flags)


def test_loan_letter_proposes_payoff_when_split_is_known(case):
    claim, contacts, ledger = case
    ledger = [dict(e, principal=5000, interest=1125, payoff_good_through="2026-12-31") if e["ledger_id"] == 7005 else e
              for e in ledger]
    letter = plan_letter(claim, contacts[50030], ledger, {"interest_reduction_percent": 50}, AS_OF, "X")
    assert "$5,562.50" in letter.values["PROPOSED_PAYOFF"]
    assert not letter.flags


def test_filename_has_nothing_appended():
    assert output_filename("Metro Pain & Spine", "Maria Rivera") == "Reduction Request - Metro Pain & Spine - Maria Rivera.pdf"


def test_draft_letters_end_to_end(client, tmp_path):
    request = json.loads((SAMPLE_INPUTS / "reduction_request.json").read_text())
    letters, notes = draft_letters(client.get_claim(10001), client.get_claim_contacts(10001),
                                   client.get_ledger(10001), request, tmp_path, keep_docx=True)
    assert [l.entity for l in letters] == ["Lakeview Imaging Center", "Metro Pain & Spine", "Example Funding Co."]
    assert any("Northside Chiropractic" in n for n in notes)  # on hold

    text = "\n".join(p.text for p in Document(letters[2].docx_path).paragraphs)
    assert "interest only, not principal" in text and "{{" not in text

    if shutil.which("soffice") or shutil.which("libreoffice"):
        for letter in letters:
            assert letter.pdf_path.exists()
            assert not [f for f in letter.flags if ".pdf" in f]  # one page, amounts present
