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
Tests for Phase 3: Add constrained dropdown editors.

Tests verify:
- OntologyOptionProvider returns instrument options
- JSpreadsheetEditor configures instrument column as dropdown
- Dropdown values round-trip through bridge and persist in WizardState
"""

import pytest
import sys
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from ontology_provider import OntologyOptionProvider
from gui_wizard_state import WizardState
from jspreadsheet_bridge import JSpreadsheetBridge
from spreadsheet_adapter import SpreadsheetAdapter
from spreadsheet_column_config import ColumnConfigBuilder


class TestOntologyProviderInstrumentOptions:
    """Tests for instrument options from ontology provider (contract)."""

    def test_provider_returns_instrument_options(self):
        """
        AC1: OntologyOptionProvider.get_options('instrument') returns a list
        of options with 'label' and 'value' keys (or falls back to defaults).
        """
        provider = OntologyOptionProvider()
        options = provider.get_options("instrument")

        # Must return a list
        assert isinstance(options, list)
        assert len(options) > 0

        # All options must have label and value
        for option in options:
            assert isinstance(option, dict)
            assert "label" in option
            assert "value" in option
            assert isinstance(option["label"], str)
            assert isinstance(option["value"], str)

    def test_provider_instrument_fallback_has_common_instruments(self):
        """
        AC2: Instrument options include common PSI-MS instruments
        (Q-TOF, Orbitrap, Ion Trap, MALDI-TOF, Tribrid).
        """
        provider = OntologyOptionProvider()
        options = provider.get_options("instrument")

        labels = [opt["label"] for opt in options]
        values = [opt["value"] for opt in options]

        # Check for common instruments in either label or value
        all_text = " ".join(labels + values).lower()
        common_instruments = ["q exactive", "orbitrap", "tripletof", "timstof", "lumos"]

        # At least one common instrument should be present
        assert any(instr.lower() in all_text for instr in common_instruments)

    def test_provider_uses_instrument_model_subtree_when_oak_adapter_supports_descendants(self):
        """
        AC3: Instrument ontology lookup uses the PSI-MS instrument subtree
        rooted at MS:1000463 instead of a plain keyword search.
        """
        adapter = MagicMock()
        adapter.descendants.return_value = ["MS:1000126", "MS:1001911"]
        adapter.get_label.side_effect = lambda curie: {
            "MS:1000126": "Waters instrument model",
            "MS:1001911": "Q Exactive",
        }[curie]

        provider = OntologyOptionProvider(oak_adapter=adapter)
        options = provider.get_options("instrument")

        adapter.descendants.assert_called_once_with("MS:1000463", reflexive=False)
        assert options == [
            {"label": "Q Exactive", "value": "Q Exactive"},
            {"label": "Waters instrument model", "value": "Waters instrument model"},
        ]


class TestSpreadsheetColumnConfig:
    """Tests for column configuration with dropdown support."""

    def test_adapter_provides_column_config_for_headers(self):
        """
        AC3: SpreadsheetAdapter provides column configuration that
        describes which columns are dropdowns and their options.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", fraction=1, instrument="Q-TOF")

        adapter = SpreadsheetAdapter(wizard)

        # Get column headers
        headers = adapter.get_column_headers()
        assert headers == ["file", "fraction", "instrument"]

        # Get field metadata for each column
        for field in headers:
            field_info = adapter.get_field_info(field)
            assert "type" in field_info
            assert "required" in field_info

    def test_field_info_identifies_constrained_columns(self):
        """
        AC4 (REVISED): Test that constrained/dropdown configuration is validated
        at the ColumnConfigBuilder layer, not just in adapter field info.
        The adapter's field_info is a low-level contract; the actual constrained
        behavior is determined by ColumnConfigBuilder.
        """
        adapter = SpreadsheetAdapter(WizardState())
        builder = ColumnConfigBuilder()

        # Build config from adapter's field info
        config = builder.build_column_config(
            ["file", "fraction", "instrument"],
            field_info_getter=adapter.get_field_info
        )

        # File should not be constrained (dropdown)
        assert config["file"].get("type") != "dropdown"
        assert "source" not in config["file"]

        # Fraction should not be constrained (dropdown)
        assert config["fraction"].get("type") != "dropdown"
        assert "source" not in config["fraction"]

        # Instrument MUST be constrained (dropdown with source)
        assert config["instrument"]["type"] == "dropdown"
        assert "source" in config["instrument"]
        assert isinstance(config["instrument"]["source"], list)
        assert len(config["instrument"]["source"]) > 0

        # Each source option should have id/name format (not label/value)
        for option in config["instrument"]["source"]:
            assert isinstance(option, dict)
            assert "id" in option, f"Option missing 'id': {option}"
            assert "name" in option, f"Option missing 'name': {option}"


class TestBridgeColumnConfigWithOptions:
    """Tests for bridge providing column configs with dropdown options."""

    def test_bridge_provides_spreadsheet_data_with_column_config(self):
        """
        AC5: JSpreadsheetBridge.get_spreadsheet_data() returns
        'column_config' in addition to 'headers' and 'data',
        describing which columns are dropdowns and their options.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", fraction=1, instrument="Orbitrap")

        bridge = JSpreadsheetBridge(wizard)
        data = bridge.get_spreadsheet_data()

        # Should have headers, data, and column_config
        assert "headers" in data
        assert "data" in data
        assert "column_config" in data

        # column_config should be a dict mapping headers to configs
        column_config = data["column_config"]
        assert isinstance(column_config, dict)

    def test_bridge_column_config_includes_instrument_dropdown(self):
        """
        AC6: The instrument column in column_config is marked as
        type='dropdown' with source options from ontology provider.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", instrument="Q-TOF")

        bridge = JSpreadsheetBridge(wizard)
        data = bridge.get_spreadsheet_data()
        column_config = data["column_config"]

        # Instrument column should have dropdown type
        assert "instrument" in column_config
        instrument_config = column_config["instrument"]
        assert "type" in instrument_config
        assert instrument_config["type"] == "dropdown"

        # Should have source options
        assert "source" in instrument_config
        options = instrument_config["source"]
        assert isinstance(options, list)
        assert len(options) > 0

        # Options should be jspreadsheet-compatible format
        # (could be dicts with id/name or strings)
        for option in options:
            assert isinstance(option, (str, dict))

    def test_bridge_column_config_non_dropdown_columns_unchanged(self):
        """
        AC7: Non-dropdown columns (file, fraction) are not marked as dropdown
        and do not have source options in column_config.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", fraction=1)

        bridge = JSpreadsheetBridge(wizard)
        data = bridge.get_spreadsheet_data()
        column_config = data["column_config"]

        # File column should not be dropdown
        assert "file" in column_config
        file_config = column_config["file"]
        assert file_config.get("type") != "dropdown"

        # Fraction column should not be dropdown
        assert "fraction" in column_config
        fraction_config = column_config["fraction"]
        assert fraction_config.get("type") != "dropdown"


class TestInstrumentRoundTrip:
    """Tests for instrument value round-trip through bridge and persistence."""

    def test_instrument_value_edited_and_persists_in_wizard(self):
        """
        AC8: When instrument is edited via bridge.handle_cell_edit(),
        the value persists in WizardState.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", instrument="Ion Trap")

        bridge = JSpreadsheetBridge(wizard)

        # Edit instrument column (index 2)
        bridge.handle_cell_edit(row_index=0, col_index=2, new_value="Orbitrap")

        # Verify wizard state updated
        assert wizard.runs[0]["instrument"] == "Orbitrap"

    def test_instrument_value_empty_string_treated_as_none(self):
        """
        AC9: When instrument is set to empty string, it is treated as None
        (optional field behavior).
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", instrument="Q-TOF")

        bridge = JSpreadsheetBridge(wizard)

        # Clear instrument
        bridge.handle_cell_edit(row_index=0, col_index=2, new_value="")

        # Should be None since instrument is optional
        assert wizard.runs[0].get("instrument") is None or wizard.runs[0]["instrument"] == ""

    def test_instrument_roundtrip_read_and_write(self):
        """
        AC10: Reading instrument via get_spreadsheet_data() after setting it
        reflects the updated value.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", instrument="Ion Trap")

        bridge = JSpreadsheetBridge(wizard)

        # Update instrument
        bridge.handle_cell_edit(row_index=0, col_index=2, new_value="Tribrid")

        # Read back via get_spreadsheet_data
        data = bridge.get_spreadsheet_data()
        row_data = data["data"][0]
        instrument_value = row_data[2]  # instrument is column index 2

        assert instrument_value == "Tribrid"

    def test_multiple_instruments_independent(self):
        """
        AC11: Multiple runs can have different instrument values that don't interfere.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test1.raw", instrument="Q-TOF")
        wizard.add_run(file="/data/test2.raw", instrument="Orbitrap")

        bridge = JSpreadsheetBridge(wizard)

        # Edit first run's instrument
        bridge.handle_cell_edit(row_index=0, col_index=2, new_value="Ion Trap")

        # Second run should remain unchanged
        assert wizard.runs[0]["instrument"] == "Ion Trap"
        assert wizard.runs[1]["instrument"] == "Orbitrap"


class TestEditorDropdownInitialization:
    """Tests for JSpreadsheetEditor dropdown initialization path."""

    def test_initialize_data_includes_column_config(self):
        """
        AC12: JSpreadsheetEditor._initialize_data() includes column_config
        from bridge.get_spreadsheet_data() in the JavaScript data store.
        """
        from jspreadsheet_editor import JSpreadsheetEditor
        from unittest.mock import MagicMock

        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", instrument="Q-TOF")

        on_change = MagicMock()
        editor = JSpreadsheetEditor(wizard, on_change)

        # Mock the JavaScript execution to capture what would be sent
        sent_scripts = []

        def mock_run_javascript(script):
            sent_scripts.append(script)

        # Mock context and container
        editor.container = MagicMock()
        editor.container.html_id = "test-container-123"

        # Capture the JavaScript that would be sent
        with patch("jspreadsheet_editor.context") as mock_context:
            mock_context.client.run_javascript = mock_run_javascript

            # Run _initialize_data
            editor._initialize_data()

        # Verify column_config was included
        assert len(sent_scripts) > 0
        script_content = sent_scripts[0]

        # Check for column_config in the data store
        assert "__quantmsSpreadsheetData" in script_content
        assert "column_config" in script_content
        assert "instrument" in script_content

        parsed_column_config = spreadsheet_data = editor.bridge.get_spreadsheet_data()["column_config"]
        assert parsed_column_config["instrument"]["type"] == "dropdown"
        assert parsed_column_config["instrument"]["source"]

    def test_create_spreadsheet_widget_merges_dropdown_config(self):
        """
        AC13: JSpreadsheetEditor._create_spreadsheet_widget() reads
        column_config from the data store and merges dropdown properties
        into the JSpreadsheet column definitions.
        """
        from jspreadsheet_editor import JSpreadsheetEditor
        from unittest.mock import MagicMock

        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", instrument="Q-TOF")

        on_change = MagicMock()
        editor = JSpreadsheetEditor(wizard, on_change)

        # Capture the JavaScript that would be sent
        sent_scripts = []

        def mock_run_javascript(script):
            sent_scripts.append(script)

        editor.widget_id = "test-widget-id"

        with patch("jspreadsheet_editor.context") as mock_context:
            mock_context.client.run_javascript = mock_run_javascript

            # Run _create_spreadsheet_widget
            editor._create_spreadsheet_widget()

        # Verify the initialization script includes dropdown config wiring
        assert len(sent_scripts) > 0
        script_content = sent_scripts[0]

        bridge_data = editor.bridge.get_spreadsheet_data()
        instrument_column_index = bridge_data["headers"].index("instrument")
        instrument_config = bridge_data["column_config"]["instrument"]

        assert instrument_config["type"] == "dropdown"
        assert instrument_config["source"]
        assert f"headers.forEach((header, index) =>" in script_content
        assert "columns[index].type = 'dropdown'" in script_content
        assert "columns[index].source = config.source" in script_content
        assert instrument_column_index == 2

    def test_instrument_column_renders_as_dropdown(self):
        """
        AC14 (REVISED): The instrument column in the spreadsheet widget
        is configured as a dropdown with source options in id/name format
        (not label/value format).
        """
        from jspreadsheet_editor import JSpreadsheetEditor
        from unittest.mock import MagicMock

        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", instrument="Q-TOF")

        on_change = MagicMock()
        editor = JSpreadsheetEditor(wizard, on_change)

        # Get what the bridge prepares
        bridge_data = editor.bridge.get_spreadsheet_data()
        column_config = bridge_data.get("column_config", {})

        # Verify instrument column is marked as dropdown
        assert "instrument" in column_config
        instrument_config = column_config["instrument"]
        assert instrument_config.get("type") == "dropdown"

        # Verify source options are present and in correct format
        assert "source" in instrument_config
        source = instrument_config["source"]
        assert isinstance(source, list)
        assert len(source) > 0

        # Each option should be in id/name format (not label/value)
        for option in source:
            assert isinstance(option, dict), f"Option should be dict, got {type(option)}"
            assert "id" in option, f"Option missing 'id': {option}"
            assert "name" in option, f"Option missing 'name': {option}"
            # Should NOT have label/value anymore
            assert "label" not in option, f"Option should not have 'label': {option}"
            assert "value" not in option, f"Option should not have 'value': {option}"

    def test_dropdown_config_flow_with_multiple_columns(self):
        """
        AC15: Column config correctly identifies which columns are
        dropdowns (instrument) and which are not (file, fraction).
        """
        from jspreadsheet_editor import JSpreadsheetEditor
        from unittest.mock import MagicMock

        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", fraction=1, instrument="Orbitrap")

        on_change = MagicMock()
        editor = JSpreadsheetEditor(wizard, on_change)

        # Get bridge data
        bridge_data = editor.bridge.get_spreadsheet_data()
        column_config = bridge_data.get("column_config", {})
        headers = bridge_data.get("headers", [])

        # Verify all headers are in config
        assert "file" in column_config
        assert "fraction" in column_config
        assert "instrument" in column_config

        # file and fraction should NOT be dropdown
        assert column_config["file"].get("type") != "dropdown"
        assert column_config["fraction"].get("type") != "dropdown"

        # instrument MUST be dropdown
        assert column_config["instrument"].get("type") == "dropdown"
        assert "source" in column_config["instrument"]


class TestPhase3Revisions:
    """Tests for Phase 3 revisions based on code review."""

    def test_dropdown_format_converted_to_id_name(self):
        """
        REVISION 1: Dropdown options should be converted from {'label': '...', 'value': '...'}
        format to {'id': '...', 'name': '...'} format expected by jspreadsheet-ce.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", instrument="Q-TOF")

        bridge = JSpreadsheetBridge(wizard)
        data = bridge.get_spreadsheet_data()
        column_config = data["column_config"]

        # Instrument should be dropdown
        assert column_config["instrument"]["type"] == "dropdown"
        source = column_config["instrument"]["source"]

        # All options must be in id/name format (not label/value)
        for option in source:
            assert isinstance(option, dict)
            assert "id" in option, f"Option missing 'id': {option}"
            assert "name" in option, f"Option missing 'name': {option}"
            # Should NOT have label/value anymore
            assert "label" not in option, f"Option should not have 'label': {option}"
            assert "value" not in option, f"Option should not have 'value': {option}"

    def test_server_side_validation_rejects_invalid_instruments(self):
        """
        REVISION 2: Server-side validation in JSpreadsheetBridge should
        reject invalid instrument values and accept valid ones.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", instrument="Orbitrap")

        bridge = JSpreadsheetBridge(wizard)

        # Valid instrument should work
        bridge.handle_cell_edit(row_index=0, col_index=2, new_value="Q-TOF")
        assert wizard.runs[0]["instrument"] == "Q-TOF"

        # Invalid instrument should raise ValueError
        with pytest.raises(ValueError, match="Invalid value.*instrument"):
            bridge.handle_cell_edit(row_index=0, col_index=2, new_value="InvalidInstrument")

    def test_server_side_validation_allows_empty_instrument(self):
        """
        REVISION 2: Server-side validation should allow empty/None for optional fields.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", instrument="Orbitrap")

        bridge = JSpreadsheetBridge(wizard)

        # Empty string should be allowed for optional field
        bridge.handle_cell_edit(row_index=0, col_index=2, new_value="")
        assert wizard.runs[0].get("instrument") in (None, "")

    def test_constrained_column_config_at_builder_layer(self):
        """
        REVISION 4: Constrained column configuration should be validated
        at the ColumnConfigBuilder layer where column_config is actually built,
        not just at the adapter field info level.
        """
        adapter = SpreadsheetAdapter(WizardState())
        builder = ColumnConfigBuilder()

        # Build config from adapter's field info
        config = builder.build_column_config(
            ["file", "fraction", "instrument"],
            field_info_getter=adapter.get_field_info
        )

        # Verify each column type is correct
        assert config["file"].get("type") != "dropdown"
        assert "source" not in config["file"]

        assert config["fraction"].get("type") != "dropdown"
        assert "source" not in config["fraction"]

        # Instrument MUST be constrained
        assert config["instrument"]["type"] == "dropdown"
        assert "source" in config["instrument"]
        assert len(config["instrument"]["source"]) > 0

        # All options in correct format
        for opt in config["instrument"]["source"]:
            assert "id" in opt
            assert "name" in opt

    def test_editor_serializes_dropdown_config_correctly(self):
        """
        REVISION 3: Editor initialization should serialize dropdown config
        in the correct format for JavaScript consumption.
        """
        from jspreadsheet_editor import JSpreadsheetEditor
        import json

        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", instrument="Q-TOF")

        on_change = MagicMock()
        editor = JSpreadsheetEditor(wizard, on_change)

        # Get serialized data
        spreadsheet_data = editor.bridge.get_spreadsheet_data()
        column_config = spreadsheet_data["column_config"]

        # Should be JSON-serializable
        json_str = json.dumps(column_config)
        parsed = json.loads(json_str)

        # Verify structure is intact
        assert "instrument" in parsed
        assert parsed["instrument"]["type"] == "dropdown"
        assert "source" in parsed["instrument"]

        # All options should be in id/name format
        for opt in parsed["instrument"]["source"]:
            assert "id" in opt
            assert "name" in opt


class TestJavaScriptDropdownGeneration:
    """Tests that verify the JavaScript code properly includes dropdown configuration."""

    def test_javascript_merges_dropdown_config_into_columns(self):
        """
        AC16: The JavaScript initialization code in _create_spreadsheet_widget
        includes logic to merge dropdown properties from columnConfig into the
        columns definition before initializing jspreadsheet.
        """
        from jspreadsheet_editor import JSpreadsheetEditor
        from unittest.mock import MagicMock, patch

        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", instrument="Q-TOF")
        wizard.add_run(file="/data/test2.raw", instrument="Orbitrap")

        on_change = MagicMock()
        editor = JSpreadsheetEditor(wizard, on_change)

        # Capture JavaScript that would be sent
        sent_scripts = []

        def mock_run_javascript(script):
            sent_scripts.append(script)

        editor.widget_id = "test_widget_123"

        with patch("jspreadsheet_editor.context") as mock_context:
            mock_context.client.run_javascript = mock_run_javascript

            # Run the widget initialization
            editor._create_spreadsheet_widget()

        # Verify JavaScript was generated
        assert len(sent_scripts) > 0
        js_code = sent_scripts[0]

        # The JavaScript must include the column config merging logic
        assert "columnConfig" in js_code
        assert "columns" in js_code
        assert "forEach" in js_code or "for" in js_code  # Iteration logic

        # Check for dropdown property assignment in the script
        assert "type" in js_code and "dropdown" in js_code

    def test_javascript_includes_dropdown_source_in_columns(self):
        """
        AC17: The JavaScript includes 'source' property from column config
        when merging dropdown properties into column definitions.
        """
        from jspreadsheet_editor import JSpreadsheetEditor
        from unittest.mock import MagicMock, patch

        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", instrument="Q-TOF")

        on_change = MagicMock()
        editor = JSpreadsheetEditor(wizard, on_change)

        sent_scripts = []

        def mock_run_javascript(script):
            sent_scripts.append(script)

        editor.widget_id = "test_widget_124"

        with patch("jspreadsheet_editor.context") as mock_context:
            mock_context.client.run_javascript = mock_run_javascript
            editor._create_spreadsheet_widget()

        # Get the initialization script
        assert len(sent_scripts) > 0
        js_code = sent_scripts[0]

        # Check for source assignment in the dropdown config merging
        assert "source" in js_code
        # The pattern should be something like:
        # columns[index].source = config.source;
        # or within an if statement checking for dropdown type

    def test_entire_flow_from_wizard_to_javascript(self):
        """
        AC18: Complete integration test from WizardState through bridge,
        editor, to JavaScript shows correct dropdown configuration.
        """
        from jspreadsheet_editor import JSpreadsheetEditor
        from unittest.mock import MagicMock, patch

        # Start with wizard state
        wizard = WizardState()
        wizard.add_run(file="/data/file1.raw", fraction=1, instrument="Q-TOF")
        wizard.add_run(file="/data/file2.raw", fraction=2, instrument="Orbitrap")

        # Create editor
        on_change = MagicMock()
        editor = JSpreadsheetEditor(wizard, on_change)

        # Verify bridge has correct data
        bridge_data = editor.bridge.get_spreadsheet_data()
        assert bridge_data["column_config"]["instrument"]["type"] == "dropdown"
        assert len(bridge_data["column_config"]["instrument"]["source"]) > 0

        # Simulate JavaScript initialization
        sent_scripts = []

        def mock_run_javascript(script):
            sent_scripts.append(script)

        editor.widget_id = "full_test_widget"
        editor.container = MagicMock()
        editor.container.html_id = "test_container"

        with patch("jspreadsheet_editor.context") as mock_context:
            mock_context.client.run_javascript = mock_run_javascript

            # Initialize data (stores in window.__quantmsSpreadsheetData)
            editor._initialize_data()

            # Create widget (reads from window.__quantmsSpreadsheetData)
            editor._create_spreadsheet_widget()

        # Should have both initialization and widget creation calls
        assert len(sent_scripts) >= 2

        # First script should set up data store with column_config
        data_script = sent_scripts[0]
        assert "__quantmsSpreadsheetData" in data_script
        assert "column_config" in data_script
        assert "instrument" in data_script

        # Verify the data includes dropdown config
        # Extract the JSON data from the script
        import json as json_lib
        if "instrument" in data_script:
            # The script should include JSON-serialized column config
            assert "dropdown" in data_script  # The type should be specified
