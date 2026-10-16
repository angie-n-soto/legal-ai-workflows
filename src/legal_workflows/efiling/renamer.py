"""Name e-filed documents as [YYYYMMDD] [CLIENT LAST] [CLIENT FIRST] [DESCRIPTION].

In the original workflow the model read each PDF's caption. This module starts from caption
fields that have already been extracted and applies the naming and confidence rules as code,
so they are deterministic and testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from ..common import to_date

HIGH, MEDIUM, LOW = "HIGH", "MEDIUM", "LOW"
_CONFIDENCE_ORDER = {LOW: 0, MEDIUM: 1, HIGH: 2}


@dataclass
class RenameResult:
    original_filename: str
    cause_number: str
    new_filename: str
    confidence: str
    plaintiffs: list[str]
    defendants: list[str]
    court: str
    client: str
    description: str
    reasons: list[str] = field(default_factory=list)


def date_code(received: date) -> str:
    """October 8, 2026 -> 20261008. No dashes; month and day keep their leading zeros."""
    return f"{received:%Y%m%d}"


def clean_part(text: str) -> str:
    """ALL CAPS, single spaces, no punctuation or special characters."""
    return " ".join(re.sub(r"[^A-Z0-9 ]", " ", re.sub(r"['\u2019]", "", text.upper())).split())


def _split_name(full_name: str) -> tuple[str, str]:
    parts = full_name.replace(".", " ").split()
    return (parts[-1], " ".join(parts[:-1])) if parts else ("", "")


def identify_client(plaintiffs: list[str], clients: list[dict]) -> tuple[dict | None, str, list[str]]:
    """Match caption plaintiffs against the firm's client list.

    Returns (client, match_level, reasons). match_level is "full", "last_name" or "none".
    """
    reasons: list[str] = []
    full, last_only = [], []
    for plaintiff in plaintiffs:
        last, first = _split_name(plaintiff)
        for client in clients:
            if client["last_name"].casefold() != last.casefold():
                continue
            if client["first_name"].casefold() == first.casefold():
                full.append((plaintiff, client))
            else:
                last_only.append((plaintiff, client))

    if len(full) == 1:
        return full[0][1], "full", reasons
    if len(full) > 1:
        reasons.append("More than one plaintiff matches a firm client: " + ", ".join(p for p, _ in full))
        return full[0][1], "none", reasons
    if len(last_only) == 1:
        plaintiff, client = last_only[0]
        reasons.append(
            f"Caption name '{plaintiff}' only matches client {client['first_name']} "
            f"{client['last_name']} by last name"
        )
        return client, "last_name", reasons
    reasons.append("No plaintiff in the caption matches a firm client")
    return None, "none", reasons


def rename_document(doc: dict, clients: list[dict]) -> RenameResult:
    caption = doc.get("caption") or {}
    plaintiffs = list(caption.get("plaintiffs") or [])
    defendants = list(caption.get("defendants") or [])
    cause = caption.get("cause_number") or ""
    court = caption.get("court") or ""
    description = clean_part(caption.get("description") or "")
    received = to_date(doc["received"])

    reasons: list[str] = []
    confidence = HIGH

    if not caption.get("legible", True) or not plaintiffs:
        confidence = LOW
        reasons.append("Caption is unclear or no plaintiff could be read")

    if len(plaintiffs) > 1:
        confidence = LOW
        reasons.append(f"Multiple plaintiffs ({len(plaintiffs)}); confirm which one is our client")

    client, match, match_reasons = identify_client(plaintiffs, clients) if plaintiffs else (None, "none", [])
    reasons += match_reasons
    if match == "none":
        confidence = LOW
    elif match == "last_name" and confidence == HIGH:
        confidence = MEDIUM

    missing = [label for label, value in (("cause number", cause), ("court", court), ("description", description)) if not value]
    if missing:
        reasons.append("Missing from caption: " + ", ".join(missing))
        if confidence == HIGH:
            confidence = MEDIUM

    client_part = clean_part(f"{client['last_name']} {client['first_name']}") if client else "UNKNOWN CLIENT"
    new_name = " ".join(p for p in (date_code(received), client_part, description or "UNKNOWN DOCUMENT") if p)

    return RenameResult(
        original_filename=doc["original_filename"],
        cause_number=cause,
        new_filename=new_name,
        confidence=confidence,
        plaintiffs=plaintiffs,
        defendants=defendants,
        court=court,
        client=f"{client['first_name']} {client['last_name']}" if client else "",
        description=description,
        reasons=reasons,
    )


def rename_all(documents: list[dict], clients: list[dict]) -> list[RenameResult]:
    """Rename every document, LOW and MEDIUM first so they get reviewed."""
    results = [rename_document(d, clients) for d in documents]
    return sorted(results, key=lambda r: _CONFIDENCE_ORDER[r.confidence])


def to_markdown(results: list[RenameResult]) -> str:
    lines = [
        "| Original filename | Cause number | New filename | Confidence |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {r.original_filename} | {r.cause_number or '(missing)'} | {r.new_filename} | {r.confidence} |"
        for r in results
    ]
    notes = [r for r in results if r.reasons]
    if notes:
        lines += ["", "**Why some rows need review**", ""]
        lines += [f"- `{r.original_filename}` ({r.confidence}): " + "; ".join(r.reasons) for r in notes]
    return "\n".join(lines) + "\n"
