"""Reconcile treatment status, ledger entries and the document store for one case.

Produces the provider table (Provider, Treatment Period, Total Charge Amount, Total) and a
short list of red flags, each tied to its source. Nothing is invented: unknown dates and
amounts stay blank and are flagged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from ..common import fmt_money, money, provider_key, to_date

MEDICAL_EXPENSE = "medical expense"
PRIMARY_BILLING, PRIMARY_RECORDS, INTAKE, ARCHIVE = "billing", "records", "intake", "archive"

# Wording in a treatment note that suggests care is not over.
ONGOING_PATTERNS = [
    r"\bfollow[- ]?up\b", r"\bscheduled\b", r"\breferr(ed|al)\b", r"\bcontinu(e|es|ing)\b",
    r"\brecommend", r"\bplan(ned)?\b", r"\bnext visit\b", r"\bongoing\b",
]
FINISHED_PATTERNS = [r"\bdischarged\b", r"\bmmi\b", r"\bcompleted\b", r"\breleased\b", r"\bno further\b"]
FINISHED_STATUSES = {"completed", "discharged", "released", "done"}
RECENT_VISIT_DAYS = 45


@dataclass
class RedFlag:
    provider: str
    issue: str
    source: str


@dataclass
class ProviderLine:
    provider: str
    period_start: date | None = None
    period_end: date | None = None
    total: Decimal | None = None
    not_final: bool = False
    possibly_treating: bool = False
    status_reason: str = ""

    @property
    def period(self) -> str:
        if not self.period_start:
            return "Unknown"
        if self.period_end and self.period_end != self.period_start:
            return f"{self.period_start:%m/%d/%Y} - {self.period_end:%m/%d/%Y}"
        return f"{self.period_start:%m/%d/%Y}"

    @property
    def amount(self) -> str:
        if self.total is None:
            return "MISSING"
        return fmt_money(self.total) + (" NOT FINAL" if self.not_final else "")


@dataclass
class AuditReport:
    case_name: str
    as_of: date
    lines: list[ProviderLine]
    flags: list[RedFlag] = field(default_factory=list)

    @property
    def total(self) -> Decimal:
        return sum((l.total for l in self.lines if l.total is not None), Decimal("0.00"))

    @property
    def total_is_final(self) -> bool:
        return all(l.total is not None and not l.not_final for l in self.lines)


def treatment_status(provider: str, notes: list[dict], cms_status: str | None,
                     last_service: date | None, as_of: date) -> tuple[bool, str]:
    """Return (possibly_still_treating, reason). Doubt counts as still treating."""
    key = provider_key(provider)
    mine = sorted((n for n in notes if provider_key(n.get("provider")) == key),
                  key=lambda n: n.get("date") or "")
    ongoing_patterns = [re.compile(p, re.I) for p in ONGOING_PATTERNS]
    finished_patterns = [re.compile(p, re.I) for p in FINISHED_PATTERNS]

    if mine:
        latest = mine[-1]
        text = latest.get("text", "")
        if any(p.search(text) for p in ongoing_patterns):
            return True, f"Treatment note {latest.get('date')}: \"{text}\""
        if any(p.search(text) for p in finished_patterns):
            return False, f"Treatment note {latest.get('date')}: \"{text}\""

    # A referral in another provider's note counts as a sign of care with this provider.
    for note in notes:
        if provider_key(note.get("provider")) != key and key and key in provider_key(note.get("text")):
            if re.search(r"\breferr", note.get("text", ""), re.I):
                return True, f"Referred in {note.get('provider')} note {note.get('date')}: \"{note['text']}\""

    if last_service and (as_of - last_service) <= timedelta(days=RECENT_VISIT_DAYS):
        return True, f"Last date of service {last_service:%m/%d/%Y} is within {RECENT_VISIT_DAYS} days"
    if cms_status and cms_status.strip().casefold() in FINISHED_STATUSES:
        return False, f"CMS treatment status: {cms_status}"
    if cms_status:
        return True, f"CMS treatment status: {cms_status}"
    return True, "No treatment note or status confirms treatment is finished"


def _unique_documents(documents: list[dict]) -> list[dict]:
    """Drop copies of the same file across folders, preferring the cleaned folders."""
    rank = {PRIMARY_BILLING: 0, PRIMARY_RECORDS: 0, INTAKE: 1, ARCHIVE: 2}
    best: dict[str, dict] = {}
    for doc in sorted(documents, key=lambda d: rank.get(d.get("folder"), 3)):
        best.setdefault(doc.get("fingerprint") or doc["doc_id"], doc)
    return list(best.values())


def audit_case(claim: dict, contacts: list[dict], ledger: list[dict], notes: list[dict],
               documents: list[dict], as_of: date) -> AuditReport:
    flags: list[RedFlag] = []
    docs = _unique_documents(documents)

    providers: dict[str, str] = {}  # key -> display name, first seen
    for contact in contacts:
        if str(contact.get("role", "")).casefold() == "medical provider":
            providers.setdefault(provider_key(contact["name"]), contact["name"])
    medical = [e for e in ledger if str(e.get("entry_type", "")).casefold() == MEDICAL_EXPENSE]
    for source in medical:
        providers.setdefault(provider_key(source.get("payee")), source.get("payee"))
    for doc in docs:
        providers.setdefault(provider_key(doc.get("provider")), doc.get("provider"))

    status_by_key = {}
    for contact in contacts:
        for f in contact.get("ad_hoc_fields") or []:
            if f.get("label") == "Treatment Status" and f.get("value"):
                status_by_key[provider_key(contact["name"])] = f["value"]

    lines: list[ProviderLine] = []
    for key, name in providers.items():
        entries = [e for e in medical if provider_key(e.get("payee")) == key]
        bills = [d for d in docs if d.get("kind") == "bill" and provider_key(d.get("provider")) == key]
        records = [d for d in docs if d.get("kind") == "record" and provider_key(d.get("provider")) == key]
        line = ProviderLine(provider=name)

        # Inconsistent names for one provider across sources.
        spellings = {e.get("payee") for e in entries} | {d.get("provider") for d in bills + records}
        spellings |= {c["name"] for c in contacts if provider_key(c.get("name")) == key}
        if len(spellings - {None}) > 1:
            flags.append(RedFlag(name, "Provider name is spelled differently across sources: "
                                 + "; ".join(sorted(s for s in spellings if s)), "CMS contacts, ledger, documents"))

        # Duplicate ledger entries: same provider, date and charge.
        seen: dict[tuple, dict] = {}
        unique_entries = []
        for e in entries:
            sig = (e.get("date"), money(e.get("charge") or 0))
            if sig in seen:
                flags.append(RedFlag(name, f"Possible duplicate ledger entry: #{e['ledger_id']} repeats "
                                     f"#{seen[sig]['ledger_id']} ({fmt_money(e.get('charge') or 0)} on {e.get('date')})",
                                     "CMS ledger"))
                continue
            seen[sig] = e
            unique_entries.append(e)

        # Treatment period from records first, then bills.
        dated = records or bills
        starts = [to_date(d.get("service_from")) for d in dated if d.get("service_from")]
        ends = [to_date(d.get("service_to")) for d in dated if d.get("service_to")]
        line.period_start = min(starts) if starts else None
        line.period_end = max(ends) if ends else None

        line.possibly_treating, line.status_reason = treatment_status(
            name, notes, status_by_key.get(key), line.period_end, as_of)
        if line.possibly_treating:
            flags.append(RedFlag(name, "May still be treating; verify and update treatment status. "
                                 + line.status_reason, "CMS treatment notes"))

        # Charges: the ledger is the figure used, the bill is the support for it.
        if unique_entries:
            line.total = sum((money(e.get("charge") or 0) for e in unique_entries), Decimal("0.00"))
        bill_total = sum((money(b.get("amount") or 0) for b in bills), Decimal("0.00")) if bills else None

        if not unique_entries:
            where = (", ".join(sorted({b["folder"] for b in bills})) + " folder") if bills else "documents"
            flags.append(RedFlag(name, "No ledger entry for this provider"
                                 + (f"; bill for {fmt_money(bill_total)} found" if bills else ""), where))
            line.total = bill_total
        elif not bills:
            flags.append(RedFlag(name, "Ledger entry has no supporting bill", "billing folder"))
        elif bill_total is not None and bill_total != line.total:
            flags.append(RedFlag(name, f"Ledger charge {fmt_money(line.total)} does not match bills "
                                 f"{fmt_money(bill_total)}", "CMS ledger vs billing folder"))

        if bills and all(b.get("folder") != PRIMARY_BILLING for b in bills):
            flags.append(RedFlag(name, "Bill is only in the intake folder, not in the cleaned billing folder",
                                 "intake folder"))
        if not records:
            flags.append(RedFlag(name, "Missing medical records", "records folder"))
        if not line.period_start:
            flags.append(RedFlag(name, "Treatment dates unknown", "records folder"))

        line.not_final = line.possibly_treating or any(b.get("final") is False for b in bills)
        if line.total is None:
            flags.append(RedFlag(name, "No charge amount found anywhere", "ledger and billing folder"))
        lines.append(line)

    return AuditReport(case_name=claim.get("case_name", ""), as_of=as_of, lines=lines, flags=flags)


def to_markdown(report: AuditReport) -> str:
    out = [
        f"# Treatment Audit: {report.case_name}",
        f"_As of {report.as_of:%m/%d/%Y}. Synthetic demo data._",
        "",
        "| Provider | Treatment Period | Total Charge Amount |",
        "|---|---|---|",
    ]
    out += [f"| {l.provider} | {l.period} | {l.amount} |" for l in report.lines]
    total = fmt_money(report.total) + ("" if report.total_is_final else " NOT FINAL")
    out += [f"| **Total** | | **{total}** |", "", "## Red Flags", ""]
    if not report.flags:
        out.append("None.")
    out += [f"- **{f.provider}**: {f.issue} _(Source: {f.source})_" for f in report.flags]
    return "\n".join(out) + "\n"


def custodian_list(contacts: list[dict], report: AuditReport) -> tuple[str, list[RedFlag]]:
    """Records custodian list in a repeating block format. Missing contact info is flagged, not guessed."""
    blocks, flags = [], []
    by_key = {provider_key(c["name"]): c for c in contacts}
    for line in report.lines:
        contact = by_key.get(provider_key(line.provider), {})
        block = ["Records Custodian for"]
        block += list(contact.get("practitioners") or [])
        block.append(contact.get("name") or line.provider)
        if contact.get("address"):
            block.append(contact["address"])
        else:
            flags.append(RedFlag(line.provider, "Missing address for records custodian", "CMS contact"))
        if contact.get("phone"):
            block.append(contact["phone"])
        block.append("(Plaintiff's healthcare provider)")
        blocks.append("\n".join(block))
    return "\n\n".join(blocks) + "\n", flags
