#!/usr/bin/env python3
"""
jspreadsheet bridge for translating between JavaScript spreadsheet events and WizardState.

This bridge handles:
- Converting WizardState to jspreadsheet-ce data format
- Syncing cell edits back to wizard via the adapter
- Handling row deletions and appends
- Providing column configuration for dropdown support
"""

from typing import Any, Dict, Set
from gui_wizard_state import WizardState
from spreadsheet_adapter import SpreadsheetAdapter
from spreadsheet_column_config import ColumnConfigBuilder
from ontology_provider import OntologyOptionProvider


class JSpreadsheetBridge:
    """
    Bridge between jspreadsheet-ce (JavaScript) and WizardState (Python).

    Handles initialization of spreadsheet data from wizard state and
    synchronization of edits/deletions back to the wizard.
    """

    def __init__(self, wizard: WizardState, column_config_builder=None):
        """Initialize bridge with wizard state.

        Args:
            wizard: WizardState instance
            column_config_builder: Optional ColumnConfigBuilder for dropdown config.
                                  If None, creates a new one.
        """
        self.wizard = wizard
        self.adapter = SpreadsheetAdapter(wizard)
        self.column_config_builder = column_config_builder or ColumnConfigBuilder()
        self.option_provider = OntologyOptionProvider()
        self._dropdown_constraint_cache = self._build_dropdown_constraints()

    def get_spreadsheet_data(self) -> Dict[str, Any]:
        """
        Get data ready for jspreadsheet-ce initialization.

        Returns:
            Dict with 'headers', 'data', and 'column_config' keys for use in JS initialization.
            column_config describes which columns are dropdowns and their options.
        """
        headers = self.adapter.get_column_headers()
        rows = self.adapter.wizard_to_spreadsheet()

        # Convert rows to nested lists for jspreadsheet format
        data = []
        for row in rows:
            row_data = [getattr(row, field) for field in headers]
            data.append(row_data)

        # Build column configuration with dropdown support
        column_config = self.column_config_builder.build_column_config(
            headers,
            field_info_getter=self.adapter.get_field_info,
        )

        return {
            "headers": headers,
            "data": data,
            "column_config": column_config,
        }

    def handle_cell_edit(self, row_index: int, col_index: int, new_value: Any) -> None:
        """
        Handle a cell edit event from jspreadsheet.

        Args:
            row_index: Row index (0-based)
            col_index: Column index (0-based)
            new_value: New cell value

        Raises:
            ValueError: If validation fails
        """
        headers = self.adapter.get_column_headers()
        field_name = headers[col_index]

        # Get current rows and update the edited cell
        current_rows = self.adapter.wizard_to_spreadsheet()

        if row_index < 0 or row_index >= len(current_rows):
            raise ValueError(f"Row index {row_index} out of range")

        edited_row = current_rows[row_index]

        # Convert value type based on field
        if field_name == "fraction" and new_value is not None:
            if isinstance(new_value, str) and new_value.strip() == "":
                new_value = None
            elif new_value is not None:
                try:
                    new_value = int(new_value)
                except (ValueError, TypeError):
                    raise ValueError(f"Fraction must be an integer, got: {new_value}")
        elif field_name == "file" and (new_value is None or new_value == ""):
            raise ValueError("File path is required")

        # Validate dropdown constraints for allowed fields
        if field_name in self._dropdown_constraint_cache:
            self._validate_dropdown_value(field_name, new_value)

        # Update the row
        edited_row.update(**{field_name: new_value})

        # Validate
        edited_row.validate()

        # Sync back to wizard
        current_rows[row_index] = edited_row
        self.adapter.spreadsheet_to_wizard(current_rows)

    def _build_dropdown_constraints(self) -> Dict[str, Set[str]]:
        """
        Build a cache of dropdown constraints for validation.

        Returns:
            Dict mapping field names to set of allowed values.
        """
        constraints = {}

        # Get instrument options
        instrument_options = self.option_provider.get_options("instrument")
        if instrument_options:
            values = set()
            for opt in instrument_options:
                if isinstance(opt, dict):
                    values.add(opt.get("value") or opt.get("id"))
                elif isinstance(opt, str):
                    values.add(opt)
            values.discard(None)
            constraints["instrument"] = values

        return constraints

    def _validate_dropdown_value(self, field_name: str, value: Any) -> None:
        """
        Validate that a value is in the allowed set for a dropdown field.

        Args:
            field_name: Field name (e.g., 'instrument')
            value: Value to validate

        Raises:
            ValueError: If value is not in allowed set (and not empty/None for optional fields)
        """
        if field_name not in self._dropdown_constraint_cache:
            return

        allowed_values = self._dropdown_constraint_cache[field_name]

        # Empty/None is allowed for optional fields
        if value is None or (isinstance(value, str) and value.strip() == ""):
            return

        # Check if value is in allowed set
        if str(value) not in allowed_values:
            allowed_list = ", ".join(sorted(allowed_values))
            raise ValueError(
                f"Invalid value for {field_name}: '{value}'. "
                f"Allowed options: {allowed_list}"
            )

    def handle_row_delete(self, row_index: int) -> None:
        """
        Handle a row delete event from jspreadsheet.

        Args:
            row_index: Row index to delete (0-based)

        Raises:
            IndexError: If row index is out of range
        """
        self.wizard.remove_run(row_index)

    def handle_row_append(self, file_path: str) -> None:
        """
        Handle appending a new row (e.g., from file picker).

        Args:
            file_path: File path to add as new run

        Raises:
            ValueError: If file path is invalid
        """
        self.wizard.add_run(file=file_path)
