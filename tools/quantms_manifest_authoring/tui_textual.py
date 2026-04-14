#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "textual",
#   "pyyaml",
# ]
# ///
"""
Terminal User Interface (TUI) for quantms YAML manifest authoring.

Provides a Textual-based interactive terminal application for creating and editing
quantms YAML manifests with validation feedback.
"""

import sys
from pathlib import Path
from typing import Optional

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from textual.app import ComposeResult, App, on
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import Header, Footer, Button, Input, Select, Static, Label, TextArea
from textual.binding import Binding
import yaml

from manifest_core import ManifestState, ChannelBuilder, validate_manifest


class ExperimentSection(Container):
    """Interactive form for experiment configuration."""

    BORDER_TITLE = "Experiment Configuration"

    def compose(self) -> ComposeResult:
        """Create experiment input form."""
        with Vertical(id="experiment-form"):
            yield Label("Acquisition Method:", classes="form-label")
            yield Select(
                options=[("DDA", "DDA"), ("DIA", "DIA")],
                id="acq_method",
                value="DDA",
            )
            yield Label("Enzyme:", classes="form-label")
            yield Input(
                placeholder="e.g., Trypsin",
                id="enzyme",
                value="Trypsin",
            )
            yield Label("Quantification Method:", classes="form-label")
            yield Select(
                options=[
                    ("None", ""),
                    ("LFQ", "LFQ"),
                    ("TMT", "TMT"),
                    ("iTRAQ", "iTRAQ"),
                    ("SILAC", "SILAC"),
                ],
                id="quant_method",
                value="",
            )
            yield Label("Dissociation Method:", classes="form-label")
            yield Input(
                placeholder="e.g., HCD",
                id="dissociation",
            )


class SamplesSection(Container):
    """Interactive form for sample management."""

    BORDER_TITLE = "Samples"

    def compose(self) -> ComposeResult:
        """Create samples form."""
        with Vertical(id="samples-form"):
            yield Label("Sample ID:", classes="form-label")
            yield Input(placeholder="e.g., sample_1", id="sample_id")
            yield Label("Organism:", classes="form-label")
            yield Input(placeholder="e.g., homo sapiens", id="organism")
            yield Label("Organism Part:", classes="form-label")
            yield Input(placeholder="e.g., liver", id="organism_part")
            yield Label("Condition:", classes="form-label")
            yield Input(placeholder="e.g., treated", id="condition")
            yield Label("Biological Replicate:", classes="form-label")
            yield Input(placeholder="1", id="bio_replicate")
            with Horizontal():
                yield Button("Add Sample", id="add-sample", variant="primary")
                yield Button("Clear", id="clear-sample")


class MixturesSection(Container):
    """Interactive form for mixture management."""

    BORDER_TITLE = "Multiplex Mixtures"

    def compose(self) -> ComposeResult:
        """Create mixtures form."""
        with Vertical(id="mixtures-form"):
            yield Label("Mixture ID:", classes="form-label")
            yield Input(placeholder="e.g., mix_1", id="mixture_id")
            yield Label("Plex Type:", classes="form-label")
            plex_options = [
                (p, p) for p in ChannelBuilder.get_supported_plex_types()
            ]
            yield Select(
                options=plex_options,
                id="plex_type",
                value="TMT6",
            )
            yield Label("Channel Assignments:", classes="form-label")
            with ScrollableContainer(id="channels-container"):
                yield Label("Select plex type above", id="channel-list")
            with Horizontal():
                yield Button("Add Mixture", id="add-mixture", variant="primary")
                yield Button("Clear", id="clear-mixture")


class RunsSection(Container):
    """Interactive form for run management."""

    BORDER_TITLE = "Raw Data Runs"

    def compose(self) -> ComposeResult:
        """Create runs form."""
        with Vertical(id="runs-form"):
            yield Label("File Path:", classes="form-label")
            yield Input(placeholder="e.g., s3://bucket/file.raw", id="run_file")
            yield Label("Mixture ID (optional for LFQ):", classes="form-label")
            yield Input(placeholder="e.g., mix_1", id="run_mixture")
            yield Label("Fraction:", classes="form-label")
            yield Input(placeholder="1", id="run_fraction")
            with Horizontal():
                yield Button("Add Run", id="add-run", variant="primary")
                yield Button("Clear", id="clear-run")


class ManifestViewer(Static):
    """Display current manifest YAML."""

    DEFAULT_CSS = """
    ManifestViewer {
        border: solid $primary;
        padding: 1;
        height: 100%;
    }
    """

    def render(self) -> str:
        """Render current manifest status."""
        if not hasattr(self, "manifest"):
            return "Manifest will appear here as you add samples, mixtures, and runs."
        try:
            yaml_output = self.manifest.to_yaml()
            return f"```yaml\n{yaml_output}\n```"
        except Exception as e:
            return f"Error rendering manifest: {e}"


class ValidationPanel(Static):
    """Display validation feedback."""

    DEFAULT_CSS = """
    ValidationPanel {
        border: solid $error;
        padding: 1;
        height: auto;
        color: $error;
    }
    """

    def render(self) -> str:
        """Render validation messages."""
        if not hasattr(self, "issues"):
            return "Validation messages will appear here."
        if not self.issues:
            return "[green]✓ Manifest is valid![/green]"
        lines = []
        for issue in self.issues:
            level = issue.get("level", "").upper()
            msg = issue.get("message", "")
            color = "$error" if level == "ERROR" else "$warning"
            lines.append(f"[{color}]{level}[/{color}]: {msg}")
        return "\n".join(lines)


class ManifestAuthoring(App):
    """Main TUI app for manifest authoring."""

    CSS_PATH = None
    TITLE = "quantms YAML Manifest Authoring"
    SUB_TITLE = "Terminal Interface"

    BINDINGS = [
        Binding("ctrl+s", "save_manifest", "Save"),
        Binding("ctrl+l", "load_manifest", "Load"),
        Binding("ctrl+q", "quit", "Quit"),
        Binding("tab", "focus_next", "Next"),
        Binding("shift+tab", "focus_previous", "Previous"),
    ]

    DEFAULT_CSS = """
    Screen {
        layout: vertical;
    }

    Header {
        dock: top;
    }

    Footer {
        dock: bottom;
    }

    #main-container {
        height: 1fr;
        layout: vertical;
    }

    #form-container {
        height: 1fr;
        layout: vertical;
    }

    .form-label {
        color: $text-muted;
        margin-top: 1;
    }

    .channel-label {
        color: $text-muted;
        width: 1fr;
        margin-right: 1;
    }

    Input {
        margin-bottom: 1;
    }

    Select {
        margin-bottom: 1;
    }

    Button {
        margin-right: 1;
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        """Create the TUI layout."""
        yield Header()
        with Container(id="main-container"):
            # Add a message display area at the top
            self.message_label = Label("", id="message-display")
            yield self.message_label
            with Horizontal():
                with Vertical(id="form-container"):
                    yield ExperimentSection(id="experiment-section")
                    yield SamplesSection(id="samples-section")
                    yield MixturesSection(id="mixtures-section")
                    yield RunsSection(id="runs-section")
                yield ManifestViewer(id="manifest-viewer")
            yield ValidationPanel(id="validation-panel")
        yield Footer()

        self.manifest = ManifestState()

    def on_mount(self) -> None:
        """Initialize UI after mounting."""
        # Initialize the channel assignments for the default plex type
        try:
            plex_type = self.query_one("#plex_type", Select).value
            container = self.query_one("#channels-container", ScrollableContainer)
            # Clear the default label
            container.query("*").remove()
            # Show message that samples need to be added first
            container.mount(Label("Add samples first to assign channels"))
        except Exception:
            # If initialization fails, continue anyway
            pass

    @on(Button.Pressed, "#add-sample")
    def action_add_sample(self) -> None:
        """Handle adding a sample."""
        sample_id = self.query_one("#sample_id", Input).value
        organism = self.query_one("#organism", Input).value
        organism_part = self.query_one("#organism_part", Input).value
        condition = self.query_one("#condition", Input).value
        bio_rep = self.query_one("#bio_replicate", Input).value

        if not sample_id:
            self._show_message("Sample ID is required")
            return

        try:
            bio_rep = int(bio_rep) if bio_rep else None
            self.manifest.add_sample(
                id=sample_id,
                organism=organism or None,
                organism_part=organism_part or None,
                condition=condition or None,
                biological_replicate=bio_rep,
            )
            self._refresh_views()
            self._clear_sample_form()

            # Rebuild channel assignments now that samples have changed
            plex_type = self.query_one("#plex_type", Select).value
            self._rebuild_channel_assignments(plex_type)

            self._show_message(f"Added sample: {sample_id}")
        except Exception as e:
            self._show_message(f"Error adding sample: {e}")

    @on(Button.Pressed, "#clear-sample")
    def action_clear_sample_form(self) -> None:
        """Clear sample form."""
        self._clear_sample_form()

    @on(Select.Changed, "#plex_type")
    def action_plex_type_changed(self) -> None:
        """Handle plex type change - rebuild channel assignment widgets."""
        plex_type = self.query_one("#plex_type", Select).value
        self._rebuild_channel_assignments(plex_type)

    def _rebuild_channel_assignments(self, plex_type: str) -> None:
        """Rebuild the channel-to-sample assignment widgets for a given plex type."""
        try:
            builder = ChannelBuilder(plex_type)
            channels = builder.get_available_channels()

            # Clear existing widgets from channels container
            container = self.query_one("#channels-container", ScrollableContainer)
            container.query("*").remove()

            # Create Select widgets for each channel to assign samples
            if self.manifest.samples:
                sample_options = [(s.id, s.id) for s in self.manifest.samples]

                for channel in channels:
                    # Create channel label
                    label = Label(f"{channel}:")
                    label.add_class("channel-label")
                    container.mount(label)

                    # Create channel assignment select
                    select = Select(
                        options=sample_options,
                        id=f"channel_{channel}",
                        value=sample_options[0][0] if sample_options else "",
                    )
                    container.mount(select)
            else:
                # If no samples yet, show a message
                container.mount(Label("Add samples first to assign channels"))
        except Exception as e:
            container = self.query_one("#channels-container", ScrollableContainer)
            container.query("*").remove()
            container.mount(Label(f"Error setting up channels: {e}"))

    @on(Button.Pressed, "#add-mixture")
    def action_add_mixture(self) -> None:
        """Handle adding a mixture with channel-to-sample assignments from widgets."""
        mixture_id = self.query_one("#mixture_id", Input).value
        plex_type = self.query_one("#plex_type", Select).value

        if not mixture_id or not plex_type:
            self._show_message("Mixture ID and Plex Type are required")
            return

        try:
            if not self.manifest.samples:
                self._show_message("Add samples before creating mixtures")
                return

            # Read channel assignments from the Select widgets
            builder = ChannelBuilder(plex_type)
            available_channels = builder.get_available_channels()
            channels = {}

            for channel in available_channels:
                try:
                    select = self.query_one(f"#channel_{channel}", Select)
                    sample_id = select.value
                    if sample_id:
                        channels[channel] = sample_id
                except Exception:
                    # If widget doesn't exist, skip this channel
                    pass

            # Validate at least one channel has an assignment (schema requires minProperties: 1)
            if not channels:
                self._show_message("At least one channel must be assigned a sample")
                return

            self.manifest.add_mixture(
                id=mixture_id,
                channels=channels,
            )
            self._refresh_views()
            self._clear_mixture_form()
            self._show_message(f"Added mixture: {mixture_id} ({len(channels)} channels)")
        except Exception as e:
            self._show_message(f"Error adding mixture: {e}")

    @on(Button.Pressed, "#clear-mixture")
    def action_clear_mixture_form(self) -> None:
        """Clear mixture form."""
        self._clear_mixture_form()

    @on(Button.Pressed, "#add-run")
    def action_add_run(self) -> None:
        """Handle adding a run."""
        run_file = self.query_one("#run_file", Input).value
        run_mixture = self.query_one("#run_mixture", Input).value
        run_fraction = self.query_one("#run_fraction", Input).value

        if not run_file:
            self._show_message("File path is required")
            return

        try:
            fraction = int(run_fraction) if run_fraction else None
            self.manifest.add_run(
                file=run_file,
                mixture=run_mixture or None,
                fraction=fraction,
            )
            self._refresh_views()
            self._clear_run_form()
            self._show_message(f"Added run: {run_file}")
        except Exception as e:
            self._show_message(f"Error adding run: {e}")

    @on(Button.Pressed, "#clear-run")
    def action_clear_run_form(self) -> None:
        """Clear run form."""
        self._clear_run_form()

    def action_save_manifest(self) -> None:
        """Save manifest to file."""
        # Set experiment from form
        acq_method = self.query_one("#acq_method", Select).value or "DDA"
        enzyme = self.query_one("#enzyme", Input).value or "Trypsin"

        self.manifest.set_experiment(
            acquisition_method=acq_method,
            enzyme=enzyme,
            quantification_method=self.query_one("#quant_method", Select).value or None,
            dissociation_method=self.query_one("#dissociation", Input).value or None,
        )

        # Validate
        issues = validate_manifest(self.manifest)
        errors = [i for i in issues if i.get("level") == "error"]
        if errors:
            self._show_message(f"Cannot save: {len(errors)} validation error(s)")
            return

        try:
            output_file = Path.home() / "quantms_manifest.yml"
            self.manifest.save_to_file(output_file)
            self._show_message(f"Manifest saved to {output_file}")
        except Exception as e:
            self._show_message(f"Error saving manifest: {e}")

    def action_load_manifest(self) -> None:
        """Load manifest from file."""
        try:
            input_file = Path.home() / "quantms_manifest.yml"
            if input_file.exists():
                self.manifest = ManifestState.load_from_file(input_file)
                self._refresh_views()
                self._show_message(f"Loaded manifest from {input_file}")
            else:
                self._show_message(f"File not found: {input_file}")
        except Exception as e:
            self._show_message(f"Error loading manifest: {e}")

    def action_quit(self) -> None:
        """Exit the application."""
        self.app.exit()

    def _clear_sample_form(self) -> None:
        """Clear sample form inputs."""
        self.query_one("#sample_id", Input).value = ""
        self.query_one("#organism", Input).value = ""
        self.query_one("#organism_part", Input).value = ""
        self.query_one("#condition", Input).value = ""
        self.query_one("#bio_replicate", Input).value = ""

    def _clear_mixture_form(self) -> None:
        """Clear mixture form inputs."""
        self.query_one("#mixture_id", Input).value = ""

    def _clear_run_form(self) -> None:
        """Clear run form inputs."""
        self.query_one("#run_file", Input).value = ""
        self.query_one("#run_mixture", Input).value = ""
        self.query_one("#run_fraction", Input).value = ""

    def _refresh_views(self) -> None:
        """Refresh manifest viewer and validation panel."""
        # Update manifest viewer
        viewer = self.query_one("#manifest-viewer", ManifestViewer)
        viewer.manifest = self.manifest
        viewer.refresh()

        # Update validation panel
        issues = validate_manifest(self.manifest)
        validation_panel = self.query_one("#validation-panel", ValidationPanel)
        validation_panel.issues = issues
        validation_panel.refresh()

    def _show_message(self, message: str) -> None:
        """Show a message to the user in the message display area."""
        self.message_label.update(f"[green]✓[/green] {message}" if "Added" in message or "Loaded" in message or "saved" in message else f"[yellow]ℹ[/yellow] {message}" if "required" in message.lower() else f"[red]✗[/red] {message}")
        self._refresh_views()


def run_tui() -> None:
    """Run the TUI application."""
    app = ManifestAuthoring()
    app.run()


if __name__ == "__main__":
    run_tui()
