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
from typing import Any, List, Callable, Optional, Dict

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from nicegui import ui
from manifest_core import ManifestState, ChannelBuilder, validate_manifest
from gui_wizard_state import WizardState, WizardStep
from spreadsheet_adapter import SpreadsheetAdapter, SpreadsheetRow
from file_picker import MsFilePickerDialog
from jspreadsheet_editor import JSpreadsheetEditor
from jspreadsheet_bridge import JSpreadsheetBridge
from ontology_provider import OntologyOptionProvider


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

        if current_idx >= len(steps) - 1:
            return False

        current_step = self.wizard.get_current_step()

        if current_step == WizardStep.RUNS:
            return len(self.wizard.runs) > 0

        if current_step == WizardStep.SAMPLES:
            return True

        if current_step == WizardStep.MIXTURES:
            return True

        if current_step == WizardStep.ASSIGNMENTS:
            return True

        if current_step == WizardStep.EXPERIMENT:
            return self.wizard._experiment_settings_saved

        if current_step == WizardStep.REVIEW:
            return False

        return True


class ManifestEditingWizard(WizardEditor):
    """Alias for WizardEditor for backward compatibility."""

    def get_current_step(self) -> WizardStep:
        """Get the current wizard step."""
        return self.wizard.get_current_step()


class SpreadsheetEditorFlushGroup:
    """Flush multiple spreadsheet editors as a single active editor."""

    def __init__(self, editors: List[Any]):
        self.editors = [editor for editor in editors if editor is not None]

    async def flush_pending_edits(self) -> None:
        """Flush pending edits from all registered editors."""
        import inspect

        for editor in self.editors:
            if not hasattr(editor, "flush_pending_edits"):
                continue
            flush_result = editor.flush_pending_edits()
            if inspect.iscoroutine(flush_result):
                await flush_result


def _normalize_modification_residues(value: Any) -> Optional[str]:
    """Convert provider residue payloads into the manifest's string form."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple, set)):
        return "".join(str(item) for item in value if item is not None)
    return str(value)


def _parse_optional_float(value: Any) -> Optional[float]:
    """Parse an optional numeric field from a UI input."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    return float(text)


def _format_optional_float(value: Any) -> str:
    """Format an optional numeric value for a text input."""
    if value is None:
        return ""
    return format(float(value), ".12g")


def _normalize_term_specificity(value: Any) -> str:
    """Normalize the UI term specificity value into the manifest representation."""
    text = str(value or "").strip().lower()
    return text or "none"


def _split_residue_codes(value: Any) -> List[str]:
    """Split residue input into comparable single-letter residue codes."""
    text = str(value or "").strip().upper()
    if not text:
        return []

    if text.isalpha():
        return list(text)

    for separator in (",", ";", "/"):
        text = text.replace(separator, " ")

    residue_codes: List[str] = []
    for token in text.split():
        if token.isalpha():
            residue_codes.extend(list(token))
    return residue_codes


def _build_selected_modification_summary(selected_option: Dict[str, Any]) -> str:
    """Build a compact UI summary for the currently selected UniMod entry."""
    label = selected_option.get("label") or selected_option.get("name") or "Selected UniMod entry"
    ontology_id = selected_option.get("ontology_id") or selected_option.get("value")
    summary = f"Selected: {label}"
    if ontology_id:
        summary = f"{summary} ({ontology_id})"

    detail_parts = []
    residues = _normalize_modification_residues(selected_option.get("residues"))
    if residues:
        detail_parts.append(f"residues {residues}")

    mass_shift = selected_option.get("mass_shift")
    if mass_shift is not None:
        detail_parts.append(f"delta {_format_optional_float(mass_shift)}")

    if detail_parts:
        summary = f"{summary} | {' | '.join(detail_parts)}"

    return summary


def _tag_customized_modification_name(name: Any) -> str:
    """Tag a modified ontology-backed name so the override is visible in the UI and spreadsheet."""
    normalized_name = str(name or "").strip()
    if not normalized_name:
        return "(custom)"
    if normalized_name.endswith(" (custom)"):
        return normalized_name
    return f"{normalized_name} (custom)"


def _convert_override_payload_to_custom(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Convert an overridden ontology-backed payload into a custom modification payload."""
    override_payload = dict(payload)
    override_payload["kind"] = "custom"
    override_payload["name"] = _tag_customized_modification_name(override_payload.get("name"))
    override_payload.pop("ontology_id", None)
    return override_payload


def _apply_selected_modification_defaults(
    selected_option: Dict[str, Any],
    residues_input: Any,
    mass_shift_input: Any,
    formula_input: Any,
    term_specificity_select: Any,
) -> None:
    """Populate authoring inputs from a selected UniMod entry when metadata is available."""
    residues = _normalize_modification_residues(selected_option.get("residues"))
    if residues:
        residues_input.value = residues
        residues_input.update()

    mass_shift = selected_option.get("mass_shift")
    if mass_shift is not None:
        mass_shift_input.value = _format_optional_float(mass_shift)
        mass_shift_input.update()

    formula = (selected_option.get("formula") or "").strip()
    if formula:
        formula_input.value = formula
        formula_input.update()

    term_specificity = selected_option.get("term_specificity")
    if term_specificity:
        term_specificity_select.value = term_specificity
        term_specificity_select.update()


def _validate_selected_modification_inputs(
    selected_option: Optional[Dict[str, Any]],
    residues: Any,
    term_specificity: Any,
) -> Optional[Dict[str, Any]]:
    """Validate residue and specificity inputs against the selected UniMod entry."""
    if not selected_option or selected_option.get("kind") != "ontology":
        return None

    label = selected_option.get("label") or selected_option.get("name") or "Selected UniMod entry"
    normalized_term_specificity = _normalize_term_specificity(term_specificity or selected_option.get("term_specificity"))

    allowed_term_specificities = list(selected_option.get("allowed_term_specificities") or [])
    if allowed_term_specificities and normalized_term_specificity not in allowed_term_specificities:
        supported = ", ".join(allowed_term_specificities)
        return {
            "message": (
                f"{label} does not support term specificity '{normalized_term_specificity}'. "
                f"Supported term specificities: {supported}."
            ),
            "can_override": False,
        }

    requested_residues = _split_residue_codes(residues)
    if not requested_residues:
        return None

    allowed_sites_by_term_specificity = dict(selected_option.get("allowed_sites_by_term_specificity") or {})
    allowed_residues = list(allowed_sites_by_term_specificity.get(normalized_term_specificity) or [])
    if not allowed_residues:
        allowed_residues = _split_residue_codes(selected_option.get("residues"))

    if not allowed_residues:
        return {
            "message": (
                f"{label} does not accept residue-specific values for term specificity "
                f"'{normalized_term_specificity}'."
            ),
            "can_override": True,
        }

    invalid_residues = [residue for residue in requested_residues if residue not in allowed_residues]
    if invalid_residues:
        return {
            "message": (
                f"{label} does not allow residues {', '.join(invalid_residues)} for term specificity "
                f"'{normalized_term_specificity}'. Allowed residues: {''.join(allowed_residues)}."
            ),
            "can_override": True,
        }

    return None


def _validate_modification_payload_requirements(payload: Optional[Dict[str, Any]]) -> Optional[str]:
    """Validate payload requirements that depend on the final modification kind."""
    if not payload:
        return None

    if payload.get("kind") == "custom" and payload.get("mass_shift") is None:
        return "Custom modifications require a mass shift."

    return None


def _build_modification_payload(
    selected_option: Optional[Dict[str, Any]],
    custom_name: Optional[str],
    mode: Optional[str],
    residues: Optional[str],
    term_specificity: Optional[str],
    mass_shift: Optional[str],
    formula: Optional[str],
    profile: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Build a modification payload from either a template or a custom entry."""
    custom_name = (custom_name or "").strip()
    payload: Dict[str, Any] = {}
    if selected_option:
        payload["kind"] = selected_option.get("kind") or "ontology"
        payload["name"] = selected_option.get("name") or selected_option.get("label")
        payload["mode"] = mode or selected_option.get("mode") or "fixed"
        payload["ontology_id"] = selected_option.get("ontology_id") or selected_option.get("value")
        payload["residues"] = residues or _normalize_modification_residues(selected_option.get("residues"))
        payload["term_specificity"] = term_specificity or selected_option.get("term_specificity")
        parsed_mass_shift = _parse_optional_float(mass_shift)
        if parsed_mass_shift is not None:
            payload["mass_shift"] = parsed_mass_shift
        elif selected_option.get("mass_shift") is not None:
            payload["mass_shift"] = selected_option.get("mass_shift")
        payload["formula"] = (formula or "").strip() or selected_option.get("formula")
    elif custom_name:
        payload["kind"] = "custom"
        payload["name"] = custom_name
        payload["mode"] = mode or "fixed"
        payload["residues"] = residues or None
        payload["term_specificity"] = term_specificity or None
        payload["mass_shift"] = _parse_optional_float(mass_shift)
        payload["formula"] = (formula or "").strip() or None
    else:
        return None

    if profile:
        payload["profile"] = profile

    return {key: value for key, value in payload.items() if value is not None}


def create_modifications_surface(wizard: WizardState, refresh_ui: Callable) -> Optional[JSpreadsheetEditor]:
    """Create the modification authoring surface that lives alongside Runs."""
    active_editor: Optional[JSpreadsheetEditor] = None
    modification_draft = wizard.get_pending_modification_draft()
    selected_modification_option: Optional[Dict[str, Any]] = modification_draft.get("selected_option")
    selected_modification_options: List[Dict[str, Any]] = []
    pending_override_payload: Optional[Dict[str, Any]] = None

    custom_modification_options = [
        modification
        for modification in wizard.modifications
        if modification.get("kind") == "custom"
    ]
    option_provider = OntologyOptionProvider()
    existing_profiles = wizard.get_modification_profiles()
    if not existing_profiles:
        wizard.register_modification_profile("default")
        wizard.set_active_modification_profile("default")
        existing_profiles = wizard.get_modification_profiles()
    keep_selected_option = object()

    def normalize_profile_name(profile: Any) -> Optional[str]:
        return wizard.normalize_modification_profile_name(profile)

    def resolve_profile_name(profile: Any) -> Optional[str]:
        return wizard.find_modification_profile_name(profile)

    with ui.card().classes("w-full mt-6"):
        ui.label("Modification profiles").classes("text-lg font-semibold")

        with ui.column().classes("w-full gap-4 mt-2"):
            # --- Tab-based profile strip (like Excel worksheet tabs) ---
            tabs_container: Any = None
            rename_row: Any = None
            rename_input: Any = None

            def recover_selected_modification_option() -> None:
                nonlocal selected_modification_option
                if selected_modification_option:
                    return
                recovered_selected_option = wizard.get_pending_modification_draft().get("selected_option")
                if recovered_selected_option:
                    selected_modification_option = recovered_selected_option

            _tab_buttons: Dict[str, Any] = {}

            def switch_to_profile(profile_name: str) -> None:
                recover_selected_modification_option()
                wizard.set_active_modification_profile(profile_name)
                persist_modification_draft()
                rebuild_tabs()

            def add_new_profile() -> None:
                existing = wizard.get_modification_profiles()
                new_name = f"profile-{len(existing) + 1}"
                wizard.register_modification_profile(new_name)
                wizard.set_active_modification_profile(new_name)
                persist_modification_draft()
                rebuild_tabs()

            def start_rename(profile_name: str) -> None:
                rename_input.value = profile_name
                rename_input.update()
                rename_row.set_visibility(True)

            def confirm_rename() -> None:
                new_name = normalize_profile_name(rename_input.value)
                if not new_name:
                    ui.notify("Profile name cannot be empty", type="warning")
                    return
                current = wizard.active_modification_profile
                if current and new_name != current:
                    resolved = resolve_profile_name(new_name)
                    if resolved and resolved != current:
                        ui.notify(f'Profile "{resolved}" already exists', type="warning")
                        return
                    wizard.rename_modification_profile(current, new_name)
                rename_row.set_visibility(False)
                persist_modification_draft()
                rebuild_tabs()

            def cancel_rename() -> None:
                rename_row.set_visibility(False)

            def rebuild_tabs() -> None:
                _tab_buttons.clear()
                tabs_container.clear()
                profiles = wizard.get_modification_profiles()
                active = wizard.active_modification_profile
                with tabs_container:
                    for profile in profiles:
                        is_active = profile == active
                        btn_props = "unelevated no-caps color=primary" if is_active else "flat no-caps"
                        btn = ui.button(profile, on_click=lambda p=profile: switch_to_profile(p))
                        btn.props(btn_props).classes("h-8 px-3")
                        _tab_buttons[profile] = btn
                        if is_active:
                            ui.button(
                                icon="edit", on_click=lambda p=profile: start_rename(p)
                            ).props("flat dense round no-caps size=xs").classes("h-6 w-6 min-w-0 ml-0")
                    ui.button("+", on_click=add_new_profile).props("flat no-caps dense").classes("h-8 w-8 min-w-0")

            with ui.row().classes("w-full items-center gap-1 border-b pb-1") as tabs_container:
                rebuild_tabs()

            ui.label(
                "Click a tab to switch profiles, use + to add another profile, and use the edit icon to rename the active profile."
            ).classes("text-xs text-gray-600")

            with ui.row().classes("w-full items-center gap-2") as rename_row:
                ui.label("Rename:").classes("text-sm text-gray-600")
                rename_input = ui.input(placeholder="New profile name").classes("grow")
                ui.button("OK", on_click=confirm_rename).props("flat dense no-caps").classes("h-8 px-2")
                ui.button("Cancel", on_click=cancel_rename).props("flat dense no-caps").classes("h-8 px-2")
            rename_row.set_visibility(False)

            ui.separator().classes("my-1")

            with ui.row().classes("w-full gap-4"):
                mode_select = ui.select(
                    options={"fixed": "fixed", "variable": "variable"},
                    value="fixed",
                    label="Mode",
                ).classes("grow basis-0")
                term_specificity_select = ui.select(
                    options={
                        "none": "none",
                        "n-term": "n-term",
                        "c-term": "c-term",
                        "protein-n-term": "protein-n-term",
                        "protein-c-term": "protein-c-term",
                    },
                    value="none",
                    label="Term Specificity",
                ).classes("grow basis-0")

            with ui.dialog() as unimod_dialog:
                with ui.card().classes("w-full max-w-2xl gap-4"):
                    ui.label("UniMod entry search").classes("text-lg font-semibold")
                    ui.label("Search UniMod-backed entries and apply the selected result to the draft.").classes(
                        "text-sm text-gray-600"
                    )
                    search_input = ui.input(
                        placeholder="Try UNIMOD:4, Carbamidomethyl, or an alternative title",
                    ).classes("w-full")
                    search_results_label = ui.label("Enter a UniMod accession or title to search").classes(
                        "text-sm text-gray-700"
                    )
                    results_select = ui.select(options={}, value=None, clearable=True).classes("w-full")

                    def run_unimod_search():
                        nonlocal selected_modification_options
                        query = (search_input.value or "").strip()
                        if not query:
                            ui.notify("Enter a UniMod accession or title to search", type="warning")
                            return

                        results = option_provider.get_modification_options(
                            custom_options=custom_modification_options,
                            query=query,
                        )
                        results_select.options = {
                            option.get("value"): option.get("label")
                            for option in results
                            if option.get("value")
                        }
                        selected_modification_options = results
                        results_select.value = results[0].get("value") if len(results) == 1 else None
                        results_select.update()
                        search_results_label.text = (
                            f"Found {len(results)} UniMod result(s)" if results else "No UniMod results found"
                        )
                        search_results_label.update()

                    def apply_unimod_selection():
                        nonlocal selected_modification_option
                        selected_value = results_select.value
                        selected_option = None
                        for option in selected_modification_options:
                            if option.get("value") == selected_value:
                                selected_option = option
                                break

                        if not selected_option:
                            ui.notify("Search UniMod and choose a result first", type="warning")
                            return

                        selected_option = option_provider.enrich_modification_option(selected_option)
                        selected_modification_option = selected_option
                        _apply_selected_modification_defaults(
                            selected_option,
                            residues_input,
                            mass_shift_input,
                            formula_input,
                            term_specificity_select,
                        )
                        selected_modification_label.text = _build_selected_modification_summary(selected_option)
                        selected_modification_label.update()
                        wizard.update_pending_modification_draft(
                            selected_option=selected_option,
                            profile=wizard.active_modification_profile,
                            mode=mode_select.value,
                            term_specificity=term_specificity_select.value,
                            custom_name=custom_name_input.value,
                            residues=residues_input.value,
                            mass_shift=mass_shift_input.value,
                            formula=formula_input.value,
                        )
                        update_custom_name_visibility()
                        # Auto-expand the modification details panel when a UniMod entry is selected
                        try:
                            modification_details_expansion.value = True
                            modification_details_expansion.update()
                        except Exception:
                            # expansion may not yet exist at definition time; ignore if unavailable
                            pass
                        unimod_dialog.close()

                    with ui.row().classes("w-full justify-end gap-2"):
                        ui.button("Search", on_click=run_unimod_search, icon="search").props(
                            "unelevated no-caps"
                        ).classes("h-11 min-w-32 px-5")
                        ui.button("Apply UniMod selection", on_click=apply_unimod_selection, icon="check").props(
                            "unelevated no-caps"
                        ).classes("h-11 min-w-56 px-5")

            ui.button("Find UniMod entry", on_click=unimod_dialog.open, icon="search").props(
                "unelevated no-caps"
            ).classes("h-11 min-w-32 px-5")

            selected_modification_label = ui.label("No UniMod entry selected").classes("text-xs text-gray-600")

            def clear_selected_modification():
                nonlocal selected_modification_option, selected_modification_options
                selected_modification_option = None
                selected_modification_options = []
                selected_modification_label.text = "No UniMod entry selected"
                selected_modification_label.update()
                persist_modification_draft(selected_option=None)
                update_custom_name_visibility()

            with ui.dialog() as override_dialog:
                with ui.card().classes("w-full max-w-lg gap-4"):
                    ui.label("Override UniMod residue validation").classes("text-lg font-semibold")
                    override_message_label = ui.label("").classes("text-sm text-gray-700")

                    with ui.row().classes("w-full justify-end gap-2"):
                        def cancel_override():
                            nonlocal pending_override_payload
                            pending_override_payload = None
                            override_dialog.close()

                        def confirm_override():
                            nonlocal pending_override_payload
                            if not pending_override_payload:
                                override_dialog.close()
                                return

                            finalize_modification_add(pending_override_payload)
                            pending_override_payload = None
                            override_dialog.close()

                        ui.button("Cancel", on_click=cancel_override).classes("px-4 py-0.5")
                        ui.button("Add anyway", on_click=confirm_override, color="warning").classes("px-4 py-0.5")

            with ui.expansion(text="Modification details", icon="tune", value=bool(selected_modification_option)).classes("w-full") as modification_details_expansion:
                with ui.column().classes("w-full p-4 bg-gray-50 rounded border border-gray-200"):
                    ui.label("Review or override the modification details before adding the entry.").classes(
                        "text-sm text-gray-600"
                    )

                    with ui.row().classes("w-full gap-4 items-start mt-3"):
                        with ui.column().classes("grow basis-0 gap-1") as custom_name_field:
                            ui.label("Modification Name").classes("text-sm text-gray-700")
                            custom_name_input = ui.input(
                                value=modification_draft.get("custom_name") or "",
                                placeholder="Enter a name for a custom modification",
                            ).classes("w-full")
                        with ui.column().classes("grow basis-0 gap-1"):
                            ui.label("Residues").classes("text-sm text-gray-700")
                            residues_input = ui.input(
                                value=modification_draft.get("residues") or "",
                                placeholder="e.g., C or STY",
                            ).classes("w-full")
                        with ui.column().classes("grow basis-0 gap-1"):
                            ui.label("Mass Shift").classes("text-sm text-gray-700")
                            mass_shift_input = ui.input(
                                value=modification_draft.get("mass_shift") or "",
                                placeholder="e.g., 57.021464",
                            ).classes("w-full")

                    with ui.row().classes("w-full gap-4 items-start mt-3"):
                        with ui.column().classes("grow basis-0 gap-1"):
                            ui.label("Formula (optional)").classes("text-sm text-gray-700")
                            formula_input = ui.input(
                                value=modification_draft.get("formula") or "",
                                placeholder="e.g., HO3P",
                            ).classes("w-full")

            def persist_modification_draft(selected_option=keep_selected_option):
                current_selected_option = (
                    selected_modification_option if selected_option is keep_selected_option else selected_option
                )
                wizard.update_pending_modification_draft(
                    selected_option=current_selected_option,
                    profile=wizard.active_modification_profile,
                    mode=mode_select.value,
                    term_specificity=term_specificity_select.value,
                    custom_name=custom_name_input.value,
                    residues=residues_input.value,
                    mass_shift=mass_shift_input.value,
                    formula=formula_input.value,
                )

            mode_select.value = modification_draft.get("mode") or mode_select.value
            term_specificity_select.value = modification_draft.get("term_specificity") or term_specificity_select.value

            if selected_modification_option:
                selected_modification_label.text = _build_selected_modification_summary(selected_modification_option)
                selected_modification_label.update()

            def update_custom_name_visibility(_=None):
                is_visible = not bool(selected_modification_option)
                custom_name_field.set_visibility(is_visible)
                custom_name_input.set_visibility(is_visible)

            update_custom_name_visibility()

            def finalize_modification_add(payload: Dict[str, Any]) -> None:
                wizard.add_modification(**payload)
                custom_name_input.value = ""
                residues_input.value = ""
                mass_shift_input.value = ""
                formula_input.value = ""
                wizard.clear_pending_modification_draft()
                clear_selected_modification()
                update_custom_name_visibility()
                refresh_ui()

            def add_modification():
                nonlocal pending_override_payload, selected_modification_option
                active_profile = wizard.active_modification_profile
                if not active_profile:
                    ui.notify("Choose or create a profile first", type="warning")
                    return

                if not selected_modification_option:
                    recover_selected_modification_option()
                    if selected_modification_option:
                        selected_modification_label.text = _build_selected_modification_summary(
                            selected_modification_option
                        )
                        selected_modification_label.update()
                        if not residues_input.value:
                            residues_input.value = _normalize_modification_residues(
                                selected_modification_option.get("residues")
                            )
                        if not mass_shift_input.value and selected_modification_option.get("mass_shift") is not None:
                            mass_shift_input.value = str(selected_modification_option.get("mass_shift"))
                        if not formula_input.value and selected_modification_option.get("formula"):
                            formula_input.value = str(selected_modification_option.get("formula"))
                        if not term_specificity_select.value and selected_modification_option.get("term_specificity"):
                            term_specificity_select.value = selected_modification_option.get("term_specificity")
                            term_specificity_select.update()
                        update_custom_name_visibility()

                persist_modification_draft()

                try:
                    payload = _build_modification_payload(
                        selected_option=selected_modification_option,
                        custom_name=custom_name_input.value,
                        mode=mode_select.value,
                        residues=residues_input.value,
                        term_specificity=term_specificity_select.value,
                        mass_shift=mass_shift_input.value,
                        formula=formula_input.value,
                        profile=active_profile,
                    )
                    if not payload:
                        ui.notify("Search UniMod and choose a modification, or enter a custom name", type="warning")
                        return

                    payload_requirement_issue = _validate_modification_payload_requirements(payload)
                    if payload_requirement_issue:
                        ui.notify(payload_requirement_issue, type="warning")
                        return

                    validation_issue = _validate_selected_modification_inputs(
                        selected_modification_option,
                        residues_input.value,
                        term_specificity_select.value,
                    )
                    if validation_issue:
                        if validation_issue.get("can_override"):
                            pending_override_payload = _convert_override_payload_to_custom(payload)
                            override_requirement_issue = _validate_modification_payload_requirements(
                                pending_override_payload
                            )
                            if override_requirement_issue:
                                pending_override_payload = None
                                ui.notify(override_requirement_issue, type="warning")
                                return

                            override_message_label.text = (
                                f"{validation_issue.get('message')} "
                                f"Add it anyway as {pending_override_payload['name']}?"
                            )
                            override_message_label.update()
                            override_dialog.open()
                            return

                        ui.notify(str(validation_issue.get("message") or "Invalid modification input"), type="warning")
                        return

                    finalize_modification_add(payload)
                except Exception as e:
                    ui.notify(f"Error adding modification: {e}", type="negative")

            with ui.row().classes("w-full justify-end mt-2"):
                add_modification_label = wizard.active_modification_profile or "default"
                ui.button(f"Add modification to {add_modification_label}", on_click=add_modification, icon="add").props(
                    "unelevated no-caps"
                ).classes("h-11 min-w-48 px-5")

        if wizard.modifications:
            ui.label(f"Modifications ({len(wizard.modifications)})").classes("text-md font-semibold mt-6")

            JSpreadsheetEditor.prepare_client_runtime()
            bridge = JSpreadsheetBridge(wizard, entity_type="modifications")
            editor = JSpreadsheetEditor(wizard, refresh_ui, bridge=bridge, worksheet_name="Modifications")
            editor.render()
            active_editor = editor

            ui.label(
                "• Click cells to edit modification fields\n"
                "• Right-click rows to delete\n"
                "* Mode, profile, and term specificity are available in the authoring flow"
            ).classes("text-xs text-gray-600 mt-4 p-2 bg-gray-50 rounded")
        else:
            ui.label("No modifications added yet. Use the form above to add one.").classes(
                "text-sm text-gray-500 italic mt-4"
            )

    return active_editor


def create_runs_step(wizard: WizardState, refresh_ui: Callable) -> Optional[Any]:
    """Create the RUNS step UI with embedded jspreadsheet-ce editor."""
    spreadsheet_editors: List[JSpreadsheetEditor] = []

    with ui.card().classes("w-full"):
        ui.label("Step 1: Add Raw/mzML Files").classes("text-lg font-semibold")
        ui.label("Edit files in the spreadsheet below. Add files via picker or manual path entry.").classes("text-sm text-gray-600")
        ui.label("(Sample and mixture assignment happens in the Assignments step)").classes("text-xs text-gray-500 italic")
        ui.label(
            "Files that share a basename after removing supported fraction markers can be suggested as groups. "
            "Use the button in the Groups pane to suggest groups for existing ungrouped files."
        ).classes("text-xs text-gray-600 mt-2 p-2 bg-blue-50 rounded")

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

        with ui.row().classes("w-full gap-4 items-start mt-6"):
            with ui.card().classes("w-full basis-0 grow"):
                if wizard.runs:
                    ui.label(f"Files Table ({len(wizard.runs)} file(s))").classes("text-md font-semibold")

                    bridge = JSpreadsheetBridge(wizard, entity_type="runs")
                    files_editor = JSpreadsheetEditor(wizard, refresh_ui, bridge=bridge, worksheet_name="Files")
                    files_editor.render()
                    spreadsheet_editors.append(files_editor)

                    ui.label(
                        "• Click cells to edit (file, fraction, instrument, group_id)\n"
                        "• Right-click rows to delete\n"
                        "• Drag-copy is supported when dragging cell borders\n"
                        "* File is required"
                    ).classes("text-xs text-gray-600 mt-4 p-2 bg-gray-50 rounded")
                else:
                    ui.label("No files added yet. Use 'Choose Local Files' to add MS data files.").classes(
                        "text-sm text-gray-500 italic"
                    )

            with ui.card().classes("w-full basis-0 grow"):
                async def suggest_groups_from_filenames() -> None:
                    def safe_notify(message: str, **kwargs: Any) -> None:
                        try:
                            ui.notify(message, **kwargs)
                        except Exception:
                            pass

                    if spreadsheet_editors:
                        await SpreadsheetEditorFlushGroup(spreadsheet_editors).flush_pending_edits()
                    seeded_count = wizard.seed_runs_from_filenames(force=True)
                    if seeded_count:
                        safe_notify(f"Suggested {seeded_count} run(s) into filename-based groups")
                        refresh_ui()
                    else:
                        safe_notify("No ungrouped files matched the filename grouping heuristic", type="info")

                ui.button(
                    "Suggest groups from filenames",
                    on_click=suggest_groups_from_filenames,
                    icon="auto_fix_high",
                ).classes("w-full mb-3")

                if wizard.groups:
                    ui.label(f"Groups Table ({len(wizard.groups)} group(s))").classes("text-md font-semibold")

                    bridge = JSpreadsheetBridge(wizard, entity_type="groups")
                    groups_editor = JSpreadsheetEditor(wizard, refresh_ui, bridge=bridge, worksheet_name="Groups")
                    groups_editor.render()
                    spreadsheet_editors.append(groups_editor)

                    ui.label(
                        "• Group ID is read-only in this phase\n"
                        "• Group name, kind, members, and description can be edited\n"
                        "• Group membership is shown in the Files table"
                    ).classes("text-xs text-gray-600 mt-4 p-2 bg-gray-50 rounded")
                else:
                    ui.label("No groups added yet. Group membership will appear here when groups exist.").classes(
                        "text-sm text-gray-500 italic"
                    )

    modifications_editor = create_modifications_surface(wizard, refresh_ui)
    if modifications_editor:
        spreadsheet_editors.append(modifications_editor)

    if len(spreadsheet_editors) > 1:
        return SpreadsheetEditorFlushGroup(spreadsheet_editors)
    if spreadsheet_editors:
        return spreadsheet_editors[0]
    return None


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
            plex_type.on_value_change(lambda e: update_channels_ui())
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
