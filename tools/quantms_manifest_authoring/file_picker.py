#!/usr/bin/env python3
"""
Local filesystem file picker dialog for quantms manifest authoring GUI.

Provides NiceGUI-based in-app file picker dialog for browsing local server
filesystem and filtering for relevant MS data file types
(.raw, .mzML, .mzXML, .mgf, .ms2).

Uses a ui.dialog-based approach following the NiceGUI local_file_picker
example pattern, which provides server-side directory browsing within the
application rather than native OS dialogs.
"""

from pathlib import Path
from typing import List, Union

from nicegui import ui, events


class LocalFilePicker:
    """Helper utilities for MS file filtering and validation."""

    # Supported MS file types
    SUPPORTED_MS_EXTENSIONS = {".raw", ".mzml", ".mzxml", ".mgf", ".ms2"}

    def __init__(self):
        """Initialize the local file picker utilities."""
        pass

    def get_supported_extensions(self) -> List[str]:
        """
        Get list of supported file extensions.

        Returns:
            List of extension strings suitable for UI display.
        """
        return [
            "*.raw (Thermo RAW)",
            "*.mzML (mzML)",
            "*.mzXML (mzXML)",
            "*.mgf (Mascot Generic Format)",
            "*.ms2 (MS2)",
        ]

    def is_ms_file(self, filepath: Union[str, Path]) -> bool:
        """
        Check if a file has a recognized MS file extension.

        Args:
            filepath: Path to the file (string or Path object).

        Returns:
            True if file has a recognized MS extension, False otherwise.
        """
        if isinstance(filepath, str):
            filepath = Path(filepath)
        elif not isinstance(filepath, Path):
            return False

        # Get extension and normalize to lowercase
        ext = filepath.suffix.lower()
        return ext in self.SUPPORTED_MS_EXTENSIONS

    def get_ms_files_in_directory(self, directory: Union[str, Path]) -> List[Path]:
        """
        Get all MS files in a directory (non-recursive).

        Args:
            directory: Path to the directory to scan.

        Returns:
            List of Path objects for MS files in the directory,
            sorted alphabetically by filename.

        Raises:
            FileNotFoundError: If directory does not exist.
            OSError: If directory cannot be read.
        """
        if isinstance(directory, str):
            directory = Path(directory)

        if not directory.exists():
            raise FileNotFoundError(f"Directory does not exist: {directory}")

        if not directory.is_dir():
            raise OSError(f"Not a directory: {directory}")

        # Collect all MS files
        ms_files = [f for f in directory.iterdir() if f.is_file() and self.is_ms_file(f)]

        # Sort alphabetically by name
        return sorted(ms_files, key=lambda p: p.name)

    def validate_file(self, filepath: Union[str, Path]) -> bool:
        """
        Validate that a file exists and is readable.

        Args:
            filepath: Path to the file to validate.

        Returns:
            True if file exists and is readable, False otherwise.
        """
        if isinstance(filepath, str):
            filepath = Path(filepath)
        elif not isinstance(filepath, Path):
            return False

        try:
            return filepath.exists() and filepath.is_file()
        except (OSError, ValueError):
            return False

    def convert_to_string(self, filepath: Union[str, Path]) -> str:
        """
        Convert a file path to a string representation.

        Args:
            filepath: The filepath (string or Path object).

        Returns:
            String representation of the filepath (absolute path).
        """
        if isinstance(filepath, str):
            return filepath
        elif isinstance(filepath, Path):
            return str(filepath)
        else:
            return str(filepath)

    def get_home_directory(self) -> Path:
        """
        Get the user's home directory.

        Returns:
            Path object for the home directory.
        """
        return Path.home()

    def browseable_directory_exists(self, directory: Union[str, Path]) -> bool:
        """
        Check if a directory exists and is browseable.

        Args:
            directory: Path to the directory.

        Returns:
            True if directory exists and is accessible, False otherwise.
        """
        if isinstance(directory, str):
            directory = Path(directory)

        try:
            return directory.exists() and directory.is_dir()
        except (OSError, ValueError):
            return False


class MsFilePickerDialog(ui.dialog):
    """
    NiceGUI dialog for browsing local server filesystem and selecting MS data files.

    Provides server-side directory browsing with filtering for MS file formats.
    Supports single or multiple file selection.

    Usage:
        async def select_files():
            result = await MsFilePickerDialog(multiple=True)
            # result is a list of selected file paths
    """

    def __init__(self, multiple: bool = True):
        """
        Initialize the MS file picker dialog.

        Args:
            multiple: Whether to allow multiple file selection (default: True).
        """
        super().__init__()

        self.picker = LocalFilePicker()
        self.path = self.picker.get_home_directory()
        self.multiple = multiple

        # Build dialog UI
        with self, ui.card():
            # Header with path navigation
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Select MS Data Files").classes("text-lg font-bold")
                self.path_label = ui.label(str(self.path)).classes("text-xs text-gray-500")

            # File grid
            self.grid = ui.aggrid(
                {
                    "columnDefs": [{"field": "name", "headerName": "File"}],
                    "rowSelection": {
                        "mode": "multiRow" if multiple else "singleRow"
                    },
                },
                html_columns=[0],
            ).classes("w-96").on("cellDoubleClicked", self.handle_double_click)

            # Navigation buttons
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancel", on_click=self.close).props("outline")
                ui.button("Ok", on_click=self._handle_ok)

            # Update grid on dialog open
            self.update_grid()

    def update_grid(self) -> None:
        """Update the grid with files and directories in the current path."""
        self.path_label.set_text(str(self.path))
        try:
            paths = list(self.path.glob("*"))
        except (OSError, PermissionError):
            # If we can't read the directory, show empty
            paths = []

        # Filter hidden files
        paths = [p for p in paths if not p.name.startswith(".")]

        # Sort: directories first, then by name
        paths.sort(key=lambda p: p.name.lower())
        paths.sort(key=lambda p: not p.is_dir())

        # Build row data
        row_data = []

        # Add parent directory navigation (if not at home or above)
        home = self.picker.get_home_directory()
        if self.path != home and self.path.parent != self.path:
            row_data.append({
                "name": '📁 <strong>..</strong>',
                "path": str(self.path.parent),
                "is_dir": True,
            })

        # Add directories and MS files
        for p in paths:
            if p.is_dir():
                row_data.append({
                    "name": f"📁 <strong>{p.name}</strong>",
                    "path": str(p),
                    "is_dir": True,
                })
            elif self.picker.is_ms_file(p):
                row_data.append({
                    "name": p.name,
                    "path": str(p),
                    "is_dir": False,
                })

        self.grid.options["rowData"] = row_data
        self.grid.update()

    def handle_double_click(self, e: events.GenericEventArguments) -> None:
        """Handle double-clicking a file or directory."""
        row_data = e.args.get("data", {})
        path_str = row_data.get("path")
        is_dir = row_data.get("is_dir", False)

        if not path_str:
            return

        self.path = Path(path_str)

        if is_dir:
            # Navigate into directory
            self.update_grid()
        else:
            # Select single file on double-click
            self.submit([str(self.path)])

    async def _handle_ok(self):
        """Submit selected files when OK button is clicked."""
        rows = await self.grid.get_selected_rows()
        selected_paths = [r["path"] for r in rows if not r.get("is_dir", False)]

        if selected_paths:
            self.submit(selected_paths)
        else:
            ui.notify("No files selected", type="warning")
