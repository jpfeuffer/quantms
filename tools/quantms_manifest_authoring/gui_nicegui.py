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

Provides a locked, state-driven wizard for creating quantms YAML manifests
with guided step-by-step progression and validation concentrated in Review.
"""

import sys
from pathlib import Path
from typing import List, Callable, Optional, Dict

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from nicegui import ui
from manifest_core import ManifestState, ChannelBuilder, validate_manifest
from gui_wizard_state import WizardState, WizardStep
from spreadsheet_adapter import SpreadsheetAdapter, SpreadsheetRow
from file_picker import MsFilePickerDialog
from jspreadsheet_editor import JSpreadsheetEditor
from jspreadsheet_bridge import JSpreadsheetBridge


class WizardEditor:
    """Manages wizard state and conversion to manifest."""

    def __init__(self):
        """Initialize the wizard."""
        self.wizard = WizardState()
        self.validation_issues = []

    def refresh_validation(self) -> None:
        """Update validation feedback from manifest."""
        try:
            manifest = self.wizard.to_manifest_state()
            self.validation_issues = validate_manifest(manifest)
        except Exception as e:
            self.validation_issues = [
                {"level": "error", "message": str(e), "field": ""}
            ]

    def get_validation_messages(self) -> List[str]:
        """Get formatted validation messages."""
        messages = []
        for issue in self.validation_issues:
            level = issue.get("level", "").upper()
            msg = issue.get("message", "")
            field = issue.get("field", "")
            messages.append(f"[{level}] {msg}" + (f" ({field})" if field else ""))
        return messages

    def can_go_forward(self) -> bool:
        """Check if the user can advance to the next step."""
        current_idx = self.wizard.current_step_index
        steps = WizardStep.ordered_steps()

        # Cannot go forward from the last step
        if current_idx >= len(steps) - 1:
            return False

        current_step = self.wizard.get_current_step()

        # RUNS step requires at least one run
        if current_step == WizardStep.RUNS:
            return len(self.wizard.runs) > 0

        # SAMPLES step: always allow forward (can skip samples)
        if current_step == WizardStep.SAMPLES:
            return True

        # MIXTURES step: always allow forward (can skip mixtures for LFQ)
        if current_step == WizardStep.MIXTURES:
            return True

        # ASSIGNMENTS step: always allow forward
        if current_step == WizardStep.ASSIGNMENTS:
            return True

        # EXPERIMENT step: require saved settings
        if current_step == WizardStep.EXPERIMENT:
            return self.wizard._experiment_settings_saved

        # REVIEW step: cannot go forward
        if current_step == WizardStep.REVIEW:
            return False

        return True


# Alias for backward compatibility with tests
class ManifestEditingWizard(WizardEditor):
    """Alias for WizardEditor for backward compatibility."""

    def get_current_step(self) -> WizardStep:
        """Get the current wizard step."""
        return self.wizard.get_current_step()


def create_runs_step(wizard: WizardState, refresh_ui: Callable) -> Optional[JSpreadsheetEditor]:
    """Create the RUNS step UI with embedded jspreadsheet-ce editor."""
    active_editor: Optional[JSpreadsheetEditor] = None

    with ui.card().classes("w-full"):
        ui.label("Step 1: Add Raw/mzML Files").classes("text-lg font-semibold")
        ui.label("Edit runs in the spreadsheet below. Add files via picker or manual path entry.").classes("text-sm text-gray-600")
        ui.label("(Sample and mixture assignment happens in the Assignments step)").classes("text-xs text-gray-500 italic")

        # File picker button at the top
        async def pick_local_files():
            selected_files = await MsFilePickerDialog(multiple=True)
            if not selected_files:
                return
            added_files = 0
            for selected_file in selected_files:
                try:
                    wizard.add_run(file=selected_file)
                    added_files += 1
                except Exception as e:
                    ui.notify(f"Error adding {selected_file}: {e}", type="negative")
            if added_files:
                ui.notify(f"Added {added_files} file(s)")
                refresh_ui()

        ui.button(
            "Choose Local Files",
            on_click=pick_local_files,
            icon="folder_open",
        ).classes("w-full mt-4")

        ui.label("Supported formats: .raw, .mzML, .mzXML, .mgf, .ms2").classes(
            "text-xs text-gray-500 mt-2"
        )

        # Manual path entry section
        with ui.row().classes("w-full gap-2 items-end mt-4"):
            manual_path_input = ui.input(
                label="Or enter file path manually",
                placeholder="e.g., /path/to/file.raw or s3://bucket/file.raw",
            ).classes("flex-grow")

            def add_manual_path():
                path = manual_path_input.value.strip()
                if not path:
                    ui.notify("Please enter a file path", type="warning")
                    return
                try:
                    wizard.add_run(file=path)
                    ui.notify(f"Added: {path}")
                    manual_path_input.value = ""
                    refresh_ui()
                except Exception as e:
                    ui.notify(f"Error adding file: {e}", type="negative")

            ui.button(
                "Add",
                on_click=add_manual_path,
                icon="add",
            ).classes("px-4 py-0.5")

        JSpreadsheetEditor.prepare_client_runtime()

        # Embedded jspreadsheet-ce widget
        if wizard.runs:
            ui.label(f"Runs Table ({len(wizard.runs)} file(s))").classes("text-md font-semibold mt-6")

            # Create and render the spreadsheet editor
            editor = JSpreadsheetEditor(wizard, refresh_ui)
            # Register the editor as the active editor for pre-navigation flush
            wizard.set_active_editor(editor)
            editor.render()
            active_editor = editor

            # Footer with instructions
            ui.label(
                "• Click cells to edit (file, fraction, instrument)\n"
                "• Right-click rows to delete\n"
                "• Drag-copy is supported when dragging cell borders\n"
                "* File is required"
            ).classes("text-xs text-gray-600 mt-4 p-2 bg-gray-50 rounded")
        else:
            ui.label("No runs added yet. Use 'Choose Local Files' to add MS data files.").classes(
                "text-sm text-gray-500 italic mt-6"
            )

    return active_editor


def create_samples_step(wizard: WizardState, refresh_ui: Callable) -> Optional[JSpreadsheetEditor]:
    """Create the SAMPLES step UI with spreadsheet-native table editing."""
    active_editor: Optional[JSpreadsheetEditor] = None

    with ui.card().classes("w-full"):
        ui.label("Step 2: Define Biological Samples").classes("text-lg font-semibold")
        ui.label("Create sample definitions for LFQ quantification.").classes("text-sm text-gray-600")

        # Quick add form
        with ui.column().classes("w-full gap-4"):
            with ui.row().classes("w-full gap-2"):
                sample_id = ui.input(
                    label="Sample ID",
                    placeholder="e.g., treated_rep1",
                ).classes("flex-grow")
                organism = ui.input(
                    label="Organism (optional)",
                    placeholder="e.g., homo sapiens",
                ).classes("flex-grow")

            with ui.row().classes("w-full gap-2"):
                organism_part = ui.input(
                    label="Organism Part (optional)",
                    placeholder="e.g., liver",
                ).classes("flex-grow")
                condition = ui.input(
                    label="Condition (optional)",
                    placeholder="e.g., treated",
                ).classes("flex-grow")

            with ui.row().classes("w-full gap-2"):
                bio_rep = ui.input(
                    label="Biological Replicate (optional)",
                    placeholder="e.g., 1",
                ).classes("flex-grow")

                def add_sample():
                    if not sample_id.value:
                        ui.notify("Sample ID is required")
                        return
                    try:
                        wizard.add_sample(
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
                        bio_rep.value = ""
                        refresh_ui()
                    except Exception as e:
                        ui.notify(f"Error: {e}", type="negative")

                ui.button("Add Sample", on_click=add_sample, icon="add").classes("px-4")

        # Render existing samples as spreadsheet
        if wizard.samples:
            ui.label(f"Samples ({len(wizard.samples)})").classes("text-md font-semibold mt-6")
            
            JSpreadsheetEditor.prepare_client_runtime()
            
            # Create samples spreadsheet editor
            bridge = JSpreadsheetBridge(wizard, entity_type="samples")
            editor = JSpreadsheetEditor(wizard, refresh_ui, bridge=bridge, worksheet_name="Samples")
            wizard.set_active_editor(editor)
            editor.render()
            active_editor = editor
            
            # Footer with instructions
            ui.label(
                "• Click cells to edit (id, organism, organism_part, condition, biological_replicate, technical_replicate)\n"
                "• Right-click rows to delete\n"
                "* ID is required"
            ).classes("text-xs text-gray-600 mt-4 p-2 bg-gray-50 rounded")
        else:
            ui.label("No samples added yet. Use 'Add Sample' to add samples.").classes(
                "text-sm text-gray-500 italic mt-4"
            )

    return active_editor


def create_mixtures_step(wizard: WizardState, refresh_ui: Callable) -> Optional[JSpreadsheetEditor]:
    """Create the MIXTURES step UI with spreadsheet-native table editing."""
    active_editor: Optional[JSpreadsheetEditor] = None

    with ui.card().classes("w-full"):
        ui.label("Step 3: Create Multiplex Mixtures (optional)").classes("text-lg font-semibold")
        ui.label("For isobaric labeling (TMT, iTRAQ): define channel-to-sample mappings.").classes(
            "text-sm text-gray-600"
        )

        if not wizard.samples:
            ui.label("Add samples first to create mixtures").classes("text-sm text-amber-600 mt-4")
            return active_editor

        # Quick add form for new mixtures
        with ui.column().classes("w-full gap-4"):
            with ui.row().classes("w-full gap-2"):
                mixture_id = ui.input(
                    label="Mixture ID",
                    placeholder="e.g., mix_1",
                ).classes("flex-grow")

                plex_type = ui.select(
                    options={p: p for p in ChannelBuilder.get_supported_plex_types()},
                    value="TMT6",
                    label="Plex Type",
                ).classes("flex-grow")

            channels_container = ui.column().classes("w-full mt-2")
            channel_selects = {}

            def update_channels_ui():
                channel_selects.clear()
                channels_container.clear()
                try:
                    plex_value = plex_type.value or "TMT6"
                    builder = ChannelBuilder(plex_value)
                    channels = builder.get_available_channels()
                    sample_ids = [s["id"] for s in wizard.samples]

                    with channels_container:
                        ui.label(f"Assign {len(channels)} channels to samples:").classes("font-semibold text-sm")
                        with ui.row().classes("w-full gap-2 flex-wrap"):
                            for idx, channel in enumerate(channels):
                                sample_sel = ui.select(
                                    options={s: s for s in sample_ids},
                                    label=f"{channel}",
                                    value=sample_ids[idx % len(sample_ids)] if sample_ids else None,
                                ).classes("w-28")
                                channel_selects[channel] = sample_sel
                except Exception as e:
                    with channels_container:
                        ui.label(f"Error: {e}")

            # Update channels UI when plex type changes
            plex_type.on_change(lambda e: update_channels_ui())
            update_channels_ui()

            def add_mixture():
                if not mixture_id.value:
                    ui.notify("Mixture ID is required")
                    return
                try:
                    channels_map = {}
                    for channel, sample_sel in channel_selects.items():
                        if sample_sel.value:
                            channels_map[channel] = sample_sel.value

                    if not channels_map:
                        ui.notify("Select at least one channel")
                        return

                    wizard.add_mixture(id=mixture_id.value, channels=channels_map)
                    ui.notify(f"Mixture '{mixture_id.value}' added")
                    mixture_id.value = ""
                    refresh_ui()
                except Exception as e:
                    ui.notify(f"Error: {e}", type="negative")

            ui.button("Add Mixture", on_click=add_mixture, icon="add").classes("w-full mt-2")

        # Render existing mixtures as spreadsheet
        if wizard.mixtures:
            ui.label(f"Mixtures ({len(wizard.mixtures)})").classes("text-md font-semibold mt-6")
            
            JSpreadsheetEditor.prepare_client_runtime()
            
            # Create mixtures spreadsheet editor
            bridge = JSpreadsheetBridge(wizard, entity_type="mixtures")
            editor = JSpreadsheetEditor(wizard, refresh_ui, bridge=bridge, worksheet_name="Mixtures")
            wizard.set_active_editor(editor)
            editor.render()
            active_editor = editor
            
            # Footer with instructions
            ui.label(
                "• Click cells to edit (id and channel sample assignments)\n"
                "• Right-click rows to delete\n"
                "* ID is required"
            ).classes("text-xs text-gray-600 mt-4 p-2 bg-gray-50 rounded")
        else:
            ui.label("No mixtures added yet (optional for LFQ)").classes("text-sm text-gray-500 italic mt-4")

    return active_editor


def create_assignments_step(wizard: WizardState, refresh_ui: Callable) -> Optional[JSpreadsheetEditor]:
    """Create the ASSIGNMENTS step UI with spreadsheet-based sample/mixture linking."""
    active_editor: Optional[JSpreadsheetEditor] = None

    with ui.card().classes("w-full"):
        ui.label("Step 5: Assign Runs to Samples/Mixtures").classes("text-lg font-semibold")

        # Quantification-aware descriptive copy
        quant_method = wizard.experiment.get("quantification_method") if wizard.experiment else None
        is_multiplexed = quant_method in ("TMT", "iTRAQ", "SILAC")

        if is_multiplexed:
            ui.label(
                "Link each run to its corresponding mixture. "
                "Isobaric labeling methods require mixture definitions."
            ).classes("text-sm text-gray-600")
        else:
            ui.label(
                "Link each run directly to its corresponding sample. "
                "For LFQ and other non-multiplexed quantification methods."
            ).classes("text-sm text-gray-600")

        if not wizard.runs:
            ui.label("No runs to assign").classes("text-sm text-gray-500 italic mt-4")
            return active_editor

        # Check for required target entities
        if is_multiplexed and not wizard.mixtures:
            ui.label(
                "No mixtures defined yet. Create mixtures first for multiplexed quantification."
            ).classes("text-sm text-amber-600 mt-4")
            return active_editor

        if not is_multiplexed and not wizard.samples:
            ui.label(
                "No samples defined yet. Create samples first for sample-based quantification."
            ).classes("text-sm text-amber-600 mt-4")
            return active_editor

        # Create spreadsheet editor
        ui.label(f"Assignments ({len(wizard.runs)} run(s))").classes("text-md font-semibold mt-6")

        JSpreadsheetEditor.prepare_client_runtime()

        # Create assignments spreadsheet editor
        bridge = JSpreadsheetBridge(wizard, entity_type="assignments")
        editor = JSpreadsheetEditor(wizard, refresh_ui, bridge=bridge, worksheet_name="Assignments")
        wizard.set_active_editor(editor)
        editor.render()
        active_editor = editor

        # Footer with instructions
        ui.label(
            "• Click cells to edit (run file and sample/mixture assignment)\n"
            "* Run file and assignment are required"
        ).classes("text-xs text-gray-600 mt-4 p-2 bg-gray-50 rounded")

    return active_editor


def create_experiment_step(wizard: WizardState, refresh_ui: Callable) -> None:
    """Create the EXPERIMENT step UI."""
    with ui.card().classes("w-full"):
        ui.label("Step 4: Define Experiment Parameters").classes("text-lg font-semibold")
        ui.label("Set acquisition method, enzyme, dissociation method, and quantification approach.").classes(
            "text-sm text-gray-600"
        )

        with ui.column().classes("w-full gap-4"):
            acq_method = ui.select(
                options={"DDA": "DDA", "DIA": "DIA"},
                value="DDA",
                label="Acquisition Method",
            )
            enzyme = ui.input(
                label="Enzyme (required)",
                value="Trypsin",
                placeholder="e.g., Trypsin",
            )
            dissociation = ui.input(
                label="Dissociation Method (required)",
                value="HCD",
                placeholder="e.g., HCD, CID, ETD",
            )
            quant_method = ui.select(
                options={
                    "": "None",
                    "LFQ": "LFQ",
                    "TMT": "TMT",
                    "iTRAQ": "iTRAQ",
                    "SILAC": "SILAC",
                },
                label="Quantification Method",
            )

            def save_experiment():
                if not enzyme.value or not dissociation.value:
                    ui.notify("Enzyme and Dissociation Method are required")
                    return
                try:
                    wizard.set_experiment(
                        acquisition_method=acq_method.value or "DDA",
                        enzyme=enzyme.value,
                        dissociation_method=dissociation.value,
                        quantification_method=quant_method.value or None,
                    )
                    ui.notify("Experiment settings saved")
                    refresh_ui()
                except Exception as e:
                    ui.notify(f"Error: {e}", type="negative")

            ui.button("Save Experiment Settings", on_click=save_experiment, icon="save").classes(
                "w-full"
            )


def create_review_step(wizard: WizardState, refresh_ui: Callable) -> None:
    """Create the REVIEW step UI with validation and save."""
    with ui.card().classes("w-full"):
        ui.label("Step 6: Review & Save").classes("text-lg font-semibold")

        # Validation status
        with ui.expansion(
            text="Validation Status",
            icon="check_circle",
            value=True,
        ).classes("w-full"):
            validation_list = ui.column().classes("w-full")

            def update_validation():
                validation_list.clear()
                try:
                    manifest = wizard.to_manifest_state()
                    issues = validate_manifest(manifest)
                    if not issues:
                        with validation_list:
                            ui.label("✓ Manifest is valid!").classes("text-green-600 font-semibold")
                    else:
                        for issue in issues:
                            level = issue.get("level", "").upper()
                            msg = issue.get("message", "")
                            with validation_list:
                                css_class = "text-red-600" if level == "ERROR" else "text-yellow-600"
                                ui.label(f"[{level}] {msg}").classes(f"text-sm {css_class}")
                except Exception as e:
                    with validation_list:
                        ui.label(f"[ERROR] {str(e)}").classes("text-sm text-red-600")

            update_validation()

        # YAML preview
        with ui.expansion(text="YAML Preview", icon="code").classes("w-full"):
            try:
                manifest = wizard.to_manifest_state()
                yaml_content = manifest.to_yaml()
            except Exception as e:
                yaml_content = f"Error generating manifest:\n{str(e)}"

            yaml_preview = ui.code(language="yaml", content=yaml_content).classes("w-full")

        # Save button
        def save_manifest():
            try:
                manifest = wizard.to_manifest_state()
                output_file = Path.home() / "quantms_manifest.yml"
                manifest.save_to_file(output_file)
                ui.notify(f"✓ Manifest saved to {output_file}")
            except Exception as e:
                ui.notify(f"Error saving: {e}", type="negative")

        ui.button(
            "Save Manifest to File",
            on_click=save_manifest,
            icon="save",
            color="primary",
        ).classes("w-full mt-4")


def create_manifest_editor_ui(editor: WizardEditor) -> None:
    """Create the wizard-driven manifest editor UI."""
    with ui.column().classes("w-full"):
        # Header
        ui.label("quantms YAML Manifest Authoring").classes("text-3xl font-bold")
        ui.label("Guided wizard for creating quantms YAML manifests").classes(
            "text-sm text-gray-600"
        )

        # Progress container (will be refreshed by render_step)
        progress_container = ui.row().classes("w-full gap-2 mt-4 mb-4 items-center")

        # Step content containers are mounted once and reused to avoid
        # remounting heavy spreadsheet widgets on every navigation.
        step_content = ui.column().classes("w-full")
        steps = WizardStep.ordered_steps()
        step_names = [
            "Runs",
            "Samples",
            "Mixtures",
            "Experiment",
            "Assignments",
            "Review",
        ]
        step_renderers = {
            WizardStep.RUNS: create_runs_step,
            WizardStep.SAMPLES: create_samples_step,
            WizardStep.MIXTURES: create_mixtures_step,
            WizardStep.EXPERIMENT: create_experiment_step,
            WizardStep.ASSIGNMENTS: create_assignments_step,
            WizardStep.REVIEW: create_review_step,
        }
        step_containers: Dict[WizardStep, ui.column] = {}
        step_dirty = {step: True for step in steps}
        step_rendered = {step: False for step in steps}
        step_editors: Dict[WizardStep, Optional[JSpreadsheetEditor]] = {step: None for step in steps}

        with step_content:
            for step in steps:
                container = ui.column().classes("w-full")
                container.set_visibility(False)
                step_containers[step] = container

        def render_progress() -> None:
            """Refresh the read-only wizard progress indicator."""
            # Update progress indicator
            progress_container.clear()

            with progress_container:
                for idx, step in enumerate(steps):
                    is_current = idx == editor.wizard.current_step_index
                    is_past = idx < editor.wizard.current_step_index
                    css_class = (
                        "bg-primary text-white" if is_current
                        else "bg-green-500 text-white" if is_past
                        else "bg-gray-300 text-gray-700"
                    )
                    with ui.button(
                        f"{idx + 1}. {step_names[idx]}",
                        icon="check" if is_past else None,
                    ).classes(f"px-3 py-2 rounded font-semibold {css_class}"):
                        pass  # Buttons are read-only progress indicators
                    if idx < len(steps) - 1:
                        ui.label("→").classes("text-gray-400")

        def render_step_content(step: WizardStep, force: bool = False) -> None:
            """Render a step into its cached container when needed."""
            if step_rendered[step] and not (force or step_dirty[step]):
                return

            container = step_containers[step]
            container.clear()
            with container:
                step_editors[step] = step_renderers[step](editor.wizard, refresh_ui)

            step_rendered[step] = True
            step_dirty[step] = False

        def show_current_step(rerender_current_step: bool) -> None:
            """Show the active step and reuse any previously mounted content."""
            current_step = editor.wizard.get_current_step()
            render_step_content(current_step, force=rerender_current_step)

            for step, container in step_containers.items():
                container.set_visibility(step == current_step)

            editor.wizard.set_active_editor(step_editors.get(current_step))

        def render_step(rerender_current_step: bool = True) -> None:
            """Refresh progress and show the current step content."""
            render_progress()
            show_current_step(rerender_current_step)

        def update_nav_buttons():
            """Update button states based on current step and progression prerequisites."""
            current_idx = editor.wizard.current_step_index
            # Back button disabled on first step
            back_btn.enabled = current_idx > 0
            # Next button enabled only if can_go_forward (respects all prerequisites)
            next_btn.enabled = editor.can_go_forward()

        def refresh_ui(rerender_current_step: bool = True, invalidate_cached_steps: bool = True):
            """Refresh the UI while reusing cached step content whenever possible."""
            if invalidate_cached_steps:
                for step in steps:
                    step_dirty[step] = True

            render_step(rerender_current_step=rerender_current_step)
            update_nav_buttons()

        # Initial render
        render_step()

        # Navigation buttons
        with ui.row().classes("w-full gap-4 mt-6"):
            back_btn = ui.button("Back", icon="arrow_back").classes("px-6")
            next_btn = ui.button("Next", icon="arrow_forward").classes("px-6")

            async def go_back():
                try:
                    # Flush pending edits from active editor before navigating
                    active_editor = editor.wizard.get_active_editor()
                    invalidate_cached_steps = False
                    if active_editor is not None:
                        if hasattr(active_editor, 'flush_pending_edits'):
                            invalidate_cached_steps = True
                            flush_result = active_editor.flush_pending_edits()
                            # If flush_pending_edits is async, await it
                            import inspect
                            if inspect.iscoroutine(flush_result):
                                await flush_result

                    editor.wizard.previous_step()
                    refresh_ui(
                        rerender_current_step=False,
                        invalidate_cached_steps=invalidate_cached_steps,
                    )
                except ValueError as e:
                    ui.notify(str(e), type="warning")

            async def go_next():
                try:
                    # Flush pending edits from active editor before navigating
                    active_editor = editor.wizard.get_active_editor()
                    invalidate_cached_steps = False
                    if active_editor is not None:
                        if hasattr(active_editor, 'flush_pending_edits'):
                            invalidate_cached_steps = True
                            flush_result = active_editor.flush_pending_edits()
                            # If flush_pending_edits is async, await it
                            import inspect
                            if inspect.iscoroutine(flush_result):
                                await flush_result

                    editor.wizard.next_step()
                    refresh_ui(
                        rerender_current_step=False,
                        invalidate_cached_steps=invalidate_cached_steps,
                    )
                except ValueError as e:
                    ui.notify(str(e), type="warning")

            back_btn.on_click(go_back)
            next_btn.on_click(go_next)

        update_nav_buttons()


def run_gui(port: int = 8080, host: str = "127.0.0.1") -> None:
    """Run the GUI application."""
    editor = WizardEditor()

    @ui.page("/")
    def main_page():
        create_manifest_editor_ui(editor)

    ui.run(host=host, port=port, title="quantms Manifest Authoring", reload=False)


if __name__ in {"__main__", "__mp_main__"}:
    run_gui()
