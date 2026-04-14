#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "nicegui",
#   "fastapi",
#   "uvicorn",
#   "pyyaml",
# ]
# ///
"""
Web GUI for quantms YAML manifest authoring using NiceGUI.

Provides a web-based interactive interface for creating and editing
quantms YAML manifests with real-time validation feedback.
"""

import sys
from pathlib import Path
from typing import Optional, Dict, List

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from nicegui import ui, app as nicegui_app
import json
from manifest_core import ManifestState, ChannelBuilder, validate_manifest


class ManifestEditor:
    """Manages the manifest editing state and UI."""

    def __init__(self):
        """Initialize the editor."""
        self.manifest = ManifestState()
        self.validation_issues = []

    def refresh_validation(self) -> None:
        """Update validation feedback."""
        self.validation_issues = validate_manifest(self.manifest)

    def get_validation_messages(self) -> List[str]:
        """Get formatted validation messages."""
        messages = []
        for issue in self.validation_issues:
            level = issue.get("level", "").upper()
            msg = issue.get("message", "")
            field = issue.get("field", "")
            messages.append(f"[{level}] {msg}" + (f" ({field})" if field else ""))
        return messages


def create_manifest_editor_ui(editor: ManifestEditor) -> None:
    """Create the main UI."""

    with ui.column().classes("w-full"):
        ui.label("quantms YAML Manifest Authoring").classes("text-2xl font-bold")

        # Create tabs and tab panels with proper structure
        with ui.tabs().classes("w-full") as tabs:
            # Add tab labels first
            exp_tab = tabs.add_tab("Experiment")
            smp_tab = tabs.add_tab("Samples")
            mix_tab = tabs.add_tab("Mixtures")
            run_tab = tabs.add_tab("Runs")

        # Create tab panel content - store references for refresh
        tab_contents = {}

        with ui.tab_panels(tabs, value=exp_tab.name).classes("w-full"):
            # Experiment tab panel
            with ui.tab_panel(exp_tab.name):
                with ui.card().classes("w-full"):
                    acq_method = ui.select(
                        options={"DDA": "DDA", "DIA": "DIA"},
                        value="DDA",
                        label="Acquisition Method",
                    ).classes("w-full")
                    enzyme = ui.input(
                        label="Enzyme",
                        value="Trypsin",
                        placeholder="e.g., Trypsin",
                    ).classes("w-full")
                    quant_method = ui.select(
                        options={
                            "": "None",
                            "LFQ": "LFQ",
                            "TMT": "TMT",
                            "iTRAQ": "iTRAQ",
                            "SILAC": "SILAC",
                        },
                        label="Quantification Method",
                    ).classes("w-full")
                    dissociation = ui.input(
                        label="Dissociation Method",
                        placeholder="e.g., HCD",
                    ).classes("w-full")

                    def update_experiment():
                        editor.manifest.set_experiment(
                            acquisition_method=acq_method.value,
                            enzyme=enzyme.value,
                            quantification_method=quant_method.value or None,
                            dissociation_method=dissociation.value or None,
                        )
                        refresh_entire_ui()

                    ui.button(
                        "Update Experiment",
                        on_click=lambda: update_experiment(),
                    ).classes("w-full mt-4")

            # Samples tab panel
            with ui.tab_panel(smp_tab.name):
                with ui.card().classes("w-full"):
                    sample_id = ui.input(
                        label="Sample ID",
                        placeholder="e.g., sample_1",
                    )
                    organism = ui.input(
                        label="Organism",
                        placeholder="e.g., homo sapiens",
                    )
                    organism_part = ui.input(
                        label="Organism Part",
                        placeholder="e.g., liver",
                    )
                    condition = ui.input(
                        label="Condition",
                        placeholder="e.g., treated",
                    )
                    bio_rep = ui.input(
                        label="Biological Replicate",
                        type="number",
                        value="1",
                    )

                    def add_sample():
                        if not sample_id.value:
                            ui.notify("Sample ID is required")
                            return
                        try:
                            editor.manifest.add_sample(
                                id=sample_id.value,
                                organism=organism.value or None,
                                organism_part=organism_part.value or None,
                                condition=condition.value or None,
                                biological_replicate=int(bio_rep.value) if bio_rep.value else None,
                            )
                            ui.notify(f"Sample '{sample_id.value}' added")
                            sample_id.value = ""
                            organism.value = ""
                            organism_part.value = ""
                            condition.value = ""
                            bio_rep.value = "1"
                            refresh_entire_ui()
                        except Exception as e:
                            ui.notify(f"Error: {e}", type="negative")

                    ui.button(
                        "Add Sample",
                        on_click=add_sample,
                    ).classes("w-full mt-4")

                    # Display current samples
                    with ui.expansion(
                        text="Current Samples",
                        icon="list",
                    ).classes("w-full mt-4"):
                        samples_list = ui.column().classes("w-full")

                        def update_samples_list():
                            samples_list.clear()
                            for sample in editor.manifest.samples:
                                with samples_list:
                                    ui.label(
                                        f"ID: {sample.id} | "
                                        f"Organism: {sample.organism or 'N/A'} | "
                                        f"Condition: {sample.condition or 'N/A'}"
                                    ).classes("text-sm")

                        update_samples_list()
                        tab_contents['update_samples_func'] = update_samples_list

            # Mixtures tab panel
            with ui.tab_panel(mix_tab.name):
                with ui.card().classes("w-full"):
                    mixture_id = ui.input(
                        label="Mixture ID",
                        placeholder="e.g., mix_1",
                    )
                    plex_type = ui.select(
                        options={p: p for p in ChannelBuilder.get_supported_plex_types()},
                        value="TMT6",
                        label="Plex Type",
                    )
                    channels_container = ui.column().classes("w-full mt-4")
                    # Store references to channel select widgets so we can read their values
                    channel_selects = {}

                    def update_channels_ui():
                        channel_selects.clear()
                        channels_container.clear()
                        try:
                            builder = ChannelBuilder(plex_type.value)
                            channels = builder.get_available_channels()

                            if not editor.manifest.samples:
                                with channels_container:
                                    ui.label("Add samples first to create mixtures")
                                return

                            with channels_container:
                                ui.label(f"Available channels ({len(channels)}):").classes(
                                    "font-semibold"
                                )
                                # Show channels with sample assignment
                                sample_ids = [s.id for s in editor.manifest.samples]
                                for idx, channel in enumerate(channels):
                                    sample_sel = ui.select(
                                        options={s: s for s in sample_ids} if sample_ids else {},
                                        label=f"{channel}",
                                        value=sample_ids[idx % len(sample_ids)] if sample_ids else None,
                                    ).classes("w-full")
                                    # Store reference to channel select so we can read it later
                                    channel_selects[channel] = sample_sel
                        except Exception as e:
                            with channels_container:
                                ui.label(f"Error: {e}")

                    plex_type.on_change(lambda: update_channels_ui())
                    update_channels_ui()

                    def add_mixture():
                        if not mixture_id.value:
                            ui.notify("Mixture ID is required")
                            return
                        try:
                            if not editor.manifest.samples:
                                ui.notify("Add samples before creating mixtures")
                                return

                            # Collect channel assignments from the UI by reading actual select values
                            channels_map = {}
                            for channel, sample_sel in channel_selects.items():
                                if sample_sel.value:  # Only include channels with a selected sample
                                    channels_map[channel] = sample_sel.value

                            if not channels_map:
                                ui.notify("Select at least one sample for a channel")
                                return

                            editor.manifest.add_mixture(
                                id=mixture_id.value,
                                channels=channels_map,
                            )
                            ui.notify(f"Mixture '{mixture_id.value}' added")
                            mixture_id.value = ""
                            refresh_entire_ui()
                        except Exception as e:
                            ui.notify(f"Error: {e}", type="negative")

                    ui.button(
                        "Add Mixture",
                        on_click=add_mixture,
                    ).classes("w-full mt-4")

                    # Display current mixtures
                    with ui.expansion(
                        text="Current Mixtures",
                        icon="list",
                    ).classes("w-full mt-4"):
                        mixtures_list = ui.column().classes("w-full")

                        def update_mixtures_list():
                            mixtures_list.clear()
                            for mixture in editor.manifest.mixtures:
                                with mixtures_list:
                                    ui.label(
                                        f"ID: {mixture.id} | "
                                        f"Channels: {len(mixture.channels)}"
                                    ).classes("text-sm")

                        update_mixtures_list()
                        tab_contents['update_mixtures_func'] = update_mixtures_list

            # Runs tab panel
            with ui.tab_panel(run_tab.name):
                with ui.card().classes("w-full"):
                    run_file = ui.input(
                        label="File Path",
                        placeholder="e.g., s3://bucket/file.raw",
                    )
                    run_mixture = ui.input(
                        label="Mixture ID (optional for LFQ)",
                        placeholder="e.g., mix_1",
                    )
                    run_fraction = ui.input(
                        label="Fraction",
                        type="number",
                        value="1",
                    )

                    def add_run():
                        if not run_file.value:
                            ui.notify("File path is required")
                            return
                        try:
                            editor.manifest.add_run(
                                file=run_file.value,
                                mixture=run_mixture.value or None,
                                fraction=int(run_fraction.value) if run_fraction.value else None,
                            )
                            ui.notify(f"Run '{run_file.value}' added")
                            run_file.value = ""
                            run_mixture.value = ""
                            run_fraction.value = "1"
                            refresh_entire_ui()
                        except Exception as e:
                            ui.notify(f"Error: {e}", type="negative")

                    ui.button(
                        "Add Run",
                        on_click=add_run,
                    ).classes("w-full mt-4")

                    # Display current runs
                    with ui.expansion(
                        text="Current Runs",
                        icon="list",
                    ).classes("w-full mt-4"):
                        runs_list = ui.column().classes("w-full")

                        def update_runs_list():
                            runs_list.clear()
                            for idx, run in enumerate(editor.manifest.runs):
                                with runs_list:
                                    ui.label(
                                        f"#{idx + 1}: {run.file} | "
                                        f"Mixture: {run.mixture or 'None'} | "
                                        f"Fraction: {run.fraction or 1}"
                                    ).classes("text-sm")

                        update_runs_list()
                        tab_contents['update_runs_func'] = update_runs_list

        # Validation panel
        with ui.card().classes("w-full mt-4 bg-blue-50"):
            ui.label("Validation Status").classes("text-lg font-semibold")
            validation_list = ui.column().classes("w-full")

            def update_validation():
                editor.refresh_validation()
                validation_list.clear()
                messages = editor.get_validation_messages()
                if not messages:
                    with validation_list:
                        ui.label("✓ Manifest is valid!").classes("text-green-600")
                else:
                    for msg in messages:
                        css_class = "text-red-600" if "[ERROR]" in msg else "text-yellow-600"
                        with validation_list:
                            ui.label(msg).classes(f"text-sm {css_class}")

            tab_contents['update_validation_func'] = update_validation

        # Manifest preview
        with ui.card().classes("w-full mt-4"):
            ui.label("YAML Preview").classes("text-lg font-semibold")
            yaml_preview = ui.code(
                language="yaml",
                content=editor.manifest.to_yaml(),
            ).classes("w-full")

            def update_preview():
                preview_text = editor.manifest.to_yaml()
                # Don't truncate, show full manifest
                yaml_preview.set_content(preview_text)

            tab_contents['update_preview_func'] = update_preview

        # Save/Load buttons
        with ui.row().classes("w-full gap-4 mt-4"):
            def save_manifest():
                try:
                    output_file = Path.home() / "quantms_manifest.yml"
                    editor.manifest.save_to_file(output_file)
                    ui.notify(f"Manifest saved to {output_file}")
                except Exception as e:
                    ui.notify(f"Error saving: {e}", type="negative")

            def load_manifest():
                try:
                    input_file = Path.home() / "quantms_manifest.yml"
                    if input_file.exists():
                        editor.manifest = ManifestState.load_from_file(input_file)
                        refresh_entire_ui()
                        ui.notify(f"Loaded from {input_file}")
                    else:
                        ui.notify(f"File not found: {input_file}", type="warning")
                except Exception as e:
                    ui.notify(f"Error loading: {e}", type="negative")

            ui.button(
                "Save Manifest",
                on_click=save_manifest,
                color="primary",
            ).classes("px-4")
            ui.button(
                "Load Manifest",
                on_click=load_manifest,
                color="info",
            ).classes("px-4")

        def refresh_entire_ui():
            """Refresh all UI elements using in-memory callbacks."""
            # Update samples
            if 'update_samples_func' in tab_contents:
                tab_contents['update_samples_func']()
            # Update mixtures
            if 'update_mixtures_func' in tab_contents:
                tab_contents['update_mixtures_func']()
            # Update runs
            if 'update_runs_func' in tab_contents:
                tab_contents['update_runs_func']()
            # Update validation
            if 'update_validation_func' in tab_contents:
                tab_contents['update_validation_func']()
            # Update preview
            if 'update_preview_func' in tab_contents:
                tab_contents['update_preview_func']()


def run_gui(port: int = 8080, host: str = "127.0.0.1") -> None:
    """Run the GUI application."""
    editor = ManifestEditor()

    @ui.page("/")
    def main_page():
        create_manifest_editor_ui(editor)

    ui.run(host=host, port=port, title="quantms Manifest Authoring")


if __name__ == "__main__":
    run_gui()
