"""Typed filter object shared by the analytics layer and the API."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Any, Iterable, Mapping


def _as_date(value: Any) -> date | None:
    """Coerce an ISO string / date / datetime to a ``date`` (None passes through)."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _as_tuple(value: Any) -> tuple[str, ...]:
    """Normalise a scalar or iterable of strings to a de-duplicated tuple."""
    if value is None or value == "":
        return ()
    if isinstance(value, str):
        items: Iterable[Any] = [part.strip() for part in value.split(",")]
    else:
        items = value
    seen: list[str] = []
    for item in items:
        text_value = str(item).strip()
        if text_value and text_value not in seen:
            seen.append(text_value)
    return tuple(seen)


@dataclass(frozen=True)
class Filters:
    """Analytical filter set propagated from the UI through the API to SQL.

    Attributes:
        from_date: Inclusive start of the operational-date window.
        to_date: Inclusive end of the operational-date window.
        tool_ids: Restrict to these tool ids.
        tool_family: Restrict to one equipment family.
        fab_site: Restrict to one fab site.
        shifts: Restrict to shift codes (A/B/C).
    """

    from_date: date | None = None
    to_date: date | None = None
    tool_ids: tuple[str, ...] = field(default_factory=tuple)
    tool_family: str | None = None
    fab_site: str | None = None
    shifts: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any] | None = None) -> "Filters":
        """Build a filter set from a loose mapping (query params, JSON, tests)."""
        mapping = mapping or {}
        return cls(
            from_date=_as_date(mapping.get("from_date")),
            to_date=_as_date(mapping.get("to_date")),
            tool_ids=_as_tuple(mapping.get("tool_ids")),
            tool_family=(mapping.get("tool_family") or None),
            fab_site=(mapping.get("fab_site") or None),
            shifts=_as_tuple(mapping.get("shifts")),
        )

    def with_overrides(self, **changes: Any) -> "Filters":
        """Return a copy with selected fields replaced (dates normalised)."""
        if "from_date" in changes:
            changes["from_date"] = _as_date(changes["from_date"])
        if "to_date" in changes:
            changes["to_date"] = _as_date(changes["to_date"])
        if "tool_ids" in changes:
            changes["tool_ids"] = _as_tuple(changes["tool_ids"])
        if "shifts" in changes:
            changes["shifts"] = _as_tuple(changes["shifts"])
        return replace(self, **changes)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation of the filters."""
        return {
            "from_date": self.from_date.isoformat() if self.from_date else None,
            "to_date": self.to_date.isoformat() if self.to_date else None,
            "tool_ids": list(self.tool_ids),
            "tool_family": self.tool_family,
            "fab_site": self.fab_site,
            "shifts": list(self.shifts),
        }

    def validate(self) -> None:
        """Raise ``ValueError`` when the filter combination cannot be answered."""
        if self.from_date and self.to_date and self.from_date > self.to_date:
            raise ValueError("from_date must be on or before to_date")
        bad_shifts = [s for s in self.shifts if s not in {"A", "B", "C"}]
        if bad_shifts:
            raise ValueError(f"unknown shift code(s): {', '.join(bad_shifts)}")
