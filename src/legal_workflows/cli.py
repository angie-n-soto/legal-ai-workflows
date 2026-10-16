"""Command line entry point: legal-workflows <audit|rename|reductions|treatment> ..."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .cms import AmbiguousClaimError, ClaimNotFoundError, MockCMSClient, resolve_claim_id
from .common import to_date

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = ROOT / "mock_cms" / "claims"
SAMPLE_INPUTS = ROOT / "sample_inputs"


def run_audit(claim_ref: str, data_dir: Path, out_dir: Path) -> Path:
    from .medical_audit.extract import build_rows
    from .medical_audit.workbook import build_workbook, save_workbook, verify_workbook

    client = MockCMSClient(data_dir)
    claim_id = resolve_claim_id(client, claim_ref)
    claim = client.get_claim(claim_id)
    columns, rows = build_rows(client.get_claim_contacts(claim_id))
    wb = build_workbook(claim, columns, rows)
    problems = verify_workbook(wb, expected_providers=len(rows))
    if problems:
        raise RuntimeError("Workbook failed verification:\n- " + "\n- ".join(problems))
    return save_workbook(wb, claim, out_dir)


def run_rename(inbox: Path, data_dir: Path, out_dir: Path) -> Path:
    from .efiling.renamer import rename_all, to_markdown

    documents = json.loads(inbox.read_text(encoding="utf-8"))["documents"]
    results = rename_all(documents, MockCMSClient(data_dir).list_clients())
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "efiling_rename_table.md"
    path.write_text(to_markdown(results), encoding="utf-8")
    return path


def run_treatment(claim_ref: str, data_dir: Path, out_dir: Path, as_of: date) -> Path:
    from .treatment_audit.audit import audit_case, custodian_list, to_markdown

    client = MockCMSClient(data_dir)
    claim_id = resolve_claim_id(client, claim_ref)
    claim = client.get_claim(claim_id)
    contacts = client.get_claim_contacts(claim_id)
    report = audit_case(claim, contacts, client.get_ledger(claim_id),
                        client.get_treatment_notes(claim_id), client.get_documents(claim_id), as_of)
    custodians, flags = custodian_list(contacts, report)
    report.flags += flags
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{claim['case_name'].replace('/', '_')}_Treatment_Audit.md"
    path.write_text(to_markdown(report) + "\n## Records Custodian List (draft)\n\n```text\n" + custodians + "```\n",
                    encoding="utf-8")
    return path


def run_reductions(request_path: Path, data_dir: Path, out_dir: Path, keep_docx: bool) -> str:
    from .reductions.letters import draft_letters, summary

    request = json.loads(request_path.read_text(encoding="utf-8"))
    client = MockCMSClient(data_dir)
    claim_id = int(request["claim_id"])
    letters, notes = draft_letters(client.get_claim(claim_id), client.get_claim_contacts(claim_id),
                                   client.get_ledger(claim_id), request, out_dir, keep_docx)
    return summary(letters, notes)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="legal-workflows", description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR, help="Folder of mock CMS JSON")
    parser.add_argument("--out", type=Path, default=Path("output"), help="Output folder")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("audit", help="Medical provider audit workbook (.xlsx)")
    p.add_argument("claim", help="Claim URL, numeric claim ID, or case name")

    p = sub.add_parser("rename", help="Rename e-filed documents from their captions")
    p.add_argument("inbox", nargs="?", type=Path, default=SAMPLE_INPUTS / "efiling_inbox.json")

    p = sub.add_parser("treatment", help="Treatment and ledger audit with red flags")
    p.add_argument("claim", help="Claim URL, numeric claim ID, or case name")
    p.add_argument("--as-of", default=None, help="Audit date, YYYY-MM-DD (default: today)")

    p = sub.add_parser("reductions", help="Draft reduction request letters (PDF)")
    p.add_argument("request", nargs="?", type=Path, default=SAMPLE_INPUTS / "reduction_request.json")
    p.add_argument("--keep-docx", action="store_true", help="Also keep the editable .docx files")

    args = parser.parse_args(argv)
    try:
        if args.command == "audit":
            print(f"Saved {run_audit(args.claim, args.data_dir, args.out)}")
        elif args.command == "rename":
            print(f"Saved {run_rename(args.inbox, args.data_dir, args.out)}")
        elif args.command == "treatment":
            as_of = to_date(args.as_of) or date.today()
            print(f"Saved {run_treatment(args.claim, args.data_dir, args.out, as_of)}")
        else:
            print(run_reductions(args.request, args.data_dir, args.out, args.keep_docx), end="")
    except AmbiguousClaimError as exc:
        print(f"{exc}\nPlease re-run with the claim ID you want.", file=sys.stderr)
        return 2
    except (ClaimNotFoundError, RuntimeError) as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
