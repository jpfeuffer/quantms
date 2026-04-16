#!/usr/bin/env python3
"""
jspreadsheet bridge for translating between JavaScript spreadsheet events and WizardState.

This bridge handles:
- Converting WizardState to jspreadsheet-ce data format
- Syncing cell edits back to wizard via the adapter
- Handling row deletions and appends
"""

from typing import Any, Dict
from gui_wizard_state import WizardState
from spreadsheet_adapter import SpreadsheetAdapter


class JSpreadsheetBridge:
    """
    Bridge between jspreadsheet-ce (JavaScript) and WizardState (Python).

    Handles initialization of spreadsheet data from wizard state and
    synchronization of edits/deletions back to the wizard.
    """

    def __init__(self, wizard: WizardState):
        """Initialize bridge with wizard state."""
        self.wizard = wizard
        self.adapter = SpreadsheetAdapter(wizard)

    def get_spreadsheet_data(self) -> Dict[str, Any]:
        """
        Get data ready for jspreadsheet-ce initialization.

        Returns:
            Dict with 'headers' and 'data' keys for use in JS initialization.
        """
        headers = self.adapter.get_column_headers()
        rows = self.adapter.wizard_to_spreadsheet()

        # Convert rows to nested lists for jspreadsheet format
        data = []
        for row in rows:
            row_data = [getattr(row, field) for field in headers]
            data.append(row_data)

        return {
            "headers": headers,
            "data": data,
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

        # Update the row
        edited_row.update(**{field_name: new_value})

        # Validate
        edited_row.validate()

        # Sync back to wizard
        current_rows[row_index] = edited_row
        self.adapter.spreadsheet_to_wizard(current_rows)

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
