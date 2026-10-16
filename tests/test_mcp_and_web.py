import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from legal_workflows.mcp_server import mcp
from legal_workflows.mdhtml import to_html
from legal_workflows.web import app


def call(tool, **args):
    result = asyncio.run(mcp.call_tool(tool, args))
    content = result[0] if isinstance(result, tuple) else result
    return [c.text for c in content]


# --- MCP server ------------------------------------------------------------------------------

def test_every_tool_is_marked_read_only():
    tools = asyncio.run(mcp.list_tools())
    assert len(tools) == 11
    assert all(t.annotations.readOnlyHint and not t.annotations.destructiveHint for t in tools)


def test_contacts_filtered_by_role():
    names = [json.loads(t)["name"] for t in call("get_claim_contacts", claim="rivera", role="medical provider")]
    assert names == ["Northside Chiropractic", "Lakeview Imaging Center", "Metro Pain & Spine", "Riverbend Physical Therapy"]


def test_ambiguous_claim_name_is_refused():
    with pytest.raises(Exception, match="matches multiple claims"):
        call("get_claim", claim="e")


def test_reduction_plan_and_needs_input():
    plan = json.loads(call("plan_reduction_letter", claim="10001", contact_id=50030,
                           interest_reduction_percent=50, as_of="2026-10-16")[0])
    assert plan["letter_type"] == "loan" and plan["payoff"] == "6125.00"
    missing = json.loads(call("plan_reduction_letter", claim="10001", contact_id=50012, reduction_percent=33)[0])
    assert "ledger_id" in missing["needs_input"]  # duplicate ledger entries: asks instead of guessing


def test_treatment_audit_tool():
    text = call("treatment_audit", claim="10001", as_of="2026-10-16")[0]
    assert "$11,800.50 NOT FINAL" in text and "Records Custodian for" in text


# --- web app ---------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def web():
    # The MCP session manager can start only once per process, so the app starts once for all tests.
    with TestClient(app) as client:
        yield client


def test_pages_and_reports(web):
    assert "Legal AI Workflows" in web.get("/").text
    assert web.get("/api/claims").json()[0]["id"] == 10001
    assert "<table>" in web.get("/api/treatment/10001?as_of=2026-10-16").json()["html"]
    assert "20261007 RIVERA MARIA" in web.get("/api/rename").json()["markdown"]
    assert web.get("/api/treatment/nobody").status_code == 404


def test_audit_download(web):
    r = web.get("/api/audit/10001")
    assert r.status_code == 200 and r.content[:2] == b"PK"  # an .xlsx is a zip file


def test_file_route_rejects_bad_paths(web):
    assert web.get("/api/files/not-a-run/x.pdf").status_code == 404
    assert web.get("/api/files/" + "0" * 32 + "/missing.pdf").status_code == 404


def test_mcp_endpoint_is_mounted(web):
    tools = web.get("/api/mcp-tools").json()
    assert {t["name"] for t in tools} >= {"get_usage_rules", "treatment_audit"}
    body = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}}
    r = web.post("/mcp", json=body, headers={"Accept": "application/json, text/event-stream", "Host": "localhost:8000"})
    assert r.status_code == 200 and r.json()["result"]["serverInfo"]["name"] == "legal-cms"


def test_markdown_converter():
    out = to_html("# T\n\n| A | B |\n|---|---|\n| **x** | `y` |\n\n- one _two_")
    assert "<h3>T</h3>" in out and "<strong>x</strong>" in out and "<code>y</code>" in out and "<em>two</em>" in out
