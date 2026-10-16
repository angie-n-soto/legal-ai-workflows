---
name: create-medical-case-audit
description: Create a formatted Excel medical-provider audit workbook from a case in a legal case management system (CMS). Use when the user asks to audit, review, export, or create a medical spreadsheet for a case or claim, for example "for case XYZ I need to do an audit, create spreadsheet" or "create the medical audit spreadsheet."
---

# Create Medical Case Audit

Create a review-ready `.xlsx` workbook from a case's Medical Provider records in the
case management system (CMS) and return a link that opens the file in a spreadsheet app.

> Portfolio note: this is a sanitized rebuild of an agent skill I wrote for a personal
> injury law firm. The original ran against a commercial legal CMS through an MCP
> connection in ChatGPT. Vendor-specific operations, firm configuration and all case data have been
> removed or replaced with generic placeholders. Python code that applies the same rules is
> in `src/legal_workflows/medical_audit/`.

## Resolve and retrieve the case

1. Use the CMS MCP connection. Before any other CMS call, load the MCP server's own usage
   and access rules and follow them.
2. Resolve the claim from the user's claim URL, numeric claim ID, or case name. If a
   claim URL contains an `id` query parameter, use that value as the claim ID. If a name
   matches more than one claim, ask the user to choose. Never guess.
3. Discover the MCP server's documented read tools before running anything. With a
   known claim ID, prefer the lightest endpoints that return the claim record and its
   contacts (without notes).
4. Retrieve the claim identity and claim contacts. Keep only contacts whose role/type is
   `Medical Provider` (case-insensitive).
5. Expand every populated custom ("ad hoc") field on each provider, using the field's
   displayed label. Guard every collection before iterating, and handle each documented
   value type: contact references, short and long text, general values, dropdowns,
   dates, numbers and decimals.

**Keep this workflow read-only.** Do not fetch claim notes, medical documents, client
medical details or unrelated contacts unless the user explicitly expands the scope.

## Build the audit workbook

Create one worksheet named `Medical Provider Audit` unless the user asks for a different
structure. Include:

- A title band with the case name, claim ID, provider count and source claim URL.
- One row per Medical Provider.
- Common source columns first: Provider, Provider Type, Relationship, LOP, Role to Case,
  Treatment Status, Notes, Contact ID.
- Any additional populated custom fields found on the case, without discarding or
  inventing values.
- Editable audit columns last: Audit Status, Issue / Discrepancy, Follow-up Needed,
  Audit Notes.

Leave missing source values blank. Default Audit Status to `Not Reviewed` with a dropdown
of `Not Reviewed`, `Reviewed - No Issue`, `Reviewed - Issue`. Use a Yes/No dropdown for
Follow-up Needed.

Format the data as a filterable table with frozen headers, readable column widths,
wrapped long text, alternating row bands and numeric IDs stored as numbers. Use a
clean, professional legal-audit style and keep the source URL as plain text.

Name the file `<Case_Name>_Medical_Provider_Audit.xlsx`, replacing only characters that
are invalid in filenames.

## Verify and deliver

Before exporting:

1. Inspect the populated range and reconcile the workbook's provider count with the
   retrieved records.
2. Scan for spreadsheet formula errors.
3. Render the whole worksheet and fix clipping, unreadable headers, overly wide columns
   or blank/broken regions.
4. Export one final `.xlsx` file and return its link.

Show a screenshot only when the user asks for one. If the case has no Medical Provider
contacts, still create the workbook with headers and a visible
`No medical providers found` notice. Never fabricate rows.
