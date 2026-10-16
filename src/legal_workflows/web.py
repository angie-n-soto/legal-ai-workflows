"""Demo web app: run each workflow in the browser, and serve the MCP server at /mcp.

    uvicorn legal_workflows.web:app --reload
"""

from __future__ import annotations

import contextlib
import json
import re
import shutil
import tempfile
import uuid
from urllib.parse import quote
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from .cli import DEFAULT_DATA_DIR, SAMPLE_INPUTS, run_audit, run_rename, run_treatment
from .cms import AmbiguousClaimError, ClaimNotFoundError, MockCMSClient
from .common import to_date
from .mcp_server import mcp
from .mdhtml import to_html

STATIC = Path(__file__).resolve().parent / "static"
RUNS = Path(tempfile.gettempdir()) / "legal-workflows-runs"
MAX_RUNS = 50


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="Legal AI Workflows demo", lifespan=lifespan, docs_url="/api/docs", redoc_url=None)


def _new_run() -> Path:
    RUNS.mkdir(parents=True, exist_ok=True)
    old = sorted(RUNS.iterdir(), key=lambda p: p.stat().st_mtime)
    for stale in old[: max(0, len(old) - MAX_RUNS)]:
        shutil.rmtree(stale, ignore_errors=True)
    run = RUNS / uuid.uuid4().hex
    run.mkdir()
    return run


def _lookup_errors(fn):
    try:
        return fn()
    except (AmbiguousClaimError, ClaimNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (STATIC / "index.html").read_text(encoding="utf-8")


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/claims")
def claims() -> list[dict]:
    return [{k: c[k] for k in ("id", "case_name")} for c in MockCMSClient(DEFAULT_DATA_DIR).list_claims()]


@app.get("/api/audit/{claim}")
def audit(claim: str) -> FileResponse:
    path = _lookup_errors(lambda: run_audit(claim, DEFAULT_DATA_DIR, _new_run()))
    return FileResponse(path, filename=path.name,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.get("/api/treatment/{claim}")
def treatment(claim: str, as_of: str | None = None) -> dict:
    as_of_date = to_date(as_of) or date.today()
    path = _lookup_errors(lambda: run_treatment(claim, DEFAULT_DATA_DIR, _new_run(), as_of_date))
    text = path.read_text(encoding="utf-8")
    return {"markdown": text, "html": to_html(text)}


@app.get("/api/rename")
def rename() -> dict:
    path = run_rename(SAMPLE_INPUTS / "efiling_inbox.json", DEFAULT_DATA_DIR, _new_run())
    inbox = json.loads((SAMPLE_INPUTS / "efiling_inbox.json").read_text(encoding="utf-8"))["documents"]
    text = path.read_text(encoding="utf-8")
    return {"markdown": text, "html": to_html(text), "inbox": inbox}


@app.get("/api/reductions")
def reductions() -> dict:
    from .reductions.letters import draft_letters, summary

    request = json.loads((SAMPLE_INPUTS / "reduction_request.json").read_text(encoding="utf-8"))
    client = MockCMSClient(DEFAULT_DATA_DIR)
    claim_id = int(request["claim_id"])
    run = _new_run()
    letters, notes = draft_letters(client.get_claim(claim_id), client.get_claim_contacts(claim_id),
                                   client.get_ledger(claim_id), request, run)
    files = []
    for letter in letters:
        path = letter.pdf_path or letter.docx_path
        files.append({"entity": letter.entity, "name": path.name, "flags": letter.flags,
                      "payoff": str(letter.payoff), "url": f"/api/files/{run.name}/{quote(path.name)}"})
    return {"request": request, "letters": files, "notes": notes, "summary": summary(letters, notes)}


@app.get("/api/files/{run_id}/{name}")
def files(run_id: str, name: str) -> FileResponse:
    if not re.fullmatch(r"[0-9a-f]{32}", run_id) or "/" in name or "\\" in name or name.startswith("."):
        raise HTTPException(status_code=404)
    path = RUNS / run_id / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File expired; run the workflow again.")
    return FileResponse(path, filename=name)


@app.get("/api/mcp-tools")
async def mcp_tools() -> list[dict]:
    return [{"name": t.name, "description": (t.description or "").strip().splitlines()[0]}
            for t in await mcp.list_tools()]


# The MCP server answers at /mcp. Mounted last so the routes above take priority.
app.mount("/", mcp.streamable_http_app())
