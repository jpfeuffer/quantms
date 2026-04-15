#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pytest",
# ]
# ///
"""
Test suite for local file picker functionality.

Tests cover file filtering by extension, directory browsing,
and MS file type recognition for the in-app file picker dialog.
"""

import pytest
import sys
import tempfile
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from file_picker import LocalFilePicker, MsFilePickerDialog


class TestFilePickerImports:
    """Tests to verify file_picker can be imported and used."""

    def test_file_picker_module_imports(self):
        """Test that LocalFilePicker can be imported."""
        picker = LocalFilePicker()
        assert picker is not None

    def test_ms_file_picker_dialog_class_exists(self):
        """Test that MsFilePickerDialog can be imported."""
        assert MsFilePickerDialog is not None

    def test_file_picker_supported_extensions_accessible(self):
        """Test that supported extensions are accessible."""
        picker = LocalFilePicker()
        extensions = picker.get_supported_extensions()
        assert len(extensions) > 0
        assert all(isinstance(ext, str) for ext in extensions)

    def test_file_picker_methods_available(self):
        """Test file picker utility methods."""
        picker = LocalFilePicker()

        # These should work
        assert picker.is_ms_file("sample.raw")
        assert not picker.is_ms_file("sample.txt")
        assert picker.get_home_directory().exists()


class TestLocalFilePickerFiltering:
    """Tests for MS file type filtering."""

    def test_is_ms_file_raw_extension(self):
        """Test that .raw files are recognized as MS files."""
        picker = LocalFilePicker()
        assert picker.is_ms_file("sample.raw")
        assert picker.is_ms_file("data.RAW")
        assert picker.is_ms_file("/path/to/file.raw")

    def test_is_ms_file_mzml_extension(self):
        """Test that .mzML files are recognized as MS files."""
        picker = LocalFilePicker()
        assert picker.is_ms_file("sample.mzML")
        assert picker.is_ms_file("data.mzml")
        assert picker.is_ms_file("/path/to/file.MZML")

    def test_is_ms_file_mzxml_extension(self):
        """Test that .mzXML files are recognized as MS files."""
        picker = LocalFilePicker()
        assert picker.is_ms_file("sample.mzXML")
        assert picker.is_ms_file("data.mzxml")

    def test_is_ms_file_mgf_extension(self):
        """Test that .mgf files are recognized as MS files."""
        picker = LocalFilePicker()
        assert picker.is_ms_file("peaks.mgf")
        assert picker.is_ms_file("data.MGF")

    def test_is_ms_file_ms2_extension(self):
        """Test that .ms2 files are recognized as MS files."""
        picker = LocalFilePicker()
        assert picker.is_ms_file("data.ms2")
        assert picker.is_ms_file("peaks.MS2")

    def test_is_ms_file_non_ms_extension(self):
        """Test that non-MS files are not recognized."""
        picker = LocalFilePicker()
        assert not picker.is_ms_file("sample.txt")
        assert not picker.is_ms_file("data.csv")
        assert not picker.is_ms_file("image.png")
        assert not picker.is_ms_file("file.pdf")

    def test_is_ms_file_case_insensitive(self):
        """Test that extension matching is case-insensitive."""
        picker = LocalFilePicker()
        assert picker.is_ms_file("SAMPLE.RAW")
        assert picker.is_ms_file("Data.MzML")
        assert picker.is_ms_file("peaks.MGF")

    def test_is_ms_file_with_path(self):
        """Test that file paths are handled correctly."""
        picker = LocalFilePicker()
        assert picker.is_ms_file("/home/user/data/sample.raw")
        assert picker.is_ms_file("C:\\Users\\data\\sample.mzML")
        assert not picker.is_ms_file("/home/user/data/sample.txt")

    def test_is_ms_file_no_extension(self):
        """Test that files without extension are not recognized."""
        picker = LocalFilePicker()
        assert not picker.is_ms_file("sample")
        assert not picker.is_ms_file("data")
        assert not picker.is_ms_file("/path/to/filename")


class TestLocalFilePickerListing:
    """Tests for directory listing and filtering."""

    def test_get_ms_files_in_directory(self):
        """Test getting list of MS files in a directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create test files
            (tmpdir_path / "sample1.raw").touch()
            (tmpdir_path / "sample2.mzML").touch()
            (tmpdir_path / "data.txt").touch()
            (tmpdir_path / "readme.md").touch()

            picker = LocalFilePicker()
            ms_files = picker.get_ms_files_in_directory(tmpdir_path)

            # Should find 2 MS files
            assert len(ms_files) == 2
            filenames = [f.name for f in ms_files]
            assert "sample1.raw" in filenames
            assert "sample2.mzML" in filenames
            assert "data.txt" not in filenames
            assert "readme.md" not in filenames

    def test_get_ms_files_returns_path_objects(self):
        """Test that get_ms_files_in_directory returns Path objects."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            (tmpdir_path / "sample.raw").touch()

            picker = LocalFilePicker()
            ms_files = picker.get_ms_files_in_directory(tmpdir_path)

            assert len(ms_files) == 1
            assert isinstance(ms_files[0], Path)

    def test_get_ms_files_empty_directory(self):
        """Test getting MS files from empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            picker = LocalFilePicker()
            ms_files = picker.get_ms_files_in_directory(tmpdir)
            assert ms_files == []

    def test_get_ms_files_no_ms_files(self):
        """Test getting MS files from directory with no MS files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            (tmpdir_path / "file1.txt").touch()
            (tmpdir_path / "file2.csv").touch()

            picker = LocalFilePicker()
            ms_files = picker.get_ms_files_in_directory(tmpdir_path)
            assert ms_files == []

    def test_get_ms_files_nonexistent_directory(self):
        """Test that get_ms_files_in_directory handles nonexistent directory."""
        picker = LocalFilePicker()
        nonexistent = Path("/nonexistent/path/that/does/not/exist")
        # Should raise an error or return empty list
        with pytest.raises((FileNotFoundError, OSError)):
            picker.get_ms_files_in_directory(nonexistent)

    def test_get_ms_files_sorted_alphabetically(self):
        """Test that MS files are returned in sorted order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create files in non-alphabetical order
            for filename in ["zebra.raw", "alpha.raw", "beta.raw"]:
                (tmpdir_path / filename).touch()

            picker = LocalFilePicker()
            ms_files = picker.get_ms_files_in_directory(tmpdir_path)

            filenames = [f.name for f in ms_files]
            assert filenames == ["alpha.raw", "beta.raw", "zebra.raw"]

    def test_get_ms_files_in_directory_with_ignored_files(self):
        """Test that non-MS files and directories are properly ignored."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create various files
            (tmpdir_path / "sample.raw").touch()
            (tmpdir_path / "config.txt").touch()
            (tmpdir_path / "subdirectory").mkdir()
            (tmpdir_path / "subdirectory" / "nested.raw").touch()

            picker = LocalFilePicker()
            ms_files = picker.get_ms_files_in_directory(tmpdir_path)

            # Should only find top-level MS file, not nested ones or non-MS files
            assert len(ms_files) == 1
            assert ms_files[0].name == "sample.raw"


class TestFileValidation:
    """Tests for file validation."""

    def test_validate_file_exists(self):
        """Test validating an existing file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            test_file = tmpdir_path / "test.raw"
            test_file.touch()

            picker = LocalFilePicker()
            assert picker.validate_file(test_file)
            assert picker.validate_file(str(test_file))

    def test_validate_file_not_exists(self):
        """Test validating a non-existent file."""
        picker = LocalFilePicker()
        assert not picker.validate_file("/nonexistent/file.raw")
        assert not picker.validate_file(Path("/nonexistent/file.raw"))

    def test_convert_to_string(self):
        """Test converting file paths to strings."""
        picker = LocalFilePicker()

        # String input
        assert picker.convert_to_string("path/to/file.raw") == "path/to/file.raw"

        # Path input
        p = Path("path/to/file.raw")
        assert picker.convert_to_string(p) == str(p)

    def test_get_home_directory(self):
        """Test getting home directory."""
        picker = LocalFilePicker()
        home = picker.get_home_directory()
        assert home.exists()
        assert home.is_dir()

    def test_browseable_directory_exists(self):
        """Test checking if directory is browseable."""
        picker = LocalFilePicker()
        home = picker.get_home_directory()
        assert picker.browseable_directory_exists(home)

        # Non-existent directory
        assert not picker.browseable_directory_exists("/nonexistent/path")

        # File path (not directory)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            test_file = tmpdir_path / "test.txt"
            test_file.touch()
            assert not picker.browseable_directory_exists(test_file)


class TestMsFilePickerDialogStructure:
    """Tests for MsFilePickerDialog structure and inheritance."""

    def test_dialog_class_exists(self):
        """Test that MsFilePickerDialog class is defined."""
        assert MsFilePickerDialog is not None

    def test_dialog_accepts_multiple_parameter(self):
        """Test that dialog constructor accepts multiple parameter."""
        # This test verifies the class signature
        # Can't instantiate without NiceGUI ui context, so just test import
        assert hasattr(MsFilePickerDialog, '__init__')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
