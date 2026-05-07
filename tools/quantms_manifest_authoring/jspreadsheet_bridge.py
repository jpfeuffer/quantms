#!/usr/bin/env python3
"""
jspreadsheet bridge for translating between JavaScript spreadsheet events and WizardState.

This bridge handles:
- Converting WizardState to jspreadsheet-ce data format for multiple entity types (runs, samples, mixtures)
- Syncing cell edits back to wizard via the adapter
- Handling row deletions and appends
- Providing column configuration for dropdown support
"""

from typing import Any, Dict, Set, Literal, Optional
from gui_wizard_state import WizardState
from spreadsheet_adapter import (
    SpreadsheetAdapter,
    SampleFieldInfo,
    MixtureFieldInfo,
    RunFieldInfo,
    GroupFieldInfo,
    ModificationFieldInfo,
    AssignmentFieldInfo,
    AssignmentSpreadsheetRow,
    ModificationSpreadsheetRow,
)
from spreadsheet_column_config import ColumnConfigBuilder
from ontology_provider import OntologyOptionProvider


class JSpreadsheetBridge:
    """
    Bridge between jspreadsheet-ce (JavaScript) and WizardState (Python).

    Handles initialization of spreadsheet data from wizard state and
    synchronization of edits/deletions back to the wizard for multiple entity types
    (runs, samples, mixtures, assignments).
    """

    MODIFICATION_ONTOLOGY_EDITABLE_FIELDS = {"mode", "profile"}

    @classmethod
    def _row_kind_is_ontology(cls, kind: Any) -> bool:
        """Return True when a modification row should be treated as ontology-backed."""
        return isinstance(kind, str) and kind.strip().lower() == "ontology"

    def __init__(
        self,
        wizard: WizardState,
        column_config_builder=None,
        entity_type: Literal["runs", "samples", "mixtures", "assignments", "modifications", "groups"] = "runs",
    ):
        """Initialize bridge with wizard state.

        Args:
            wizard: WizardState instance
            column_config_builder: Optional ColumnConfigBuilder for dropdown config.
                                  If None, creates a new one.
            entity_type: Type of entity ('runs', 'samples', 'mixtures', 'assignments', 'modifications', or 'groups'). Default is 'runs'.
        """
        self.wizard = wizard
        self.entity_type = entity_type
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
        if self.entity_type == "runs":
            headers = self.adapter.get_column_headers()
            rows = self.adapter.wizard_to_spreadsheet()
            data = [[getattr(row, field, None) for field in headers] for row in rows]
        elif self.entity_type == "samples":
            headers = self.adapter.get_column_headers_samples()
            rows = self.adapter.wizard_samples_to_spreadsheet()
            data = [[getattr(row, field, None) for field in headers] for row in rows]
        elif self.entity_type == "mixtures":
            headers = self.adapter.get_column_headers_mixtures()
            rows = self.adapter.wizard_mixtures_to_spreadsheet()
            # For mixtures, flatten channels into individual columns
            data = []
            for row in rows:
                row_data = [row.id]  # First column is always id
                # Then add channel values in order of headers (skipping 'id')
                for channel in headers[1:]:
                    row_data.append(row.channels.get(channel, None))
                data.append(row_data)
        elif self.entity_type == "assignments":
            # Get headers based on quantification method
            quant_method = self.wizard.experiment.get("quantification_method") if self.wizard.experiment else None
            headers = self.adapter.get_assignment_headers_for_quantification(quant_method)
            rows = self.adapter.wizard_assignments_to_spreadsheet(quant_method)
            data = [[getattr(row, field, None) for field in headers] for row in rows]
        elif self.entity_type == "modifications":
            headers = self.adapter.get_column_headers_modifications()
            rows = self.adapter.wizard_modifications_to_spreadsheet()
            data = [[getattr(row, field, None) for field in headers] for row in rows]
        elif self.entity_type == "groups":
            headers = self.adapter.get_column_headers_groups()
            rows = self.adapter.wizard_groups_to_spreadsheet()
            data = [[getattr(row, field, None) for field in headers] for row in rows]
        else:
            raise ValueError(f"Unknown entity type: {self.entity_type}")

        # Build column configuration with dropdown support
        column_config = self.column_config_builder.build_column_config(
            headers,
            field_info_getter=lambda field: self._get_field_info(field),
            dropdown_sources=self._get_dropdown_sources(headers),
        )

        spreadsheet_data = {
            "headers": headers,
            "data": data,
            "column_config": column_config,
        }

        if self.entity_type == "modifications":
            spreadsheet_data["read_only_cells"] = self._get_modification_read_only_cells(headers, rows)
        elif self.entity_type == "groups":
            spreadsheet_data["read_only_cells"] = [
                {"row": row_index, "col": col_index}
                for row_index, _ in enumerate(rows)
                for col_index, _ in enumerate(headers)
            ]
            spreadsheet_data["allow_delete_row"] = False

        return spreadsheet_data

    def _is_locked_ontology_modification_field(self, row: ModificationSpreadsheetRow, field_name: str) -> bool:
        """Return True when an ontology-backed modification field must stay read-only in the sheet."""
        return self._row_kind_is_ontology(row.kind) and field_name not in self.MODIFICATION_ONTOLOGY_EDITABLE_FIELDS

    def _get_modification_read_only_cells(
        self,
        headers: list[str],
        rows: list[ModificationSpreadsheetRow],
    ) -> list[dict[str, int]]:
        """Return per-cell read-only metadata for ontology-backed modification rows."""
        read_only_cells: list[dict[str, int]] = []
        for row_index, row in enumerate(rows):
            for col_index, field_name in enumerate(headers):
                if self._is_locked_ontology_modification_field(row, field_name):
                    read_only_cells.append({"row": row_index, "col": col_index})
        return read_only_cells


    def _get_field_info(self, field: str) -> Dict[str, Any]:
        """Get field info for the current entity type."""
        if self.entity_type == "runs":
            return RunFieldInfo.get_field_info(field)
        elif self.entity_type == "samples":
            return SampleFieldInfo.get_field_info(field)
        elif self.entity_type == "mixtures":
            if field == "id":
                return MixtureFieldInfo.get_field_info(field)
            return {
                "type": "str",
                "required": False,
                "description": f"Sample assigned to channel {field}",
            }
        elif self.entity_type == "assignments":
            return AssignmentFieldInfo.get_field_info(field)
        elif self.entity_type == "modifications":
            return ModificationFieldInfo.get_field_info(field)
        elif self.entity_type == "groups":
            return GroupFieldInfo.get_field_info(field)
        else:
            raise ValueError(f"Unknown entity type: {self.entity_type}")

    def _get_dropdown_sources(self, headers: list[str]) -> Dict[str, list[dict[str, str]]]:
        """Get explicit dropdown sources for entity-specific columns."""
        if self.entity_type == "mixtures":
            sample_options = [{"id": sample["id"], "name": sample["id"]} for sample in self.wizard.samples]
            return {header: sample_options for header in headers if header != "id"}
        elif self.entity_type == "runs":
            group_options = [{"id": group["id"], "name": group["id"]} for group in self.wizard.groups]
            return {"group_id": group_options} if group_options else {}
        elif self.entity_type == "assignments":
            sources = {}
            if "sample" in headers:
                sample_options = [{"id": sample["id"], "name": sample["id"]} for sample in self.wizard.samples]
                sources["sample"] = sample_options
            if "mixture" in headers:
                mixture_options = [{"id": mixture["id"], "name": mixture["id"]} for mixture in self.wizard.mixtures]
                sources["mixture"] = mixture_options
            return sources
        elif self.entity_type == "modifications":
            return {
                "mode": [
                    {"id": "fixed", "name": "fixed"},
                    {"id": "variable", "name": "variable"},
                ],
                "kind": [
                    {"id": "ontology", "name": "ontology"},
                    {"id": "custom", "name": "custom"},
                ],
            }
        else:
            return {}

    def get_row_count(self) -> int:
        """Return the number of rows managed by the current bridge."""
        if self.entity_type == "runs":
            return len(self.wizard.runs)
        if self.entity_type == "samples":
            return len(self.wizard.samples)
        if self.entity_type == "mixtures":
            return len(self.wizard.mixtures)
        if self.entity_type == "assignments":
            return len(self.wizard.runs)
        if self.entity_type == "modifications":
            return len(self.wizard.modifications)
        if self.entity_type == "groups":
            return len(self.wizard.groups)
        raise ValueError(f"Unknown entity type: {self.entity_type}")

    def sync_from_spreadsheet_data(self, spreadsheet_data: list[list[Any]]) -> None:
        """Synchronize a full worksheet snapshot back into wizard state."""
        if not isinstance(spreadsheet_data, list):
            return

        if self.entity_type == "groups":
            return

        if self.entity_type == "runs":
            rows = self.adapter.wizard_to_spreadsheet()
            headers = self.adapter.get_column_headers()
            for row_index, row_data in enumerate(spreadsheet_data[: len(rows)]):
                if not isinstance(row_data, (list, tuple)):
                    continue
                row = rows[row_index]
                for col_index, field_name in enumerate(headers[: len(row_data)]):
                    value = row_data[col_index]
                    if field_name == "fraction" and isinstance(value, str) and value.strip() != "":
                        value = int(value)
                    if field_name != "file" and value == "":
                        value = None
                    row.update(**{field_name: value})
            self.adapter.spreadsheet_to_wizard(rows)
            return

        if self.entity_type == "samples":
            rows = self.adapter.wizard_samples_to_spreadsheet()
            headers = self.adapter.get_column_headers_samples()
            for row_index, row_data in enumerate(spreadsheet_data[: len(rows)]):
                if not isinstance(row_data, (list, tuple)):
                    continue
                row = rows[row_index]
                for col_index, field_name in enumerate(headers[: len(row_data)]):
                    value = row_data[col_index]
                    if field_name in {"biological_replicate", "technical_replicate"}:
                        if value == "":
                            value = None
                        elif isinstance(value, str):
                            value = int(value)
                    elif value == "":
                        value = None
                    row.update(**{field_name: value})
            self.adapter.sync_sample_edits(rows)
            return

        if self.entity_type == "mixtures":
            rows = self.adapter.wizard_mixtures_to_spreadsheet()
            headers = self.adapter.get_column_headers_mixtures()
            for row_index, row_data in enumerate(spreadsheet_data[: len(rows)]):
                if not isinstance(row_data, (list, tuple)):
                    continue
                row = rows[row_index]
                channels = {}
                for col_index, field_name in enumerate(headers[: len(row_data)]):
                    value = row_data[col_index]
                    if field_name == "id":
                        row.id = value
                    elif value not in (None, ""):
                        channels[field_name] = value
                row.channels = channels
            self.adapter.sync_mixture_edits(rows)
            return

        if self.entity_type == "assignments":
            quant_method = self.wizard.experiment.get("quantification_method") if self.wizard.experiment else None
            rows = self.adapter.wizard_assignments_to_spreadsheet(quant_method)
            headers = self.adapter.get_assignment_headers_for_quantification(quant_method)
            for row_index, row_data in enumerate(spreadsheet_data[: len(rows)]):
                if not isinstance(row_data, (list, tuple)):
                    continue
                row = rows[row_index]
                for col_index, field_name in enumerate(headers[: len(row_data)]):
                    value = row_data[col_index]
                    # Ignore run_file edits - it is read-only and derived from run state
                    if field_name == "run_file":
                        continue
                    if value == "":
                        value = None
                    row.update(**{field_name: value})
            self.adapter.sync_assignment_edits(rows, quant_method)
            return

        if self.entity_type == "modifications":
            rows = self.adapter.wizard_modifications_to_spreadsheet()
            headers = self.adapter.get_column_headers_modifications()
            for row_index, row_data in enumerate(spreadsheet_data[: len(rows)]):
                if not isinstance(row_data, (list, tuple)):
                    continue
                row = rows[row_index]
                row_was_ontology = self._row_kind_is_ontology(row.kind)
                for col_index, field_name in enumerate(headers[: len(row_data)]):
                    if row_was_ontology and field_name not in self.MODIFICATION_ONTOLOGY_EDITABLE_FIELDS:
                        continue
                    value = row_data[col_index]
                    if field_name in {"mass_shift"}:
                        if value == "":
                            value = None
                        elif isinstance(value, str):
                            value = float(value)
                    elif field_name in {"mode", "kind", "name", "ontology_id", "residues", "term_specificity", "profile"} and value == "":
                        value = None
                    row.update(**{field_name: value})
            self.adapter.sync_modification_edits(rows)
            return

        if self.entity_type == "groups":
            return

        raise ValueError(f"Unknown entity type: {self.entity_type}")


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
        if self.entity_type == "runs":
            self._handle_cell_edit_runs(row_index, col_index, new_value)
        elif self.entity_type == "samples":
            self._handle_cell_edit_samples(row_index, col_index, new_value)
        elif self.entity_type == "mixtures":
            self._handle_cell_edit_mixtures(row_index, col_index, new_value)
        elif self.entity_type == "assignments":
            self._handle_cell_edit_assignments(row_index, col_index, new_value)
        elif self.entity_type == "modifications":
            self._handle_cell_edit_modifications(row_index, col_index, new_value)
        elif self.entity_type == "groups":
            return
        else:
            raise ValueError(f"Unknown entity type: {self.entity_type}")

    def _handle_cell_edit_runs(self, row_index: int, col_index: int, new_value: Any) -> None:
        """Handle cell edit for runs."""
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
        elif field_name == "group_id" and (new_value is None or new_value == ""):
            new_value = None

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

    def _handle_cell_edit_samples(self, row_index: int, col_index: int, new_value: Any) -> None:
        """Handle cell edit for samples."""
        headers = self.adapter.get_column_headers_samples()
        field_name = headers[col_index]

        # Get current rows and update the edited cell
        current_rows = self.adapter.wizard_samples_to_spreadsheet()

        if row_index < 0 or row_index >= len(current_rows):
            raise ValueError(f"Row index {row_index} out of range")

        edited_row = current_rows[row_index]

        # Convert value type based on field
        if field_name in ("biological_replicate", "technical_replicate") and new_value is not None:
            if isinstance(new_value, str) and new_value.strip() == "":
                new_value = None
            elif new_value is not None:
                try:
                    new_value = int(new_value)
                except (ValueError, TypeError):
                    raise ValueError(f"{field_name} must be an integer, got: {new_value}")
        elif field_name == "id" and (new_value is None or new_value == ""):
            raise ValueError("Sample ID is required")

        # Update the row
        edited_row.update(**{field_name: new_value})

        # Validate
        edited_row.validate()

        # Sync back to wizard
        current_rows[row_index] = edited_row
        self.adapter.sync_sample_edits(current_rows)

    def _handle_cell_edit_mixtures(self, row_index: int, col_index: int, new_value: Any) -> None:
        """Handle cell edit for mixtures."""
        headers = self.adapter.get_column_headers_mixtures()
        field_name = headers[col_index]

        # Get current rows and update the edited cell
        current_rows = self.adapter.wizard_mixtures_to_spreadsheet()

        if row_index < 0 or row_index >= len(current_rows):
            raise ValueError(f"Row index {row_index} out of range")

        edited_row = current_rows[row_index]

        if field_name == "id" and (new_value is None or new_value == ""):
            raise ValueError("Mixture ID is required")

        # If field_name is a channel, update the channels dict
        if field_name != "id":
            # It's a channel - update channels dict
            if edited_row.channels is None:
                edited_row.channels = {}
            if new_value is None or (isinstance(new_value, str) and new_value.strip() == ""):
                edited_row.channels.pop(field_name, None)
            else:
                edited_row.channels[field_name] = new_value
        else:
            # Regular field update
            edited_row.update(**{field_name: new_value})

        # Validate
        edited_row.validate()

        # Sync back to wizard
        current_rows[row_index] = edited_row
        self.adapter.sync_mixture_edits(current_rows)

    def _handle_cell_edit_assignments(self, row_index: int, col_index: int, new_value: Any) -> None:
        """Handle cell edit for assignments."""
        quant_method = self.wizard.experiment.get("quantification_method") if self.wizard.experiment else None
        headers = self.adapter.get_assignment_headers_for_quantification(quant_method)
        field_name = headers[col_index]

        # Get current rows and update the edited cell
        current_rows = self.adapter.wizard_assignments_to_spreadsheet(quant_method)

        if row_index < 0 or row_index >= len(current_rows):
            raise ValueError(f"Row index {row_index} out of range")

        edited_row = current_rows[row_index]

        # run_file is read-only, cannot edit
        if field_name == "run_file":
            raise ValueError("Run file is read-only")

        # Update the assignment fields
        if new_value is None or (isinstance(new_value, str) and new_value.strip() == ""):
            value = None
        else:
            value = new_value

        edited_row.update(**{field_name: value})

        # Validate
        edited_row.validate()

        # Sync back to wizard
        current_rows[row_index] = edited_row
        self.adapter.sync_assignment_edits(current_rows, quant_method)

    def _handle_cell_edit_modifications(self, row_index: int, col_index: int, new_value: Any) -> None:
        """Handle cell edit for modifications."""
        headers = self.adapter.get_column_headers_modifications()
        field_name = headers[col_index]

        current_rows = self.adapter.wizard_modifications_to_spreadsheet()

        if row_index < 0 or row_index >= len(current_rows):
            raise ValueError(f"Row index {row_index} out of range")

        edited_row = current_rows[row_index]

        if self._is_locked_ontology_modification_field(edited_row, field_name):
            raise ValueError(
                "Ontology-backed modifications can only edit 'mode' and 'profile' in the sheet. "
                "Delete and re-add the modification to change curated fields."
            )

        if field_name == "mass_shift" and new_value is not None:
            if isinstance(new_value, str) and new_value.strip() == "":
                new_value = None
            elif new_value is not None:
                try:
                    new_value = float(new_value)
                except (ValueError, TypeError):
                    raise ValueError(f"mass_shift must be a number, got: {new_value}")
        elif field_name in {"max_occurrences", "binary_group", "min_occurrences", "distance_from_terminus"} and new_value is not None:
            if isinstance(new_value, str) and new_value.strip() == "":
                new_value = None
            elif new_value is not None:
                try:
                    new_value = int(new_value)
                except (ValueError, TypeError):
                    raise ValueError(f"{field_name} must be an integer, got: {new_value}")

        if field_name in self._dropdown_constraint_cache:
            self._validate_dropdown_value(field_name, new_value)

        edited_row.update(**{field_name: new_value})
        edited_row.validate()

        current_rows[row_index] = edited_row
        self.adapter.sync_modification_edits(current_rows)

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

        if self.entity_type == "modifications":
            constraints["mode"] = {"fixed", "variable"}
            constraints["kind"] = {"ontology", "custom"}

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
        if self.entity_type == "runs":
            self.wizard.remove_run(row_index)
        elif self.entity_type == "samples":
            self.wizard.remove_sample(row_index)
        elif self.entity_type == "mixtures":
            self.wizard.remove_mixture(row_index)
        elif self.entity_type == "assignments":
            # Assignments are a linkage view over runs, so deletion is a no-op.
            # Assignment rows cannot be directly deleted; they reflect run state.
            pass
        elif self.entity_type == "modifications":
            if row_index < 0 or row_index >= len(self.wizard.modifications):
                raise IndexError(f"Row index {row_index} out of range")
            del self.wizard.modifications[row_index]
        elif self.entity_type == "groups":
            pass
        else:
            raise ValueError(f"Unknown entity type: {self.entity_type}")

    def handle_row_append(self, file_path: str) -> None:
        """
        Handle appending a new row (e.g., from file picker).

        Args:
            file_path: File path to add as new run

        Raises:
            ValueError: If file path is invalid
        """
        if self.entity_type != "runs":
            raise NotImplementedError(
                f"row append is only supported for runs, not {self.entity_type}"
            )
        self.wizard.add_run(file=file_path)
