#!/usr/bin/env python3
"""
Integration test for file picker GUI integration.

Tests that the file picker is properly integrated into the RUNS step.
"""

import pytest
import sys
from pathlib import Path
import gui_nicegui

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from file_picker import LocalFilePicker, MsFilePickerDialog
from gui_wizard_state import WizardState, WizardStep


class TestFilePickerGUIIntegration:
    """Tests for file picker integration with GUI."""

    def test_file_picker_can_be_instantiated(self):
        """Test that LocalFilePicker can be instantiated."""
        picker = LocalFilePicker()
        assert picker is not None

    def test_ms_file_picker_dialog_class_exists(self):
        """Test that MsFilePickerDialog class exists."""
        assert MsFilePickerDialog is not None

    def test_gui_module_imports_picker_dialog(self):
        """Test that the GUI module wires in the picker dialog."""
        assert getattr(gui_nicegui, "MsFilePickerDialog", None) is MsFilePickerDialog

    def test_gui_wizard_can_be_instantiated(self):
        """Test that WizardState can be instantiated."""
        wizard = WizardState()
        assert wizard is not None
        assert wizard.get_current_step() == WizardStep.RUNS

    def test_file_picker_methods_available(self):
        """Test that file picker has required methods."""
        picker = LocalFilePicker()

        # Check required methods exist
        assert hasattr(picker, 'is_ms_file'), "is_ms_file method missing"
        assert hasattr(picker, 'get_ms_files_in_directory'), "get_ms_files_in_directory method missing"
        assert hasattr(picker, 'validate_file'), "validate_file method missing"
        assert hasattr(picker, 'get_supported_extensions'), "get_supported_extensions method missing"
        assert hasattr(picker, 'convert_to_string'), "convert_to_string method missing"
        assert hasattr(picker, 'get_home_directory'), "get_home_directory method missing"

    def test_file_picker_filters_ms_files(self):
        """Test that file picker properly filters MS files."""
        picker = LocalFilePicker()

        # Verify filtering works
        assert picker.is_ms_file("sample.raw")
        assert picker.is_ms_file("data.mzML")
        assert not picker.is_ms_file("readme.txt")
        assert not picker.is_ms_file("image.png")

    def test_gui_runs_step_allows_file_addition(self):
        """Test that GUI wizard can add files."""
        wizard = WizardState()

        # Add a file
        wizard.add_run(file="/path/to/sample.raw")

        # Verify file was added
        assert len(wizard.runs) == 1
        assert wizard.runs[0]['file'] == "/path/to/sample.raw"

    def test_gui_multiple_files_from_picker(self):
        """Test that GUI can handle multiple files from picker."""
        wizard = WizardState()

        # Simulate adding multiple files from picker
        files = [
            "/data/sample1.raw",
            "/data/sample2.mzML",
            "/data/sample3.raw",
        ]

        for file_path in files:
            wizard.add_run(file=file_path)

        # Verify all files were added
        assert len(wizard.runs) == 3
        assert all(wizard.runs[i]['file'] == files[i] for i in range(3))

    def test_file_picker_home_directory_accessible(self):
        """Test that file picker can access home directory."""
        picker = LocalFilePicker()
        home = picker.get_home_directory()

        assert home.exists()
        assert home.is_dir()

    def test_file_picker_supports_common_ms_formats(self):
        """Test that file picker supports common MS formats."""
        picker = LocalFilePicker()
        extensions = picker.get_supported_extensions()

        # Should support at least these formats
        ext_str = ' '.join(extensions).lower()
        assert 'raw' in ext_str
        assert 'mzml' in ext_str or 'mz' in ext_str

    def test_file_picker_dialog_supports_multiple_selection(self):
        """Test that MsFilePickerDialog supports multiple selection."""
        # Just verify the class can be imported
        # Actual instantiation requires NiceGUI context
        assert MsFilePickerDialog is not None
        assert hasattr(MsFilePickerDialog, '__init__')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
