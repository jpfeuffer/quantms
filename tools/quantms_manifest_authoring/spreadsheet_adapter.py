#!/usr/bin/env python3
"""
Spreadsheet adapter for translating between WizardState runs and spreadsheet rows.

This adapter provides a reusable contract for mapping between the authoritative
WizardState (list of run dicts) and flat spreadsheet rows that can be edited
and synchronized back.

Key principles:
- WizardState is the authoritative source (never modified by adapter except via explicit sync)
- Spreadsheet rows are ephemeral views that can be edited and synced back
- Column order is predictable for consistent UI rendering
- Required fields (especially 'file') are validated
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional


class RunFieldInfo:
    """Metadata about run fields for the adapter."""

    FIELD_METADATA = {
        "file": {
            "type": "str",
            "required": True,
            "description": "Path or URI to raw/mzML file",
        },
        "fraction": {
            "type": "int",
            "required": False,
            "description": "Fraction number",
        },
        "instrument": {
            "type": "str",
            "required": False,
            "description": "Instrument name",
        },
    }

    @staticmethod
    def get_all_fields() -> List[str]:
        """Get all available field names."""
        return list(RunFieldInfo.FIELD_METADATA.keys())

    @staticmethod
    def get_field_info(field: str) -> Dict[str, Any]:
        """Get metadata for a specific field."""
        if field not in RunFieldInfo.FIELD_METADATA:
            raise ValueError(f"Unknown field: {field}")
        return RunFieldInfo.FIELD_METADATA[field]

    @staticmethod
    def get_required_fields() -> List[str]:
        """Get list of required fields."""
        return [
            field
            for field, info in RunFieldInfo.FIELD_METADATA.items()
            if info["required"]
        ]


@dataclass
class SpreadsheetRow:
    """Represents a single spreadsheet row corresponding to a run."""

    file: Optional[str] = None
    fraction: Optional[int] = None
    instrument: Optional[str] = None
    row_index: int = 0

    @classmethod
    def from_wizard_run(cls, run: Dict[str, Any], row_index: int = 0) -> "SpreadsheetRow":
        """
        Create a spreadsheet row from a wizard run dict.

        Args:
            run: Dictionary from WizardState.runs
            row_index: Index of this row (for reference)

        Returns:
            SpreadsheetRow instance
        """
        return cls(
            file=run.get("file"),
            fraction=run.get("fraction"),
            instrument=run.get("instrument"),
            row_index=row_index,
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert row to dict, excluding None values.

        Returns:
            Dictionary suitable for wizard.update_run()
        """
        result = {}
        if self.file is not None:
            result["file"] = self.file
        if self.fraction is not None:
            result["fraction"] = self.fraction
        if self.instrument is not None:
            result["instrument"] = self.instrument
        return result

    def update(self, **kwargs) -> None:
        """Update row fields."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def validate(self) -> None:
        """
        Validate row against field constraints.

        Raises:
            ValueError: If validation fails
        """
        # Check required fields
        if not self.file:
            raise ValueError("Required field 'file' is missing")

        # Type coercion and validation
        if self.fraction is not None:
            # Treat empty string as None
            if isinstance(self.fraction, str) and self.fraction.strip() == "":
                self.fraction = None
            elif isinstance(self.fraction, str):
                try:
                    self.fraction = int(self.fraction)
                except (ValueError, TypeError):
                    raise ValueError(f"Fraction must be an integer, got: {self.fraction}")

    def is_empty_optional_field(self, field: str) -> bool:
        """Check if an optional field is empty (None or empty string)."""
        value = getattr(self, field, None)
        return value is None or value == ""


class SpreadsheetAdapter:
    """
    Adapter for translating between WizardState and spreadsheet rows.

    Keeps WizardState as the authoritative source. The adapter converts the
    state to/from spreadsheet rows which can be edited and synced.
    """

    def __init__(self, wizard):
        """
        Initialize adapter with a wizard state.

        Args:
            wizard: WizardState instance to operate on
        """
        self.wizard = wizard

    def get_column_headers(self) -> List[str]:
        """
        Get column headers in predictable order (run-level fields only).

        Returns:
            List of field names representing columns
        """
        # Always put 'file' first, then others in consistent order
        return ["file", "fraction", "instrument"]

    def wizard_to_spreadsheet(self) -> List[SpreadsheetRow]:
        """
        Convert WizardState.runs to spreadsheet rows.

        Returns:
            List of SpreadsheetRow instances (one per run)
        """
        rows = []
        for idx, run in enumerate(self.wizard.runs):
            row = SpreadsheetRow.from_wizard_run(run, row_index=idx)
            rows.append(row)
        return rows

    def spreadsheet_row_to_wizard_run(self, row: SpreadsheetRow) -> Dict[str, Any]:
        """
        Convert a spreadsheet row to a wizard run dict.

        Args:
            row: SpreadsheetRow to convert

        Returns:
            Dictionary suitable for WizardState
        """
        return row.to_dict()

    def spreadsheet_to_wizard(self, rows: List[SpreadsheetRow]) -> None:
        """
        Synchronize spreadsheet rows back to WizardState.

        This validates all rows and updates the wizard in-place.

        Args:
            rows: List of SpreadsheetRow instances to sync

        Raises:
            ValueError: If row count differs from wizard or validation fails
        """
        # Validate row count matches
        if len(rows) != len(self.wizard.runs):
            raise ValueError(
                f"row count mismatch: spreadsheet has {len(rows)} rows but wizard has {len(self.wizard.runs)} runs"
            )

        # Validate all rows
        for row in rows:
            row.validate()

        # Synchronize each row
        for idx, row in enumerate(rows):
            # Get the updated fields from the spreadsheet row
            updated_fields = {}

            for field in RunFieldInfo.get_all_fields():
                if field == "file":
                    # File is always required
                    updated_fields[field] = getattr(row, field)
                else:
                    # For optional fields, only include if not None/empty
                    value = getattr(row, field)
                    if value is not None and (not isinstance(value, str) or value.strip() != ""):
                        updated_fields[field] = value

            # Update the run in wizard (only with fields that have values)
            self.wizard.update_run(idx, **updated_fields)

            # Remove fields that were explicitly cleared (None or empty string for optional fields)
            for field in RunFieldInfo.get_all_fields():
                if field != "file":  # Never remove the required file field
                    value = getattr(row, field)
                    # If the field is None or empty string, remove it from wizard run
                    if value is None or (isinstance(value, str) and value.strip() == ""):
                        # Use public API to remove field
                        self.wizard.clear_run_field(idx, field)

    def get_row_by_index(self, index: int) -> Optional[SpreadsheetRow]:
        """
        Get a specific spreadsheet row by index.

        Args:
            index: Index of the row

        Returns:
            SpreadsheetRow or None if out of range
        """
        rows = self.wizard_to_spreadsheet()
        if 0 <= index < len(rows):
            return rows[index]
        return None

    def copy_field_down(
        self,
        field: str,
        from_row_index: int,
        to_row_index: Optional[int] = None,
    ) -> None:
        """
        Copy a field value down (fill-down) from one row to subsequent rows.

        This is groundwork for spreadsheet-style drag-copy behavior.
        The value from from_row_index is copied to all rows from from_row_index+1
        to to_row_index (inclusive). If to_row_index is None, copies to end of rows.

        Args:
            field: Field name to copy (must be a valid field)
            from_row_index: Starting row index (source of value)
            to_row_index: Ending row index (inclusive). If None, copies to last row.

        Raises:
            ValueError: If field is invalid, from_row_index is out of range, or range is invalid
        """
        # Validate field
        if field not in RunFieldInfo.get_all_fields():
            raise ValueError(
                f"Unknown field '{field}'. Valid fields: {RunFieldInfo.get_all_fields()}"
            )

        # Validate from_row_index
        if from_row_index < 0 or from_row_index >= len(self.wizard.runs):
            raise ValueError(
                f"from_row_index {from_row_index} out of range (0-{len(self.wizard.runs) - 1})"
            )

        # Default to_row_index to last row
        if to_row_index is None:
            to_row_index = len(self.wizard.runs) - 1

        # Validate to_row_index
        if to_row_index < from_row_index:
            raise ValueError(
                f"to_row_index {to_row_index} must be >= from_row_index {from_row_index}"
            )
        if to_row_index >= len(self.wizard.runs):
            raise ValueError(
                f"to_row_index {to_row_index} out of range (0-{len(self.wizard.runs) - 1})"
            )

        # Get the value from the source row
        source_run = self.wizard.runs[from_row_index]
        value_to_copy = source_run.get(field)

        # Copy the value to all target rows
        for idx in range(from_row_index + 1, to_row_index + 1):
            if value_to_copy is not None:
                self.wizard.update_run(idx, **{field: value_to_copy})
            else:
                # If source value is None, remove field from target if present
                self.wizard.clear_run_field(idx, field)
