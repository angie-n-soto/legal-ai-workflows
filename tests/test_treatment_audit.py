from datetime import date
from decimal import Decimal

import pytest

from legal_workflows.common import provider_key
from legal_workflows.treatment_audit.audit import audit_case, custodian_list, to_markdown, treatment_status

AS_OF = date(2026, 10, 16)


@pytest.fixture
def report(client):
    return audit_case(client.get_claim(10001), client.get_claim_contacts(10001), client.get_ledger(10001),
                      client.get_treatment_notes(10001), client.get_documents(10001), AS_OF)


def flags_for(report, provider):
    return [f.issue for f in report.flags if f.provider == provider]


def test_provider_names_normalize():
    assert provider_key("Metro Pain & Spine") == provider_key("Metro Pain and Spine, PLLC")


def test_one_line_per_provider_with_total(report):
    assert [l.provider for l in report.lines] == [
        "Northside Chiropractic", "Lakeview Imaging Center", "Metro Pain & Spine", "Riverbend Physical Therapy",
    ]
    assert report.total == Decimal("11800.50")
    assert not report.total_is_final


def test_duplicate_ledger_entry_is_flagged_and_not_double_counted(report):
    lakeview = next(l for l in report.lines if l.provider == "Lakeview Imaging Center")
    assert lakeview.total == Decimal("2100.50")
    assert any("duplicate ledger entry" in f for f in flags_for(report, "Lakeview Imaging Center"))


def test_copies_across_folders_are_not_counted_twice(report):
    # Lakeview's bill is in both billing and intake; Metro's is in billing and archive.
    assert not any("does not match" in f for f in flags_for(report, "Lakeview Imaging Center"))
    assert not any("does not match" in f for f in flags_for(report, "Metro Pain & Spine"))


def test_ongoing_treatment_is_never_assumed_finished(report):
    north = next(l for l in report.lines if l.provider == "Northside Chiropractic")
    assert north.possibly_treating and north.not_final
    assert "Follow-up scheduled" in north.status_reason


def test_referral_in_another_note_counts_as_possible_treatment(report):
    river = next(l for l in report.lines if l.provider == "Riverbend Physical Therapy")
    assert river.possibly_treating
    assert any("No ledger entry" in f for f in flags_for(report, "Riverbend Physical Therapy"))
    assert any("only in the intake folder" in f for f in flags_for(report, "Riverbend Physical Therapy"))


def test_discharged_provider_is_finished_but_missing_records_flagged(report):
    metro = next(l for l in report.lines if l.provider == "Metro Pain & Spine")
    assert not metro.possibly_treating and not metro.not_final
    issues = flags_for(report, "Metro Pain & Spine")
    assert "Missing medical records" in issues
    assert any("spelled differently" in f for f in issues)


def test_no_note_and_no_status_means_uncertain():
    treating, reason = treatment_status("Someone", [], None, None, AS_OF)
    assert treating and "No treatment note" in reason


def test_markdown_table_and_custodian_list(client, report):
    md = to_markdown(report)
    assert "| **Total** | | **$11,800.50 NOT FINAL** |" in md
    assert md.index("| Provider |") < md.index("## Red Flags")
    text, flags = custodian_list(client.get_claim_contacts(10001), report)
    assert text.count("Records Custodian for") == 4
    assert "Sam Ortiz, M.D.\nPriya Shah, M.D.\nMetro Pain & Spine" in text
    assert [f.provider for f in flags] == ["Riverbend Physical Therapy"]  # no address: flagged, not invented
