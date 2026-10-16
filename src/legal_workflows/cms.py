"""Read-only access to a case management system (CMS), shared by every workflow.

The original agent skills talked to a commercial legal CMS through an MCP server connected to ChatGPT.
Here the CMS is a small interface with a mock implementation backed by local JSON files,
so every workflow can run and be tested without any real case data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol
from urllib.parse import parse_qs, urlparse


class ClaimNotFoundError(LookupError):
    pass


class AmbiguousClaimError(LookupError):
    """A case name matched more than one claim. The caller must ask the user to choose."""

    def __init__(self, query: str, matches: list[dict]):
        self.matches = matches
        names = ", ".join(f"{m['case_name']} (ID {m['id']})" for m in matches)
        super().__init__(f"'{query}' matches multiple claims: {names}")


class CMSClient(Protocol):
    def list_claims(self) -> list[dict]: ...
    def get_claim(self, claim_id: int) -> dict: ...
    def get_claim_contacts(self, claim_id: int) -> list[dict]: ...
    def get_ledger(self, claim_id: int) -> list[dict]: ...
    def get_treatment_notes(self, claim_id: int) -> list[dict]: ...
    def get_documents(self, claim_id: int) -> list[dict]: ...


class MockCMSClient:
    """Serves claims from JSON files in a folder. Read-only by design."""

    def __init__(self, data_dir: str | Path):
        self._claims: dict[int, dict] = {}
        for path in sorted(Path(data_dir).glob("*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            self._claims[int(record["claim"]["id"])] = record

    def list_claims(self) -> list[dict]:
        return [dict(r["claim"]) for r in self._claims.values()]

    def get_claim(self, claim_id: int) -> dict:
        try:
            return dict(self._claims[claim_id]["claim"])
        except KeyError:
            raise ClaimNotFoundError(f"No claim with ID {claim_id}") from None

    def _section(self, claim_id: int, key: str) -> list[dict]:
        if claim_id not in self._claims:
            raise ClaimNotFoundError(f"No claim with ID {claim_id}")
        return [dict(item) for item in (self._claims[claim_id].get(key) or [])]

    def get_claim_contacts(self, claim_id: int) -> list[dict]:
        return self._section(claim_id, "contacts")

    def get_contact(self, claim_id: int, contact_id: int) -> dict:
        for contact in self.get_claim_contacts(claim_id):
            if contact.get("contact_id") == contact_id:
                return contact
        raise ClaimNotFoundError(f"No contact {contact_id} on claim {claim_id}")

    def get_ledger(self, claim_id: int) -> list[dict]:
        return self._section(claim_id, "ledger")

    def get_treatment_notes(self, claim_id: int) -> list[dict]:
        return self._section(claim_id, "treatment_notes")

    def get_documents(self, claim_id: int) -> list[dict]:
        """Index of the case's document store (folder, kind, provider, amounts, dates)."""
        return self._section(claim_id, "documents")

    def list_clients(self) -> list[dict]:
        """Every client the firm represents, with the claim they belong to."""
        return [
            {**r["claim"]["client"], "claim_id": int(r["claim"]["id"])}
            for r in self._claims.values()
            if r["claim"].get("client")
        ]


def resolve_claim_id(client: CMSClient, ref: str) -> int:
    """Resolve a claim URL, numeric ID or case name to a claim ID. Never guesses."""
    ref = ref.strip()

    if ref.startswith(("http://", "https://")):
        query = parse_qs(urlparse(ref).query)
        ids = query.get("id") or query.get("ID")
        if not ids or not ids[0].isdigit():
            raise ClaimNotFoundError(f"No numeric 'id' parameter in URL: {ref}")
        return int(ids[0])

    if ref.isdigit():
        return int(ref)

    needle = ref.casefold()
    matches = [c for c in client.list_claims() if needle in c["case_name"].casefold()]
    if not matches:
        raise ClaimNotFoundError(f"No claim matches '{ref}'")
    if len(matches) > 1:
        raise AmbiguousClaimError(ref, matches)
    return int(matches[0]["id"])
