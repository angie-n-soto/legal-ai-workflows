"""MCP server for the mock case management system (CMS).

At the firm, the agent skills reached the CMS through an MCP server. This module rebuilds that
pattern over the synthetic case data: read-only CMS tools an AI agent can call, plus tools that
run the four workflows.

Run it locally for an MCP client such as Claude Desktop or the MCP Inspector:

    python -m legal_workflows.mcp_server            # stdio
    python -m legal_workflows.mcp_server --http     # streamable HTTP on http://127.0.0.1:8000/mcp

The demo web app (`legal_workflows.web`) also serves it at `/mcp`.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from .cms import AmbiguousClaimError, ClaimNotFoundError, MockCMSClient, resolve_claim_id
from .common import to_date

DATA_DIR = Path(os.environ.get("CMS_DATA_DIR", Path(__file__).resolve().parents[2] / "mock_cms" / "claims"))

USAGE_RULES = """\
Rules for using this CMS server:
1. Every tool is read-only. Nothing here changes case data.
2. Resolve a claim from its URL, numeric ID or case name. If a name matches more than one claim,
   ask the user which one they mean. Never guess.
3. Prefer the lightest tool that answers the question. Do not pull notes or documents you don't need.
4. Never invent values. If a field is empty, report it as missing.
5. All data on this server is synthetic and exists only for demonstration.
"""

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)


def _security() -> TransportSecuritySettings:
    """Protect against DNS rebinding; allow localhost plus the Render hostname when deployed."""
    hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
    origins = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]
    for host in filter(None, [os.environ.get("RENDER_EXTERNAL_HOSTNAME"), *os.environ.get("MCP_ALLOWED_HOSTS", "").split(",")]):
        hosts += [host.strip(), f"{host.strip()}:*"]
        origins.append(f"https://{host.strip()}")
    return TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=hosts, allowed_origins=origins)


mcp = FastMCP(
    "legal-cms",
    instructions=USAGE_RULES,
    stateless_http=True,
    json_response=True,
    streamable_http_path="/mcp",
    transport_security=_security(),
)


def _client() -> MockCMSClient:
    return MockCMSClient(DATA_DIR)


def _claim_id(client: MockCMSClient, claim: str) -> int:
    try:
        return resolve_claim_id(client, str(claim))
    except AmbiguousClaimError as exc:
        raise ValueError(f"{exc}. Ask the user which claim they mean.") from None
    except ClaimNotFoundError as exc:
        raise ValueError(str(exc)) from None


# --- CMS read tools --------------------------------------------------------------------------

@mcp.tool(annotations=READ_ONLY)
def get_usage_rules() -> str:
    """Read this first. The rules every caller of this CMS server must follow."""
    return USAGE_RULES


@mcp.tool(annotations=READ_ONLY)
def list_claims() -> list[dict[str, Any]]:
    """List every claim: ID, case name and URL."""
    return [{k: c[k] for k in ("id", "case_name", "url")} for c in _client().list_claims()]


@mcp.tool(annotations=READ_ONLY)
def get_claim(claim: str) -> dict[str, Any]:
    """Get one claim's record (client, incident date, incident type) by URL, numeric ID or case name."""
    client = _client()
    return client.get_claim(_claim_id(client, claim))


@mcp.tool(annotations=READ_ONLY)
def get_claim_contacts(claim: str, role: str | None = None) -> list[dict[str, Any]]:
    """Get a claim's contacts, optionally filtered by role (case-insensitive), e.g. "Medical Provider"."""
    client = _client()
    contacts = client.get_claim_contacts(_claim_id(client, claim))
    if role:
        contacts = [c for c in contacts if str(c.get("role", "")).casefold() == role.casefold()]
    return contacts


@mcp.tool(annotations=READ_ONLY)
def get_ledger(claim: str, entry_type: str | None = None) -> list[dict[str, Any]]:
    """Get a claim's ledger entries, optionally filtered by entry type, e.g. "Medical Expense"."""
    client = _client()
    entries = client.get_ledger(_claim_id(client, claim))
    if entry_type:
        entries = [e for e in entries if str(e.get("entry_type", "")).casefold() == entry_type.casefold()]
    return entries


@mcp.tool(annotations=READ_ONLY)
def get_treatment_notes(claim: str) -> list[dict[str, Any]]:
    """Get the injury and treatment notes on a claim."""
    client = _client()
    return client.get_treatment_notes(_claim_id(client, claim))


@mcp.tool(annotations=READ_ONLY)
def get_documents(claim: str) -> list[dict[str, Any]]:
    """Get the index of a claim's document store: folder, kind (bill or record), provider, dates and amounts."""
    client = _client()
    return client.get_documents(_claim_id(client, claim))


# --- Workflow tools ---------------------------------------------------------------------------

@mcp.tool(annotations=READ_ONLY)
def medical_provider_audit(claim: str) -> dict[str, Any]:
    """Build the medical provider audit rows for a claim (the data behind the audit workbook)."""
    from .medical_audit.extract import build_rows

    client = _client()
    claim_id = _claim_id(client, claim)
    columns, rows = build_rows(client.get_claim_contacts(claim_id))
    clean = [{k: (v.isoformat() if isinstance(v, date) else v) for k, v in r.items()} for r in rows]
    return {"claim": client.get_claim(claim_id)["case_name"], "provider_count": len(rows),
            "columns": columns, "rows": clean}


@mcp.tool(annotations=READ_ONLY)
def treatment_audit(claim: str, as_of: str | None = None) -> str:
    """Run the treatment audit: provider table, red flags and a draft records custodian list (Markdown).

    as_of is the audit date as YYYY-MM-DD; it defaults to today.
    """
    from .treatment_audit.audit import audit_case, custodian_list, to_markdown

    client = _client()
    claim_id = _claim_id(client, claim)
    contacts = client.get_claim_contacts(claim_id)
    report = audit_case(client.get_claim(claim_id), contacts, client.get_ledger(claim_id),
                        client.get_treatment_notes(claim_id), client.get_documents(claim_id),
                        to_date(as_of) or date.today())
    custodians, flags = custodian_list(contacts, report)
    report.flags += flags
    return to_markdown(report) + "\n## Records Custodian List (draft)\n\n" + custodians


@mcp.tool(annotations=READ_ONLY)
def rename_efiled_documents(documents_json: str | None = None) -> str:
    """Propose filenames for e-filed documents from their caption fields (Markdown table).

    documents_json is a JSON list of {original_filename, received, caption{plaintiffs, defendants,
    cause_number, court, description, legible}}. Leave it empty to use the sample inbox.
    """
    from .efiling.renamer import rename_all, to_markdown

    if documents_json:
        documents = json.loads(documents_json)
    else:
        sample = Path(__file__).resolve().parents[2] / "sample_inputs" / "efiling_inbox.json"
        documents = json.loads(sample.read_text(encoding="utf-8"))["documents"]
    return to_markdown(rename_all(documents, _client().list_clients()))


@mcp.tool(annotations=READ_ONLY)
def plan_reduction_letter(claim: str, contact_id: int, reduction_percent: float | None = None,
                          interest_reduction_percent: float | None = None, ledger_id: int | None = None,
                          use_ledger_current_due: bool = False, as_of: str | None = None) -> dict[str, Any]:
    """Work out a reduction request without drafting the letter: payoff, percentage, filename and flags.

    Medical providers take reduction_percent (or use_ledger_current_due when a reduction is already
    entered). Funding companies take interest_reduction_percent, which applies to interest only.
    """
    from .reductions.letters import NeedsInputError, plan_letter

    client = _client()
    claim_id = _claim_id(client, claim)
    request = {"reduction_percent": reduction_percent, "interest_reduction_percent": interest_reduction_percent,
               "ledger_id": ledger_id, "use_ledger_current_due": use_ledger_current_due}
    try:
        letter = plan_letter(client.get_claim(claim_id), client.get_contact(claim_id, contact_id),
                             client.get_ledger(claim_id), request, to_date(as_of) or date.today(), "[Attorney Name]")
    except (NeedsInputError, ClaimNotFoundError) as exc:
        return {"needs_input": str(exc)}
    return {"entity": letter.entity, "letter_type": letter.kind, "billed": str(letter.billed),
            "payoff": str(letter.payoff), "reduction_percent": str(letter.reduction_percent),
            "filename": letter.filename, "flags": letter.flags}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the mock CMS MCP server.")
    parser.add_argument("--http", action="store_true", help="Serve streamable HTTP instead of stdio")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    if args.http:
        import uvicorn

        uvicorn.run(mcp.streamable_http_app(), host="127.0.0.1", port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
