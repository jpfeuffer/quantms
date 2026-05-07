#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pytest",
#   "nicegui",
#   "pyyaml",
# ]
# ///
"""
Tests for jspreadsheet bridge integration with the Runs step.

Tests the actual bridge behavior for:
- Initializing spreadsheet data from adapter rows
- Syncing cell edits back to wizard state
- Deleting rows from the spreadsheet
- Appending rows via file picker into the spreadsheet
"""

import pytest
import sys
import asyncio
from pathlib import Path
from types import SimpleNamespace
from copy import deepcopy
from unittest.mock import MagicMock, patch
from typing import Any, Dict, List

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from gui_wizard_state import WizardState
from spreadsheet_adapter import SpreadsheetAdapter, SpreadsheetRow
from jspreadsheet_bridge import JSpreadsheetBridge
from jspreadsheet_editor import JSpreadsheetEditor


class TestJSpreadsheetBridge:
    """Tests for the jspreadsheet bridge."""

    def test_bridge_initialization_converts_wizard_to_spreadsheet_format(self):
        """
        AC1: Bridge.get_spreadsheet_data() converts WizardState.runs to jspreadsheet format
        with headers and nested list data (run-level fields only).
        """
        wizard = WizardState()
        wizard.add_run(file="/data/s1.raw", fraction=1)
        wizard.add_run(file="/data/s2.raw", fraction=2, instrument="Orbitrap")

        bridge = JSpreadsheetBridge(wizard)
        data = bridge.get_spreadsheet_data()

        # Verify structure
        assert "headers" in data
        assert "data" in data
        assert data["headers"] == ["file", "fraction", "instrument", "group_id"]

        # Verify data rows
        assert len(data["data"]) == 2
        assert data["data"][0][0] == "/data/s1.raw"  # file column
        assert data["data"][0][1] == 1  # fraction column

        assert data["data"][1][0] == "/data/s2.raw"
        assert data["data"][1][1] == 2  # fraction column
        assert data["data"][1][2] == "Orbitrap"  # instrument column

    def test_bridge_handles_cell_edit_syncs_to_wizard(self):
        """
        AC2: Bridge.handle_cell_edit() updates wizard state via adapter when a cell is edited.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/original.raw", fraction=1)

        bridge = JSpreadsheetBridge(wizard)

        # Edit fraction in first row (column index 1)
        bridge.handle_cell_edit(row_index=0, col_index=1, new_value=5)

        # Verify wizard state updated
        assert wizard.runs[0]["fraction"] == 5

    def test_bridge_handles_cell_edit_validates_required_fields(self):
        """
        AC3: Bridge.handle_cell_edit() raises ValueError if required field (file) is cleared.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")

        bridge = JSpreadsheetBridge(wizard)

        # Try to clear the required file field
        with pytest.raises(ValueError, match="File path is required"):
            bridge.handle_cell_edit(row_index=0, col_index=0, new_value="")

    def test_bridge_handles_cell_edit_coerces_fraction_to_int(self):
        """
        AC4: Bridge.handle_cell_edit() coerces fraction to int or rejects invalid values.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")

        bridge = JSpreadsheetBridge(wizard)

        # Edit with string "3" in fraction column (index 1)
        bridge.handle_cell_edit(row_index=0, col_index=1, new_value="3")
        assert wizard.runs[0]["fraction"] == 3
        assert isinstance(wizard.runs[0]["fraction"], int)

        # Edit with invalid non-numeric string - should raise
        with pytest.raises(ValueError, match="Fraction must be an integer"):
            bridge.handle_cell_edit(row_index=0, col_index=1, new_value="not_a_number")

    def test_bridge_handles_row_delete(self):
        """
        AC5: Bridge.handle_row_delete() removes a row from the wizard.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/s1.raw")
        wizard.add_run(file="/data/s2.raw")

        assert len(wizard.runs) == 2

        bridge = JSpreadsheetBridge(wizard)
        bridge.handle_row_delete(row_index=0)

        assert len(wizard.runs) == 1
        assert wizard.runs[0]["file"] == "/data/s2.raw"

    def test_bridge_handles_row_append(self):
        """
        AC6: Bridge.handle_row_append() adds a new run to the wizard.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/existing.raw")

        bridge = JSpreadsheetBridge(wizard)
        bridge.handle_row_append("/data/new.raw")

        assert len(wizard.runs) == 2
        assert wizard.runs[1]["file"] == "/data/new.raw"

    def test_bridge_handles_multiple_cell_edits_sequence(self):
        """
        AC7: Bridge handles a sequence of cell edits correctly (e.g., user fills in fraction, instrument).
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")

        bridge = JSpreadsheetBridge(wizard)

        # Simulate user editing fraction column (index 1)
        bridge.handle_cell_edit(row_index=0, col_index=1, new_value=2)
        assert wizard.runs[0]["fraction"] == 2

        # Edit instrument column (index 2)
        bridge.handle_cell_edit(row_index=0, col_index=2, new_value="Orbitrap")
        assert wizard.runs[0]["instrument"] == "Orbitrap"

    def test_bridge_exposes_group_membership_dropdown_for_runs(self):
        """Runs spreadsheet should expose group membership as an editable dropdown."""
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")
        wizard.add_group(id="group_1", name="Replicate group", kind="replicate")

        bridge = JSpreadsheetBridge(wizard)
        data = bridge.get_spreadsheet_data()

        assert data["headers"] == ["file", "fraction", "instrument", "group_id"]
        assert data["data"][0][data["headers"].index("group_id")] is None
        assert data["column_config"]["group_id"]["type"] == "dropdown"
        assert data["column_config"]["group_id"]["source"] == [{"id": "group_1", "name": "group_1"}]

        bridge.handle_cell_edit(row_index=0, col_index=data["headers"].index("group_id"), new_value="group_1")

        assert wizard.runs[0]["group_id"] == "group_1"
        assert wizard.groups[0]["members"] == [wizard.runs[0]["id"]]

    def test_bridge_clear_optional_field_with_empty_string(self):
        """
        AC8: Bridge allows clearing optional fields by setting empty string.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", instrument="Orbitrap")

        bridge = JSpreadsheetBridge(wizard)

        # Clear instrument field (column 2)
        bridge.handle_cell_edit(row_index=0, col_index=2, new_value="")

        # Verify field was removed (not in the dict)
        assert "instrument" not in wizard.runs[0] or wizard.runs[0]["instrument"] is None

    def test_groups_bridge_exposes_read_only_groups_table(self):
        """Groups spreadsheet should render authoring groups from WizardState as read-only rows."""
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")
        wizard.add_group(id="group_1", name="Replicate group", kind="replicate")
        wizard.assign_run(run_index=0, group_id="group_1")

        bridge = JSpreadsheetBridge(wizard, entity_type="groups")
        data = bridge.get_spreadsheet_data()

        assert data["headers"] == ["id", "name", "kind", "members", "description"]
        assert data["data"][0][data["headers"].index("members")] == wizard.runs[0]["id"]
        assert data["read_only_cells"] == [
            {"row": 0, "col": 0},
            {"row": 0, "col": 1},
            {"row": 0, "col": 2},
            {"row": 0, "col": 3},
            {"row": 0, "col": 4},
        ]
        assert bridge.get_row_count() == 1

    def test_groups_bridge_sync_paths_do_not_mutate_wizard_groups(self):
        """Groups sync APIs should be inert in the read-only Phase 2 surface."""
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")
        wizard.add_group(id="group_1", name="Replicate group", kind="replicate")
        wizard.assign_run(run_index=0, group_id="group_1")

        initial_groups = deepcopy(wizard.groups)
        bridge = JSpreadsheetBridge(wizard, entity_type="groups")

        rows = bridge.adapter.wizard_groups_to_spreadsheet()
        rows[0].name = "Edited name"
        rows[0].members = "run_999"
        bridge.adapter.sync_group_edits(rows)
        assert wizard.groups == initial_groups

        spreadsheet_data = bridge.get_spreadsheet_data()
        mutated_snapshot = [row[:] for row in spreadsheet_data["data"]]
        mutated_snapshot[0][spreadsheet_data["headers"].index("name")] = "Edited name"
        mutated_snapshot[0][spreadsheet_data["headers"].index("members")] = "run_999"

        bridge.sync_from_spreadsheet_data(mutated_snapshot)

        assert wizard.groups == initial_groups

    def test_groups_editor_flush_pending_edits_does_not_sync_groups(self):
        """Groups editor flush should not attempt to round-trip read-only group data."""
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")
        wizard.add_group(id="group_1", name="Replicate group", kind="replicate")
        wizard.assign_run(run_index=0, group_id="group_1")

        initial_groups = deepcopy(wizard.groups)
        bridge = JSpreadsheetBridge(wizard, entity_type="groups")
        editor = JSpreadsheetEditor(wizard, MagicMock(), bridge=bridge, worksheet_name="Groups")
        editor.container = SimpleNamespace(html_id="groups-container")

        with patch("jspreadsheet_editor.context") as mock_context:
            mock_context.client.run_javascript = MagicMock(side_effect=AssertionError("run_javascript should not be called for groups flush"))

            result = asyncio.run(editor.flush_pending_edits())

        assert result == 0
        assert wizard.groups == initial_groups
        mock_context.client.run_javascript.assert_not_called()

    def test_bridge_edge_case_row_index_out_of_range(self):
        """
        AC9: Bridge raises ValueError for out-of-range row indices.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")

        bridge = JSpreadsheetBridge(wizard)

        with pytest.raises(ValueError, match="out of range"):
            bridge.handle_cell_edit(row_index=10, col_index=0, new_value="new_value")

    def test_modification_bridge_handles_missing_term_specificity(self):
        """Bridge should tolerate modifications that do not define term_specificity."""
        wizard = WizardState()
        wizard.add_modification(
            mode="fixed",
            kind="custom",
            name="Custom PTM",
            residues="C",
            profile="default",
        )

        bridge = JSpreadsheetBridge(wizard, entity_type="modifications")
        data = bridge.get_spreadsheet_data()

        assert "term_specificity" in data["headers"]
        assert data["data"][0][data["headers"].index("term_specificity")] is None

        bridge.sync_from_spreadsheet_data(data["data"])

        assert wizard.modifications[0].get("term_specificity") is None

    def test_modification_bridge_marks_ontology_cells_read_only_except_mode_and_profile(self):
        """Ontology-backed modification rows should lock curated fields in spreadsheet metadata."""
        wizard = WizardState()
        wizard.add_modification(
            mode="fixed",
            kind="ontology",
            name="Phospho",
            ontology_id="UNIMOD:21",
            residues="STY",
            term_specificity="none",
            mass_shift=79.966331,
            profile="default",
        )

        bridge = JSpreadsheetBridge(wizard, entity_type="modifications")
        data = bridge.get_spreadsheet_data()

        headers = data["headers"]
        editable_fields = {"mode", "profile"}
        locked_positions = {(cell["row"], cell["col"]) for cell in data["read_only_cells"]}

        for col_index, field_name in enumerate(headers):
            if field_name in editable_fields:
                assert (0, col_index) not in locked_positions
            else:
                assert (0, col_index) in locked_positions

    def test_modification_bridge_rejects_editing_locked_ontology_fields(self):
        """Ontology-backed modification rows should only permit mode/profile edits in the sheet."""
        wizard = WizardState()
        wizard.add_modification(
            mode="fixed",
            kind="ontology",
            name="Phospho",
            ontology_id="UNIMOD:21",
            residues="STY",
            term_specificity="none",
            mass_shift=79.966331,
            profile="default",
        )

        bridge = JSpreadsheetBridge(wizard, entity_type="modifications")
        spreadsheet_data = bridge.get_spreadsheet_data()

        with pytest.raises(ValueError, match="only edit 'mode' and 'profile'"):
            bridge.handle_cell_edit(
                row_index=0,
                col_index=spreadsheet_data["headers"].index("name"),
                new_value="Phospho edited",
            )

        bridge.handle_cell_edit(
            row_index=0,
            col_index=spreadsheet_data["headers"].index("profile"),
            new_value="alternate",
        )

        assert wizard.modifications[0]["profile"] == "alternate"

    def test_modification_bridge_sync_ignores_locked_ontology_field_changes(self):
        """Full-sheet sync should preserve locked ontology fields and only accept editable ones."""
        wizard = WizardState()
        wizard.add_modification(
            mode="fixed",
            kind="ontology",
            name="Phospho",
            ontology_id="UNIMOD:21",
            residues="STY",
            term_specificity="none",
            mass_shift=79.966331,
            profile="default",
        )

        bridge = JSpreadsheetBridge(wizard, entity_type="modifications")
        spreadsheet_data = bridge.get_spreadsheet_data()
        headers = spreadsheet_data["headers"]
        row = spreadsheet_data["data"][0][:]
        row[headers.index("name")] = "Phospho edited"
        row[headers.index("residues")] = "M"
        row[headers.index("profile")] = "alternate"

        bridge.sync_from_spreadsheet_data([row])

        assert wizard.modifications[0]["name"] == "Phospho"
        assert wizard.modifications[0]["residues"] == "STY"
        assert wizard.modifications[0]["profile"] == "alternate"

    def test_modification_bridge_sync_allows_copying_ontology_values_onto_non_ontology_row(self):
        """Copying an ontology row onto a non-ontology row should create a locked ontology row."""
        wizard = WizardState()
        wizard.add_modification(
            mode="fixed",
            kind="ontology",
            name="Phospho",
            ontology_id="UNIMOD:21",
            residues="STY",
            term_specificity="none",
            mass_shift=79.966331,
            profile="default",
        )
        wizard.add_modification(
            mode="variable",
            kind="custom",
            name="Lab Label",
            residues="M",
            mass_shift=42.0,
            profile="custom-profile",
        )

        bridge = JSpreadsheetBridge(wizard, entity_type="modifications")
        spreadsheet_data = bridge.get_spreadsheet_data()
        copied_row = spreadsheet_data["data"][0][:]
        copied_row[spreadsheet_data["headers"].index("profile")] = "alternate"

        bridge.sync_from_spreadsheet_data([spreadsheet_data["data"][0], copied_row])

        assert wizard.modifications[1]["kind"] == "ontology"
        assert wizard.modifications[1]["name"] == "Phospho"
        assert wizard.modifications[1]["ontology_id"] == "UNIMOD:21"
        assert wizard.modifications[1]["residues"] == "STY"
        assert wizard.modifications[1]["mass_shift"] == 79.966331
        assert wizard.modifications[1]["profile"] == "alternate"
