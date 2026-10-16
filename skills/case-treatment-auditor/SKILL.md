---
name: case-treatment-auditor
description: Audit a personal injury client's treatment status, medical ledger and supporting bills and records, then report a provider table and red flags; also drafts records custodian lists from templates. Use when the user asks for a treatment audit, a medical ledger review, or a records custodian list.
---

# Case Treatment Auditor

> Portfolio note: this is a sanitized rebuild of an agent skill I wrote for a personal injury
> law firm. The vendor CMS name, the firm's document-store folder layout, internal file IDs,
> firm templates and an unfinished demand-drafting section have been removed or generalized.
> Python code that applies the same rules is in `src/legal_workflows/treatment_audit/`.

This skill supports treatment audits, medical ledger reviews and drafting from templates. Its first
priority is determining the client's current treatment status accurately, using the case
management system (CMS), reached through its MCP connection, and the client's document store.

## 1. Treatment status first

Start with the client's injury and treatment notes in the CMS and read every note. Decide whether the
client appears to be done treating. If any note, recent date of service, scheduled follow-up,
referral, recommendation, open treatment plan or provider status suggests ongoing care, **do not treat
the client as finished.** Name each provider the client may still be seeing and quote the detail that
creates the doubt, so the user can verify it and update the CMS.

## 2. Ledger reconciliation

Review the ledger's medical-expense entries: total charges and current balances for every provider.
Reconcile provider names, treatment dates and amounts against the bills and records. Identify:

- duplicate ledger entries
- providers in the records with no ledger entry
- ledger entries with no supporting bill
- amounts that look incomplete or not final
- conflicting dates, inconsistent provider names and unexplained balance changes

## 3. Document store

| Folder | Use |
|---|---|
| `billing` | Primary source for bills, billing affidavits and final balances |
| `records` | Primary source for medical records, records affidavits and treatment dates |
| `intake` | Original intake documents; may hold copies of files already in the cleaned folders |
| `archive` | Duplicates or unneeded copies; reference only, never counted |

Once the client is done treating, confirm final balances and completeness from `billing` and
`records`. Check `intake` only to explain a discrepancy. **A document found in more than one folder
is one document**: never count it as a second charge or a second course of treatment.

## 4. Output

1. **Provider table** first: Provider | Treatment Period | Total Charge Amount, one row per provider,
   plus a Total row. Mark provisional amounts `NOT FINAL`. Combine ledger entries for one provider only
   when they clearly belong to the same account. Never invent dates, balances, providers or totals.
2. **Red Flags** right after: short, action-oriented, only items that need the user's attention, each
   tied to its source or folder.

## 5. Drafting from templates

Use the user's templates whenever they are provided. Keep their structure, headings, order, formatting
and tone. The template's tone takes priority over the default concise style.

**Records custodian list**: repeat one block per provider:

```
Records Custodian for
<practitioner name(s) and credentials, one per line, when known>
<facility or entity name>
<street or mailing address>
<phone, when available>
(Plaintiff's healthcare provider)
```

Include every verified provider who may need a custodian. If only the entity is known, list only the
entity. Never invent addresses, phone numbers, credentials or affiliations; flag what is missing.

## 6. Always

Separate verified facts from inferences and missing information, cite where each fact came from, and
flag unsupported statements before using them. Treat client and medical information as confidential
and repeat it no more than needed. If the CMS, a folder, a template or a file is unavailable, say
exactly what is needed rather than claiming it was reviewed.
