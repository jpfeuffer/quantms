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
from unittest.mock import MagicMock, patch, AsyncMock
from typing import Any, Dict, List

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from gui_wizard_state import WizardState
from spreadsheet_adapter import SpreadsheetAdapter, SpreadsheetRow
from jspreadsheet_bridge import JSpreadsheetBridge
from jspreadsheet_editor import JSpreadsheetEditor
from manifest_core import ChannelBuilder


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

    def test_bridge_exposes_group_membership_dropdown_for_existing_groups_only(self):
        """Runs spreadsheet should expose existing groups as dropdown options without creatable metadata."""
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")
        wizard.add_group(id="group_1", name="Replicate group", kind="replicate")

        bridge = JSpreadsheetBridge(wizard)
        data = bridge.get_spreadsheet_data()

        assert data["headers"] == ["file", "fraction", "instrument", "group_id"]
        assert data["data"][0][data["headers"].index("group_id")] is None
        assert data["column_config"]["group_id"]["type"] == "dropdown"
        assert data["column_config"]["group_id"]["source"] == [{"id": "group_1", "name": "group_1"}]
        assert "new_options" not in data["column_config"]["group_id"]

        bridge.handle_cell_edit(row_index=0, col_index=data["headers"].index("group_id"), new_value="group_1")

        assert wizard.runs[0]["group_id"] == "group_1"
        assert wizard.groups[0]["members"] == [wizard.runs[0]["id"]]

    def test_bridge_rejects_missing_group_when_group_id_is_edited(self):
        """Runs spreadsheet edits should not create a group when the user types a missing group_id."""
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")

        bridge = JSpreadsheetBridge(wizard)
        headers = bridge.get_spreadsheet_data()["headers"]

        with pytest.raises(ValueError, match="Group 'new_group' not found"):
            bridge.handle_cell_edit(row_index=0, col_index=headers.index("group_id"), new_value="new_group")

        assert "group_id" not in wizard.runs[0]
        assert wizard.groups == []

    def test_bridge_group_dropdown_does_not_advertise_free_text_creation_metadata(self):
        """Runs spreadsheet should not advertise that group_id supports creating new values."""
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")
        wizard.add_group(id="group_1", name="Replicate group", kind="replicate")

        bridge = JSpreadsheetBridge(wizard)
        data = bridge.get_spreadsheet_data()

        assert data["column_config"]["group_id"]["type"] == "dropdown"
        assert "new_options" not in data["column_config"]["group_id"]

    def test_bridge_group_column_is_not_creatable_when_no_groups_exist(self):
        """The Files table should not expose a creatable group_id dropdown when no groups exist."""
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")

        bridge = JSpreadsheetBridge(wizard)
        data = bridge.get_spreadsheet_data()

        assert data["column_config"]["group_id"]["type"] != "dropdown"
        assert "source" not in data["column_config"]["group_id"]
        assert "new_options" not in data["column_config"]["group_id"]

    def test_bridge_group_dropdown_updates_after_new_group_creation(self):
        """Adding a group should make it available in the Files-side group dropdown on rerender."""
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")

        bridge = JSpreadsheetBridge(wizard)
        initial_data = bridge.get_spreadsheet_data()
        assert initial_data["column_config"]["group_id"]["type"] != "dropdown"

        wizard.add_group(id="group_1", name="Replicate group", kind="LFQ")

        refreshed_data = bridge.get_spreadsheet_data()
        assert refreshed_data["column_config"]["group_id"]["type"] == "dropdown"
        assert refreshed_data["column_config"]["group_id"]["source"] == [{"id": "group_1", "name": "group_1"}]

    def test_bridge_groups_labeling_strategy_dropdown_respects_experiment_quantification_method(self):
        """Groups-sheet labeling strategy options should stay restricted by the experiment quantification method."""
        wizard = WizardState()
        wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD",
            quantification_method="LFQ",
        )
        wizard.add_group(id="group_1", name="LFQ group", kind="LFQ")

        bridge = JSpreadsheetBridge(wizard, entity_type="groups")
        data = bridge.get_spreadsheet_data()

        assert data["column_config"]["labeling_strategy"]["type"] == "dropdown"
        assert data["column_config"]["labeling_strategy"]["source"] == [
            {"id": "label free sample", "name": "label free sample"}
        ]

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

    def test_bridge_cleared_group_id_blocks_future_heuristic_reseed(self):
        """Clearing group_id through the bridge should stay clear until an explicit regroup request."""
        wizard = WizardState()
        wizard.add_run(file="/data/sample_fraction1.raw")

        bridge = JSpreadsheetBridge(wizard)
        headers = bridge.get_spreadsheet_data()["headers"]

        bridge.handle_cell_edit(row_index=0, col_index=headers.index("group_id"), new_value="")
        wizard.add_run(file="/data/sample_fraction2.raw")

        assert "group_id" not in wizard.runs[0]
        assert wizard.runs[0]["group_assignment_cleared"] is True
        assert "group_id" not in wizard.runs[1]
        assert wizard.groups == []

        wizard.seed_runs_from_filenames(force=True)

        assert wizard.runs[0]["group_id"] == "sample"
        assert wizard.runs[1]["group_id"] == "sample"
        assert wizard.groups[0]["members"] == [wizard.runs[0]["id"], wizard.runs[1]["id"]]

    def test_bridge_explicit_empty_group_id_marks_never_grouped_run_as_cleared(self):
        """Explicitly clearing an empty group cell should still suppress future heuristic grouping for that run."""
        wizard = WizardState()
        wizard.add_run(file="/data/sample.raw")

        bridge = JSpreadsheetBridge(wizard)
        headers = bridge.get_spreadsheet_data()["headers"]

        bridge.handle_cell_edit(row_index=0, col_index=headers.index("group_id"), new_value="")
        wizard.add_run(file="/data/sample_fraction2.raw")

        assert "group_id" not in wizard.runs[0]
        assert wizard.runs[0]["group_assignment_cleared"] is True

    def test_groups_bridge_exposes_groups_table_without_members_column(self):
        """Groups spreadsheet should not expose membership editing from the Groups side."""
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")
        wizard.add_group(id="group_1", name="LFQ group", kind="LFQ")
        wizard.assign_run(run_index=0, group_id="group_1")

        bridge = JSpreadsheetBridge(wizard, entity_type="groups")
        data = bridge.get_spreadsheet_data()

        assert data["headers"] == ["id", "name", "kind", "labeling_strategy", "channel_count", "description"]
        assert data["data"][0][data["headers"].index("labeling_strategy")] == "label free sample"
        assert data["data"][0][data["headers"].index("channel_count")] == 1
        assert data["column_config"]["id"]["read_only"] is True
        assert "read_only" not in data["column_config"]["name"]
        assert "read_only" not in data["column_config"]["kind"]
        assert "read_only" not in data["column_config"]["labeling_strategy"]
        assert data["column_config"]["channel_count"]["read_only"] is True
        assert "read_only" not in data["column_config"]["description"]
        assert data["column_config"]["kind"]["type"] == "dropdown"
        assert data["column_config"]["kind"]["source"] == [
            {"id": "LFQ", "name": "LFQ"},
            {"id": "TMT", "name": "TMT"},
            {"id": "iTRAQ", "name": "iTRAQ"},
            {"id": "SILAC", "name": "SILAC"},
        ]
        assert "members" not in data["headers"]
        assert "members" not in data["column_config"]
        assert data["read_only_cells"] == [{"row": 0, "col": 0}, {"row": 0, "col": 4}]
        assert bridge.get_row_count() == 1

    def test_groups_bridge_includes_labeling_strategy_and_channel_count_columns(self):
        """Groups spreadsheet should expose labeling strategy and derived channel count."""
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")
        wizard.add_group(id="group_1", name="LFQ group", kind="LFQ")

        bridge = JSpreadsheetBridge(wizard, entity_type="groups")
        data = bridge.get_spreadsheet_data()

        assert data["headers"] == ["id", "name", "kind", "labeling_strategy", "channel_count", "description"]
        assert data["data"][0][data["headers"].index("labeling_strategy")] == "label free sample"
        assert data["data"][0][data["headers"].index("channel_count")] == 1
        assert data["column_config"]["labeling_strategy"]["type"] == "dropdown"
        assert data["column_config"]["channel_count"]["read_only"] is True

    def test_groups_bridge_labeling_strategy_dropdown_uses_all_allowed_strategies_for_unrestricted_experiments(self):
        """LFQ-only sheets should still expose the full allowed labeling-strategy source when the experiment does not narrow kinds."""
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")
        wizard.add_group(id="group_1", name="LFQ group", kind="LFQ")

        bridge = JSpreadsheetBridge(wizard, entity_type="groups")
        data = bridge.get_spreadsheet_data()

        assert data["column_config"]["labeling_strategy"]["source"] == [
            {"id": strategy, "name": strategy}
            for strategy in wizard.get_allowed_labeling_strategies()
        ]

    def test_groups_bridge_backfills_missing_labeling_strategy_from_kind(self):
        """Legacy groups without strategy metadata should be normalized when the sheet renders."""
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")
        wizard.groups.append({"id": "group_1", "name": "LFQ group", "kind": "LFQ", "members": []})

        bridge = JSpreadsheetBridge(wizard, entity_type="groups")
        data = bridge.get_spreadsheet_data()

        assert wizard.groups[0]["labeling_strategy"] == "label free sample"
        assert wizard.groups[0]["channel_count"] == 1
        assert data["data"][0][data["headers"].index("labeling_strategy")] == "label free sample"
        assert data["data"][0][data["headers"].index("channel_count")] == 1

    def test_groups_bridge_keeps_kind_and_labeling_strategy_synced_on_full_sheet_edit(self):
        """Full-sheet group sync should keep derived channel counts aligned with the chosen strategy."""
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")
        wizard.add_group(id="group_1", name="Multiplex group", kind="TMT", labeling_strategy="TMT6")

        bridge = JSpreadsheetBridge(wizard, entity_type="groups")
        data = bridge.get_spreadsheet_data()
        headers = data["headers"]
        snapshot = [row[:] for row in data["data"]]

        snapshot[0][headers.index("kind")] = "LFQ"
        snapshot[0][headers.index("labeling_strategy")] = "label free sample"
        snapshot[0][headers.index("channel_count")] = 99

        bridge.sync_from_spreadsheet_data(snapshot)

        assert wizard.groups[0]["kind"] == "LFQ"
        assert wizard.groups[0]["labeling_strategy"] == "label free sample"
        assert wizard.groups[0]["channel_count"] == 1

    def test_groups_bridge_allows_labeling_strategy_edit_after_kind_change(self):
        """Groups cell edits should accept a newly valid strategy after the kind is changed."""
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")
        wizard.add_group(id="group_1", name="LFQ group", kind="LFQ")

        bridge = JSpreadsheetBridge(wizard, entity_type="groups")
        headers = bridge.get_spreadsheet_data()["headers"]

        tmt_strategy = wizard.get_allowed_labeling_strategies("TMT")[0]

        bridge.handle_cell_edit(row_index=0, col_index=headers.index("kind"), new_value="TMT")
        bridge.handle_cell_edit(row_index=0, col_index=headers.index("labeling_strategy"), new_value=tmt_strategy)

        assert wizard.groups[0]["kind"] == "TMT"
        assert wizard.groups[0]["labeling_strategy"] == tmt_strategy
        assert wizard.groups[0]["channel_count"] == wizard.get_labeling_strategy_channel_count(tmt_strategy)

    def test_groups_bridge_sync_paths_update_wizard_groups(self):
        """Groups sync APIs should keep membership owned by the Files side."""
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")
        wizard.add_run(file="/data/other.raw")
        wizard.add_group(id="group_1", name="LFQ group", kind="LFQ")
        wizard.assign_run(run_index=0, group_id="group_1")

        bridge = JSpreadsheetBridge(wizard, entity_type="groups")

        rows = bridge.adapter.wizard_groups_to_spreadsheet()
        rows[0].name = "Edited name"
        rows[0].kind = "TMT"
        rows[0].members = wizard.runs[1]["id"]
        rows[0].description = "Edited description"
        bridge.adapter.sync_group_edits(rows)

        assert wizard.groups[0]["name"] == "Edited name"
        assert wizard.groups[0]["kind"] == "TMT"
        assert wizard.groups[0]["members"] == [wizard.runs[0]["id"]]
        assert wizard.groups[0]["description"] == "Edited description"
        assert wizard.runs[0]["group_id"] == "group_1"
        assert "group_id" not in wizard.runs[1]

        spreadsheet_data = bridge.get_spreadsheet_data()
        mutated_snapshot = [row[:] for row in spreadsheet_data["data"]]
        mutated_snapshot[0][spreadsheet_data["headers"].index("name")] = "Edited name"
        mutated_snapshot[0][spreadsheet_data["headers"].index("kind")] = "LFQ"
        mutated_snapshot[0][spreadsheet_data["headers"].index("description")] = "Browser edit"

        bridge.sync_from_spreadsheet_data(mutated_snapshot)

        assert wizard.groups[0]["name"] == "Edited name"
        assert wizard.groups[0]["kind"] == "LFQ"
        assert wizard.groups[0]["members"] == [wizard.runs[0]["id"]]
        assert wizard.groups[0]["description"] == "Browser edit"
        assert wizard.runs[0]["group_id"] == "group_1"
        assert "group_id" not in wizard.runs[1]

    def test_group_channels_bridge_uses_sample_dropdowns_for_strategy_columns(self):
        """Group channel sheets should expose strategy-specific channel columns with Sample-sheet dropdowns."""
        wizard = WizardState()
        wizard.add_sample(id="sample_1")
        wizard.add_sample(id="sample_2")
        wizard.add_group(id="tmt6_group", name="TMT6 group", kind="TMT", labeling_strategy="TMT6")
        wizard.set_group_channel_assignments("tmt6_group", {"TMT126": "sample_1"})

        bridge = JSpreadsheetBridge(wizard, entity_type="group_channels", group_strategy="TMT6")
        data = bridge.get_spreadsheet_data()

        assert data["headers"] == ["id", "TMT126", "TMT127N", "TMT127C", "TMT128N", "TMT128C", "TMT129N"]
        assert data["data"][0][0] == "tmt6_group"
        assert data["data"][0][1] == "sample_1"
        assert data["column_config"]["TMT126"]["type"] == "dropdown"
        assert data["column_config"]["TMT126"]["source"] == [
            {"id": "sample_1", "name": "sample_1"},
            {"id": "sample_2", "name": "sample_2"},
        ]
        assert data["read_only_cells"] == [{"row": 0, "col": 0}]
        assert data["allow_delete_row"] is False

    def test_group_channels_bridge_supports_lfq_sample_target_columns(self):
        """LFQ group channel sheets should use a single sample target column sourced from Samples."""
        wizard = WizardState()
        wizard.add_sample(id="sample_1")
        wizard.add_group(id="lfq_group", name="LFQ group", kind="LFQ")
        wizard.set_group_sample_target("lfq_group", "sample_1")

        bridge = JSpreadsheetBridge(wizard, entity_type="group_channels", group_strategy="LFQ")
        data = bridge.get_spreadsheet_data()

        assert data["headers"] == ["id", "sample_target"]
        assert data["data"][0][0] == "lfq_group"
        assert data["data"][0][1] == "sample_1"
        assert data["column_config"]["sample_target"]["type"] == "dropdown"
        assert data["column_config"]["sample_target"]["source"] == [{"id": "sample_1", "name": "sample_1"}]

    def test_channel_catalog_includes_provenance_for_known_strategies(self):
        """Bundled channel catalog entries should carry strategy provenance when available."""
        catalog = ChannelBuilder.get_channel_catalog()

        assert "TMT6" in catalog
        assert catalog["TMT6"][0]["channel"] == "TMT126"
        assert catalog["TMT6"][0]["provenance"]
        assert "PSI-MS" in catalog["TMT6"][0]["provenance"] or "PRIDE" in catalog["TMT6"][0]["provenance"]

    def test_groups_editor_flush_pending_edits_round_trips_groups(self):
        """Groups editor flush should round-trip editable group rows without changing membership ownership."""
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")
        wizard.add_group(id="group_1", name="LFQ group", kind="LFQ")
        wizard.assign_run(run_index=0, group_id="group_1")

        bridge = JSpreadsheetBridge(wizard, entity_type="groups")
        editor = JSpreadsheetEditor(wizard, MagicMock(), bridge=bridge, worksheet_name="Groups")
        editor.container = SimpleNamespace(html_id="groups-container")

        with patch("jspreadsheet_editor.context") as mock_context:
            mock_context.client.run_javascript = AsyncMock(return_value=[
                [
                    "group_1",
                    "Updated group",
                    "SILAC",
                    "SILAC_2plex",
                    2,
                    "Updated via flush",
                ],
            ])

            result = asyncio.run(editor.flush_pending_edits())

        assert result == 0
        assert wizard.groups[0]["name"] == "Updated group"
        assert wizard.groups[0]["kind"] == "SILAC"
        assert wizard.groups[0]["members"] == [wizard.runs[0]["id"]]
        assert wizard.groups[0]["description"] == "Updated via flush"
        mock_context.client.run_javascript.assert_called()

    def test_groups_bridge_rejects_unknown_members_and_respects_kind_restrictions(self):
        """Groups edits must honor experiment-driven kind restrictions without exposing member edits."""
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")
        wizard.add_group(id="group_1", name="LFQ group", kind="LFQ")
        wizard.assign_run(run_index=0, group_id="group_1")
        wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            quantification_method="TMT",
            dissociation_method="HCD",
        )

        bridge = JSpreadsheetBridge(wizard, entity_type="groups")
        data = bridge.get_spreadsheet_data()

        assert data["column_config"]["kind"]["source"] == [{"id": "TMT", "name": "TMT"}]

        with pytest.raises(ValueError, match="Allowed options: TMT"):
            bridge.handle_cell_edit(
                row_index=0,
                col_index=data["headers"].index("kind"),
                new_value="LFQ",
            )

        assert "members" not in data["headers"]

    def test_runs_group_id_edits_keep_groups_membership_view_in_sync(self):
        """Changing a run's group_id should move membership between groups."""
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")
        wizard.add_group(id="group_1", name="LFQ group 1", kind="LFQ")
        wizard.add_group(id="group_2", name="LFQ group 2", kind="LFQ")

        bridge = JSpreadsheetBridge(wizard)
        headers = bridge.get_spreadsheet_data()["headers"]

        bridge.handle_cell_edit(row_index=0, col_index=headers.index("group_id"), new_value="group_1")
        bridge.handle_cell_edit(row_index=0, col_index=headers.index("group_id"), new_value="group_2")

        assert wizard.groups[0]["members"] == []
        assert wizard.groups[1]["members"] == [wizard.runs[0]["id"]]

    def test_runs_full_sheet_sync_applies_group_id_edits(self):
        """Full-sheet sync should keep run-side group_id edits working."""
        wizard = WizardState()
        wizard.add_run(file="/data/sample.raw", instrument="Orbitrap")
        wizard.add_group(id="group_1", name="Group 1", kind="DDA")
        wizard.add_group(id="group_2", name="Group 2", kind="DDA")
        wizard.assign_run(run_index=0, group_id="group_1")

        bridge = JSpreadsheetBridge(wizard)
        spreadsheet_data = bridge.get_spreadsheet_data()
        mutated_snapshot = [row[:] for row in spreadsheet_data["data"]]
        mutated_snapshot[0][spreadsheet_data["headers"].index("group_id")] = "group_2"

        bridge.sync_from_spreadsheet_data(mutated_snapshot)

        assert wizard.runs[0]["group_id"] == "group_2"
        assert wizard.groups[0]["members"] == []
        assert wizard.groups[1]["members"] == [wizard.runs[0]["id"]]
        assert wizard.runs[0]["instrument"] == "Orbitrap"

    def test_groups_full_sheet_sync_rejects_id_edits(self):
        """Groups full-sheet sync should reject edits to the immutable group identifier."""
        wizard = WizardState()
        wizard.add_run(file="/data/sample.raw")
        wizard.add_group(id="group_1", name="Group 1", kind="DDA")
        wizard.assign_run(run_index=0, group_id="group_1")

        bridge = JSpreadsheetBridge(wizard, entity_type="groups")
        spreadsheet_data = bridge.get_spreadsheet_data()
        mutated_snapshot = [row[:] for row in spreadsheet_data["data"]]
        mutated_snapshot[0][spreadsheet_data["headers"].index("id")] = "group_edited"

        with pytest.raises(ValueError, match="Group ID is read-only"):
            bridge.sync_from_spreadsheet_data(mutated_snapshot)

        assert wizard.groups[0]["id"] == "group_1"
        assert wizard.runs[0]["group_id"] == "group_1"

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
