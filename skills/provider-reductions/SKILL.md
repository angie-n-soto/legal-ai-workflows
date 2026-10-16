---
name: provider-reductions
description: Draft reduction request letters from case ledger data in a legal case management system (CMS), for medical providers and for litigation-funding or loan companies, using the firm's approved letter templates. Use when the user asks for reduction letters, lien reductions or payoff reductions on a case.
---

# Provider Reductions

> Portfolio note: this is a sanitized rebuild of an agent skill I wrote for a personal
> injury law firm. The firm name, attorney, signature, letterhead, approved templates and
> wording, vendor-specific operations and real company names have all been removed or replaced
> with generic placeholders. Python code that applies the same rules is in
> `src/legal_workflows/reductions/`.

## Templates

- `assets/provider-reduction-template.docx`: the master letter for medical providers.
- `assets/loan-company-reduction-template.docx`: the wording and layout reference for
  litigation-funding and loan companies.

(This repo generates generic stand-ins for both in `src/legal_workflows/reductions/templates.py`.)

## CMS is the source of truth

1. Use the CMS MCP connection. Before any other CMS call, load the MCP server's own usage and
   access rules and follow them.
2. Resolve the correct claim. If more than one claim matches, ask; never guess.
3. Discover the documented read endpoints before running anything. Prefer the lightest
   endpoints that return the claim with its ledger, and the contact record for mailing details.
4. Stay read-only unless the user separately asks to update the CMS.
5. For each entity, use the matching ledger entry for the billed or payoff amount, current due,
   reduction and reference data. If there is more than one possible entry, ask which one to use.
6. Take the client name, date of birth and date of incident from the claim record. Never invent
   missing data.
7. If address data conflicts or looks wrong, don't silently fix it. Keep any address the user
   approved, and flag the conflict.

## Choose the letter type

### Medical provider
- Draft only for the providers the user names, and respect every hold or exclusion.
- If the user gives a reduction percentage, calculate the payoff from the pre-reduction bill.
  For example, an 85% reduction leaves 15% due.
- If no percentage is given, use a reduction already entered in the CMS only when it clearly
  represents the user's request. Otherwise ask for the target reduction.
- Round currency to cents.

### Litigation funding or loan company
- Do not use the provider wording. Use the loan-company template.
- State that the firm represents the client in the personal injury matter and identify the
  incident date.
- State the current payoff from the payoff letter or the CMS when it supports it.
- Request the user's percentage reduction of **interest** charges only, not principal,
  unless the user explicitly says otherwise.
- Explain that the reduction is meant to maximize the client's net recovery and resolve the
  matter promptly.
- Request a breakdown of principal and accrued interest and a revised payoff that reflects the
  reduction, plus written confirmation of any approved reduction.
- If the payoff letter doesn't split principal and interest, don't invent the split. Ask for it.
- If the payoff is date-sensitive or expired, say so and use the most current supported amount.

## Preserve formatting

Fill in the approved template; don't retype the letter. Change only the case- and entity-specific
fields unless the user asks for wording changes. Keep the letterhead, footer, paragraph structure,
fonts, spacing, margins, page size, signature block, contact information and acceptance section
exactly as they are. Never substitute a typed signature, a different logo or a different font.

## Output and QA

1. Render each drafted document and inspect it before converting.
2. Convert to PDF, then render the PDF and check for clipping, overlap, a missing signature or logo,
   changed fonts or layout, a broken footer, or unexpected page breaks.
3. Keep the one-page layout when the data fits. Don't shrink or reflow it unnecessarily.
4. Deliver PDFs by default. Keep editable copies only when asked.
5. Name each PDF exactly `Reduction Request - Provider Name - Client Name.pdf`. For a funding
   company, its name goes in the Provider Name position. Never append IDs, dates or version labels.

## Final response

One link per PDF, naming the entity and the requested payoff or reduction. Mention held or excluded
providers only when it helps confirm they were left out on purpose.
