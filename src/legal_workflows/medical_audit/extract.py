"""Turn CMS contacts into audit rows: filter Medical Providers and flatten custom fields."""

from __future__ import annotations

from datetime import date
from typing import Any

MEDICAL_PROVIDER_ROLE = "medical provider"

# Columns pulled from the contact record itself.
CONTACT_COLUMNS = {
    "Provider": "name",
    "Relationship": "relationship",
    "Role to Case": "role_to_case",
    "Notes": "notes",
    "Contact ID": "contact_id",
}

SOURCE_COLUMNS = [
    "Provider",
    "Provider Type",
    "Relationship",
    "LOP",
    "Role to Case",
    "Treatment Status",
    "Notes",
    "Contact ID",
]

AUDIT_COLUMNS = ["Audit Status", "Issue / Discrepancy", "Follow-up Needed", "Audit Notes"]
AUDIT_STATUS_OPTIONS = ["Not Reviewed", "Reviewed - No Issue", "Reviewed - Issue"]
DEFAULT_AUDIT_STATUS = AUDIT_STATUS_OPTIONS[0]


def is_medical_provider(contact: dict) -> bool:
    role = contact.get("role") or contact.get("type") or ""
    return str(role).strip().casefold() == MEDICAL_PROVIDER_ROLE


def field_value(field: dict) -> Any:
    """Return a display value for one custom field, or None when it is empty."""
    value = field.get("value")
    if value is None or value == "":
        return None

    kind = (field.get("type") or "").casefold()
    if kind == "contact_reference":
        if isinstance(value, dict):
            return value.get("name") or value.get("contact_id")
        return value
    if kind == "date":
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return str(value)
    if kind == "number":
        return int(value) if float(value).is_integer() else float(value)
    if kind == "decimal":
        return float(value)
    # short_text, long_text, dropdown, general and anything unknown: keep as text.
    return str(value) if not isinstance(value, (int, float)) else value


def custom_fields(contact: dict) -> dict[str, Any]:
    """Populated custom fields keyed by their displayed label."""
    fields = contact.get("ad_hoc_fields") or []
    out: dict[str, Any] = {}
    for field in fields:
        if not isinstance(field, dict) or not field.get("label"):
            continue
        value = field_value(field)
        if value is not None:
            out[str(field["label"])] = value
    return out


def build_rows(contacts: list[dict] | None) -> tuple[list[str], list[dict[str, Any]]]:
    """Return (columns, rows) for every Medical Provider contact.

    Columns are the common source columns, then any extra populated custom fields in
    the order first seen, then the editable audit columns.
    """
    providers = [c for c in (contacts or []) if isinstance(c, dict) and is_medical_provider(c)]

    rows: list[dict[str, Any]] = []
    extra_columns: list[str] = []
    for contact in providers:
        row: dict[str, Any] = {}
        for column, key in CONTACT_COLUMNS.items():
            value = contact.get(key)
            row[column] = None if value == "" else value
        for label, value in custom_fields(contact).items():
            row[label] = value
            if label not in SOURCE_COLUMNS and label not in extra_columns:
                extra_columns.append(label)
        row["Audit Status"] = DEFAULT_AUDIT_STATUS
        rows.append(row)

    return SOURCE_COLUMNS + extra_columns + AUDIT_COLUMNS, rows
