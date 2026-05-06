#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pytest",
#   "nicegui",
#   "pyyaml",
# ]
# ///
"""Tests for the Runs-page modification authoring surface."""

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from gui_wizard_state import WizardState
from jspreadsheet_bridge import JSpreadsheetBridge
from gui_nicegui import create_runs_step


class MockElement:
    def __init__(self, text="", **kwargs):
        self.text = text
        self.label = kwargs.get("label", "")
        self.placeholder = kwargs.get("placeholder", "")
        self.value = kwargs.get("value")
        self.options = kwargs.get("options")
        self.icon = kwargs.get("icon", "")
        self.on_click = kwargs.get("on_click")
        self.on_change_callback = kwargs.get("on_change")
        self.kwargs = kwargs
        self.visible = kwargs.get("visible", True)
        self.update_calls = 0
        self.classes_text = ""
        self.props_text = ""

    def classes(self, *args, **kwargs):
        self.classes_text = " ".join(str(arg) for arg in args)
        return self

    def props(self, *args, **kwargs):
        self.props_text = " ".join(str(arg) for arg in args)
        return self

    def set_visibility(self, visible):
        self.visible = visible
        return self

    def on_change(self, callback):
        self.on_change_callback = callback
        return self

    def on_value_change(self, callback):
        self.on_change_callback = callback
        return self

    def update(self):
        self.update_calls += 1
        return self

    def set_autocomplete(self, autocomplete):
        self.kwargs["autocomplete"] = autocomplete
        return self

    def on(self, event_name, handler):
        """Register a generic event handler (e.g. dblclick)."""
        return self


class MockContainer(MockElement):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.labels = []
        self.buttons = []
        self.inputs = []
        self.selects = []
        self.separators = []
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def clear(self):
        self.labels = []
        self.buttons = []
        self.inputs = []
        self.selects = []
        self.separators = []
        self.rows = []
        return None

    def set_visibility(self, visible):
        self.visible = visible


class MockDialog(MockContainer):
    def __init__(self, ui, **kwargs):
        super().__init__(**kwargs)
        self.ui = ui
        self.inputs = []
        self.selects = []
        self.buttons = []
        self.labels = []
        self.rows = []
        self.open_calls = 0
        self.close_calls = 0

    def __enter__(self):
        self.ui._scope_stack.append(self)
        return self

    def __exit__(self, exc_type, exc, tb):
        self.ui._scope_stack.pop()
        return False

    def open(self):
        self.open_calls += 1
        self.visible = True
        return self

    def close(self):
        self.close_calls += 1
        self.visible = False
        return self


class MockUIContext:
    def __init__(self):
        self.labels = []
        self.buttons = []
        self.inputs = []
        self.selects = []
        self.separators = []
        self.rows = []
        self.dialogs = []
        self.notifications = []
        self._scope_stack = []

    def _record(self, element, collection_name):
        if self._scope_stack:
            getattr(self._scope_stack[-1], collection_name).append(element)
        else:
            getattr(self, collection_name).append(element)
        return element

    def notify(self, message, type=None):
        self.notifications.append({"message": message, "type": type})

    def label(self, text=""):
        element = MockElement(text=text)
        return self._record(element, "labels")

    def button(self, text="", on_click=None, icon="", color=None):
        element = MockElement(text=text, on_click=on_click, icon=icon, color=color)
        return self._record(element, "buttons")

    def input(self, value="", placeholder="", label="", type=None, **kwargs):
        element = MockElement(value=value, placeholder=placeholder, label=label, type=type, **kwargs)
        return self._record(element, "inputs")

    def select(self, options=None, value=None, label="", **kwargs):
        element = MockElement(options=options, value=value, label=label, **kwargs)
        return self._record(element, "selects")

    def separator(self, **kwargs):
        element = MockElement(**kwargs)
        return self._record(element, "separators")

    def dialog(self, **kwargs):
        dialog = MockDialog(self, **kwargs)
        self.dialogs.append(dialog)
        return dialog

    def row(self):
        element = MockContainer()
        return self._record(element, "rows")

    def column(self):
        return MockContainer()

    def card(self):
        return MockContainer()

    def expansion(self, *args, **kwargs):
        return MockContainer()

    def code(self, *args, **kwargs):
        return MockElement()


def _pick_element(elements, label):
    for element in elements:
        if element.label == label:
            return element

    if label == "UniMod results" and len(elements) == 1:
        return elements[0]

    placeholder_aliases = {
        "Modification Name": "Enter a name for a custom modification",
        "Residues": "e.g., C or STY",
        "Mass Shift": "e.g., 57.021464",
        "Formula (optional)": "e.g., HO3P",
        "Create Profile": "Create a new profile once, then add multiple modifications",
        "Search UniMod": "Try UNIMOD:4, Carbamidomethyl, or an alternative title",
        "Or enter file path manually": "e.g., /path/to/file.raw or s3://bucket/file.raw",
    }
    placeholder = placeholder_aliases.get(label)
    if placeholder:
        for element in elements:
            if element.placeholder == placeholder:
                return element

    raise AssertionError(f"Element with label '{label}' not found")


def test_runs_step_renders_modification_surface_and_adds_custom_modification():
    wizard = WizardState()
    wizard.register_modification_profile("default")
    wizard.set_active_modification_profile("default")
    refresh_calls = []

    def refresh_ui():
        refresh_calls.append(True)

    mock_ui = MockUIContext()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("gui_nicegui.ui", mock_ui)
        monkeypatch.setattr("gui_nicegui.JSpreadsheetEditor.prepare_client_runtime", lambda: None)
        create_runs_step(wizard, refresh_ui=refresh_ui)

    assert any("modification" in label.text.lower() for label in mock_ui.labels)

    add_button = next(button for button in mock_ui.buttons if button.text.startswith("Add modification to "))
    _pick_element(mock_ui.inputs, "Modification Name").value = "My Lab Label"
    _pick_element(mock_ui.inputs, "Residues").value = "M"
    _pick_element(mock_ui.inputs, "Mass Shift").value = "42.0"
    _pick_element(mock_ui.selects, "Mode").value = "fixed"

    add_button.on_click()

    assert len(wizard.modifications) == 1
    assert wizard.modifications[0]["kind"] == "custom"
    assert wizard.modifications[0]["name"] == "My Lab Label"
    assert wizard.modifications[0]["mode"] == "fixed"
    assert wizard.modifications[0]["residues"] == "M"
    assert wizard.modifications[0]["mass_shift"] == 42.0
    assert wizard.modifications[0]["profile"] == "default"
    assert refresh_calls


def test_runs_step_profile_area_exposes_existing_profiles_as_tabs():
    wizard = WizardState()
    wizard.register_modification_profile("default")
    wizard.set_active_modification_profile("default")
    mock_ui = MockUIContext()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("gui_nicegui.ui", mock_ui)
        monkeypatch.setattr("gui_nicegui.JSpreadsheetEditor.prepare_client_runtime", lambda *args, **kwargs: None)
        monkeypatch.setattr(
            "gui_nicegui.OntologyOptionProvider.get_modification_options",
            lambda self, custom_options=None, query=None: [],
        )
        create_runs_step(wizard, refresh_ui=lambda: None)

    # Profile should appear as a tab button (not an input)
    profile_tab_buttons = [b for b in mock_ui.buttons if b.text == "default"]
    assert len(profile_tab_buttons) >= 1
    # Active tab should have primary styling
    active_tab = profile_tab_buttons[0]
    assert "primary" in active_tab.props_text
    # "+" button for adding new profiles should exist
    plus_buttons = [b for b in mock_ui.buttons if b.text == "+"]
    assert len(plus_buttons) >= 1
    # No Profile input should exist
    profile_inputs = [i for i in mock_ui.inputs if i.label == "Profile"]
    assert len(profile_inputs) == 0


def test_runs_step_seeds_default_profile_and_shows_tab_help_text():
    wizard = WizardState()
    mock_ui = MockUIContext()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("gui_nicegui.ui", mock_ui)
        monkeypatch.setattr("gui_nicegui.JSpreadsheetEditor.prepare_client_runtime", lambda *args, **kwargs: None)
        monkeypatch.setattr(
            "gui_nicegui.OntologyOptionProvider.get_modification_options",
            lambda self, custom_options=None, query=None: [],
        )
        create_runs_step(wizard, refresh_ui=lambda: None)

    default_tab = next(button for button in mock_ui.buttons if button.text == "default")
    assert "primary" in default_tab.props_text
    assert wizard.active_modification_profile == "default"
    assert wizard.get_modification_profiles() == ["default"]
    assert any(
        "click a tab to switch profiles" in label.text.lower()
        for label in mock_ui.labels
    )


def test_runs_step_profile_plus_button_is_compact():
    wizard = WizardState()
    wizard.register_modification_profile("default")
    wizard.set_active_modification_profile("default")
    mock_ui = MockUIContext()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("gui_nicegui.ui", mock_ui)
        monkeypatch.setattr("gui_nicegui.JSpreadsheetEditor.prepare_client_runtime", lambda: None)
        monkeypatch.setattr(
            "gui_nicegui.OntologyOptionProvider.get_modification_options",
            lambda self, custom_options=None, query=None: [],
        )
        create_runs_step(wizard, refresh_ui=lambda: None)

    plus_button = next(b for b in mock_ui.buttons if b.text == "+")
    assert "h-8" in plus_button.classes_text
    assert "dense" in plus_button.props_text


def test_runs_step_profile_rename_updates_related_state():
    wizard = WizardState()
    wizard.register_modification_profile("default")
    wizard.set_active_modification_profile("default")
    wizard.update_pending_modification_draft(profile="default")
    wizard.add_modification(mode="fixed", kind="custom", name="Label", residues="M", profile="default")
    wizard.add_run(file="run.raw", modification_profile="default")
    mock_ui = MockUIContext()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("gui_nicegui.ui", mock_ui)
        monkeypatch.setattr("gui_nicegui.JSpreadsheetEditor.prepare_client_runtime", lambda *args, **kwargs: None)
        monkeypatch.setattr(
            "gui_nicegui.OntologyOptionProvider.get_modification_options",
            lambda self, custom_options=None, query=None: [],
        )
        create_runs_step(wizard, refresh_ui=lambda: None)

    # Simulate rename: the rename_input gets the new name and OK is clicked
    # Find the rename input (placeholder "New profile name")
    rename_input = next(i for i in mock_ui.inputs if i.placeholder == "New profile name")
    rename_input.value = "Renamed Profile"

    # Find the OK button for rename confirmation
    ok_button = next(b for b in mock_ui.buttons if b.text == "OK")
    ok_button.on_click()

    assert wizard.active_modification_profile == "Renamed Profile"
    assert wizard.get_modification_profiles() == ["Renamed Profile"]
    assert wizard.modifications[0]["profile"] == "Renamed Profile"
    assert wizard.runs[0]["modification_profile"] == "Renamed Profile"
    assert wizard.get_pending_modification_draft()["profile"] == "Renamed Profile"


def test_runs_step_profile_area_can_create_another_profile_via_plus_button():
    wizard = WizardState()
    wizard.register_modification_profile("default")
    wizard.set_active_modification_profile("default")
    mock_ui = MockUIContext()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("gui_nicegui.ui", mock_ui)
        monkeypatch.setattr("gui_nicegui.JSpreadsheetEditor.prepare_client_runtime", lambda: None)
        monkeypatch.setattr(
            "gui_nicegui.OntologyOptionProvider.get_modification_options",
            lambda self, custom_options=None, query=None: [],
        )
        create_runs_step(wizard, refresh_ui=lambda: None)

    # Click "+" to add a new profile
    plus_button = next(b for b in mock_ui.buttons if b.text == "+")
    plus_button.on_click()

    assert wizard.active_modification_profile == "profile-2"
    assert wizard.get_modification_profiles() == ["default", "profile-2"]

    # Click "+" again for a third
    plus_button.on_click()

    assert wizard.active_modification_profile == "profile-3"
    assert wizard.get_modification_profiles() == ["default", "profile-2", "profile-3"]


def test_runs_step_custom_modification_requires_mass_shift():
    wizard = WizardState()
    wizard.register_modification_profile("default")
    wizard.set_active_modification_profile("default")
    mock_ui = MockUIContext()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("gui_nicegui.ui", mock_ui)
        monkeypatch.setattr("gui_nicegui.JSpreadsheetEditor.prepare_client_runtime", lambda: None)
        monkeypatch.setattr(
            "gui_nicegui.OntologyOptionProvider.get_modification_options",
            lambda self, custom_options=None, query=None: [],
        )
        create_runs_step(wizard, refresh_ui=lambda: None)

        _pick_element(mock_ui.inputs, "Modification Name").value = "My Lab Label"
        _pick_element(mock_ui.inputs, "Residues").value = "M"
        _pick_element(mock_ui.selects, "Mode").value = "fixed"

        next(button for button in mock_ui.buttons if button.text.startswith("Add modification to ")).on_click()

    assert wizard.modifications == []
    assert mock_ui.notifications[-1] == {
        "message": "Custom modifications require a mass shift.",
        "type": "warning",
    }


def test_runs_step_uses_dialog_for_unimod_search_and_term_specificity():
    wizard = WizardState()
    wizard.register_modification_profile("default")
    wizard.set_active_modification_profile("default")
    refresh_calls = []

    def refresh_ui():
        refresh_calls.append(True)

    mock_ui = MockUIContext()

    provider_options = [
        {
            "label": "Carbamidomethyl",
            "value": "UNIMOD:4",
            "kind": "ontology",
            "ontology_id": "UNIMOD:4",
            "mode": "fixed",
            "residues": "C",
            "term_specificity": "none",
            "mass_shift": 57.021464,
        }
    ]

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("gui_nicegui.ui", mock_ui)
        monkeypatch.setattr("gui_nicegui.JSpreadsheetEditor.prepare_client_runtime", lambda: None)
        monkeypatch.setattr(
            "gui_nicegui.OntologyOptionProvider.get_modification_options",
            lambda self, custom_options=None, query=None: provider_options
            if query and query.lower() in {"unimod:4", "carbamidomethyl", "acetyl"}
            else [],
        )
        create_runs_step(wizard, refresh_ui=refresh_ui)

        assert "UniMod modification" not in {input_.label for input_ in mock_ui.inputs}
        assert "UniMod entry" not in {select.label for select in mock_ui.selects}
        assert "Find UniMod entry" in {button.text for button in mock_ui.buttons}
        custom_name_input = _pick_element(mock_ui.inputs, "Modification Name")
        assert custom_name_input.visible is True

        find_button = next(button for button in mock_ui.buttons if button.text == "Find UniMod entry")
        find_button.on_click()

        assert mock_ui.dialogs
        unimod_dialog = mock_ui.dialogs[0]
        assert unimod_dialog.visible is True

        search_input = _pick_element(unimod_dialog.inputs, "Search UniMod")
        search_input.value = "carbamidomethyl"
        search_button = next(button for button in unimod_dialog.buttons if button.text == "Search")
        search_button.on_click()

        results_select = _pick_element(unimod_dialog.selects, "UniMod results")
        assert results_select.options == {"UNIMOD:4": "Carbamidomethyl"}
        assert results_select.value == "UNIMOD:4"

        apply_button = next(button for button in unimod_dialog.buttons if button.text == "Apply UniMod selection")
        apply_button.on_click()

        assert custom_name_input.visible is False
        _pick_element(mock_ui.selects, "Term Specificity").value = "none"
        _pick_element(mock_ui.selects, "Mode").value = "fixed"

        add_button = next(button for button in mock_ui.buttons if button.text.startswith("Add modification to "))
        add_button.on_click()

    assert len(wizard.modifications) == 1
    assert wizard.modifications[0]["kind"] == "ontology"
    assert wizard.modifications[0]["ontology_id"] == "UNIMOD:4"
    assert wizard.modifications[0]["name"] == "Carbamidomethyl"
    assert wizard.modifications[0]["residues"] == "C"
    assert wizard.modifications[0]["term_specificity"] == "none"
    assert wizard.modifications[0]["profile"] == "default"
    assert refresh_calls


def test_runs_step_applies_selected_unimod_defaults_to_inputs():
    wizard = WizardState()
    wizard.register_modification_profile("default")
    wizard.set_active_modification_profile("default")
    mock_ui = MockUIContext()

    provider_options = [
        {
            "label": "Carbamidomethyl",
            "value": "UNIMOD:4",
            "kind": "ontology",
            "ontology_id": "UNIMOD:4",
            "name": "Carbamidomethyl",
            "iri": "http://purl.obolibrary.org/obo/UNIMOD_4",
        }
    ]

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("gui_nicegui.ui", mock_ui)
        monkeypatch.setattr("gui_nicegui.JSpreadsheetEditor.prepare_client_runtime", lambda: None)
        monkeypatch.setattr(
            "gui_nicegui.OntologyOptionProvider.get_modification_options",
            lambda self, custom_options=None, query=None: provider_options if query == "carbamidomethyl" else [],
        )
        monkeypatch.setattr(
            "gui_nicegui.OntologyOptionProvider.enrich_modification_option",
            lambda self, option: {
                **option,
                "mass_shift": 57.021464,
                "residues": "C",
                "term_specificity": "none",
                "formula": "H(3) C(2) N O",
                "allowed_term_specificities": ["none"],
                "allowed_sites_by_term_specificity": {"none": ["C"]},
            },
        )
        create_runs_step(wizard, refresh_ui=lambda: None)

        find_button = next(button for button in mock_ui.buttons if button.text == "Find UniMod entry")
        find_button.on_click()

        unimod_dialog = mock_ui.dialogs[0]
        _pick_element(unimod_dialog.inputs, "Search UniMod").value = "carbamidomethyl"
        next(button for button in unimod_dialog.buttons if button.text == "Search").on_click()
        next(button for button in unimod_dialog.buttons if button.text == "Apply UniMod selection").on_click()

    assert _pick_element(mock_ui.inputs, "Residues").value == "C"
    assert _pick_element(mock_ui.inputs, "Mass Shift").value == "57.021464"
    assert _pick_element(mock_ui.inputs, "Formula (optional)").value == "H(3) C(2) N O"
    assert _pick_element(mock_ui.selects, "Term Specificity").value == "none"


def test_runs_step_allows_invalid_residue_override_with_custom_tag():
    wizard = WizardState()
    wizard.register_modification_profile("default")
    wizard.set_active_modification_profile("default")
    mock_ui = MockUIContext()

    provider_options = [
        {
            "label": "Carbamidomethyl",
            "value": "UNIMOD:4",
            "kind": "ontology",
            "ontology_id": "UNIMOD:4",
            "name": "Carbamidomethyl",
            "iri": "http://purl.obolibrary.org/obo/UNIMOD_4",
        }
    ]

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("gui_nicegui.ui", mock_ui)
        monkeypatch.setattr("gui_nicegui.JSpreadsheetEditor.prepare_client_runtime", lambda: None)
        monkeypatch.setattr(
            "gui_nicegui.OntologyOptionProvider.get_modification_options",
            lambda self, custom_options=None, query=None: provider_options if query == "carbamidomethyl" else [],
        )
        monkeypatch.setattr(
            "gui_nicegui.OntologyOptionProvider.enrich_modification_option",
            lambda self, option: {
                **option,
                "mass_shift": 57.021464,
                "residues": "C",
                "term_specificity": "none",
                "allowed_term_specificities": ["none"],
                "allowed_sites_by_term_specificity": {"none": ["C"]},
            },
        )
        create_runs_step(wizard, refresh_ui=lambda: None)

        next(button for button in mock_ui.buttons if button.text == "Find UniMod entry").on_click()
        unimod_dialog = mock_ui.dialogs[0]
        _pick_element(unimod_dialog.inputs, "Search UniMod").value = "carbamidomethyl"
        next(button for button in unimod_dialog.buttons if button.text == "Search").on_click()
        next(button for button in unimod_dialog.buttons if button.text == "Apply UniMod selection").on_click()

        _pick_element(mock_ui.inputs, "Residues").value = "M"

        next(button for button in mock_ui.buttons if button.text.startswith("Add modification to ")).on_click()

        assert wizard.modifications == []

        override_dialog = next(
            dialog
            for dialog in mock_ui.dialogs
            if any(label.text == "Override UniMod residue validation" for label in dialog.labels)
        )
        assert override_dialog.visible is True
        assert any(
            "Carbamidomethyl does not allow residues M for term specificity 'none'. Allowed residues: C." in label.text
            for label in override_dialog.labels
        )

        next(button for button in override_dialog.buttons if button.text == "Add anyway").on_click()

    assert len(wizard.modifications) == 1
    assert wizard.modifications[0]["kind"] == "custom"
    assert "ontology_id" not in wizard.modifications[0]
    assert wizard.modifications[0]["residues"] == "M"
    assert wizard.modifications[0]["name"] == "Carbamidomethyl (custom)"


def test_runs_step_keeps_last_uni_mod_selection_after_search_box_changes_before_add():
    wizard = WizardState()
    wizard.register_modification_profile("default")
    wizard.set_active_modification_profile("default")
    mock_ui = MockUIContext()

    search_results = [
        {
            "label": "Carbamidomethyl",
            "value": "UNIMOD:4",
            "kind": "ontology",
            "ontology_id": "UNIMOD:4",
            "mode": "fixed",
            "residues": "C",
            "term_specificity": "none",
            "mass_shift": 57.021464,
        }
    ]

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("gui_nicegui.ui", mock_ui)
        monkeypatch.setattr("gui_nicegui.JSpreadsheetEditor.prepare_client_runtime", lambda: None)
        monkeypatch.setattr(
            "gui_nicegui.OntologyOptionProvider.get_modification_options",
            lambda self, custom_options=None, query=None: search_results if query == "carbamidomethyl" else [],
        )
        create_runs_step(wizard, refresh_ui=lambda: None)

        find_button = next(button for button in mock_ui.buttons if button.text == "Find UniMod entry")
        find_button.on_click()

        unimod_dialog = mock_ui.dialogs[0]
        search_input = _pick_element(unimod_dialog.inputs, "Search UniMod")
        ontology_select = _pick_element(unimod_dialog.selects, "UniMod results")
        mode_select = _pick_element(mock_ui.selects, "Mode")

        search_input.value = "carbamidomethyl"
        search_button = next(button for button in unimod_dialog.buttons if button.text == "Search")
        search_button.on_click()
        apply_button = next(button for button in unimod_dialog.buttons if button.text == "Apply UniMod selection")
        apply_button.on_click()

        search_input.value = ""
        mode_select.value = "fixed"

        add_button = next(button for button in mock_ui.buttons if button.text.startswith("Add modification to "))
        add_button.on_click()

    assert len(wizard.modifications) == 1
    assert wizard.modifications[0]["ontology_id"] == "UNIMOD:4"
    assert wizard.modifications[0]["name"] == "Carbamidomethyl"


def test_runs_step_profile_first_selection_persists_across_rerender_before_modifications():
    wizard = WizardState()
    wizard.register_modification_profile("default")
    wizard.set_active_modification_profile("default")

    first_ui = MockUIContext()
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("gui_nicegui.ui", first_ui)
        monkeypatch.setattr("gui_nicegui.JSpreadsheetEditor.prepare_client_runtime", lambda: None)
        monkeypatch.setattr(
            "gui_nicegui.OntologyOptionProvider.get_modification_options",
            lambda self, custom_options=None, query=None: [],
        )
        create_runs_step(wizard, refresh_ui=lambda: None)

    # Active profile tab should be rendered with primary styling
    default_tab = next(b for b in first_ui.buttons if b.text == "default")
    assert "primary" in default_tab.props_text

    # Re-render the step and verify active profile persists
    second_ui = MockUIContext()
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("gui_nicegui.ui", second_ui)
        monkeypatch.setattr("gui_nicegui.JSpreadsheetEditor.prepare_client_runtime", lambda: None)
        monkeypatch.setattr(
            "gui_nicegui.OntologyOptionProvider.get_modification_options",
            lambda self, custom_options=None, query=None: [],
        )
        create_runs_step(wizard, refresh_ui=lambda: None)

    default_tab_2 = next(b for b in second_ui.buttons if b.text == "default")
    assert "primary" in default_tab_2.props_text
    assert wizard.active_modification_profile == "default"


def test_runs_step_preserves_selected_ontology_entry_across_rerender_after_profile_creation():
    import gui_nicegui

    fresh_gui = importlib.reload(gui_nicegui)
    wizard = WizardState()

    provider_options = [
        {
            "label": "Phospho",
            "value": "UNIMOD:21",
            "kind": "ontology",
            "ontology_id": "UNIMOD:21",
            "name": "Phospho",
            "iri": "http://purl.obolibrary.org/obo/UNIMOD_21",
        }
    ]

    first_ui = MockUIContext()
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(fresh_gui, "ui", first_ui)
        monkeypatch.setattr(fresh_gui.JSpreadsheetEditor, "prepare_client_runtime", lambda: None)
        monkeypatch.setattr(
            fresh_gui.OntologyOptionProvider,
            "get_modification_options",
            lambda self, custom_options=None, query=None: provider_options if query == "21" else [],
        )
        monkeypatch.setattr(
            fresh_gui.OntologyOptionProvider,
            "enrich_modification_option",
            lambda self, option: {
                **option,
                "mass_shift": 79.966331,
                "residues": "STY",
                "term_specificity": "none",
                "formula": "H O(3) P",
                "allowed_term_specificities": ["none"],
                "allowed_sites_by_term_specificity": {"none": ["S", "T", "Y"]},
            },
        )
        fresh_gui.create_runs_step(wizard, refresh_ui=lambda: None)

        next(button for button in first_ui.buttons if button.text == "Find UniMod entry").on_click()
        unimod_dialog = first_ui.dialogs[0]
        _pick_element(unimod_dialog.inputs, "Search UniMod").value = "21"
        next(button for button in unimod_dialog.buttons if button.text == "Search").on_click()
        next(button for button in unimod_dialog.buttons if button.text == "Apply UniMod selection").on_click()

        # Create a new profile via wizard state (tabs handle the UI)
        wizard.register_modification_profile("newprof")
        wizard.set_active_modification_profile("newprof")
        wizard.update_pending_modification_draft(profile="newprof")

    second_ui = MockUIContext()
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(fresh_gui, "ui", second_ui)
        monkeypatch.setattr(fresh_gui.JSpreadsheetEditor, "prepare_client_runtime", lambda: None)
        monkeypatch.setattr(
            fresh_gui.OntologyOptionProvider,
            "get_modification_options",
            lambda self, custom_options=None, query=None: provider_options if query == "21" else [],
        )
        monkeypatch.setattr(
            fresh_gui.OntologyOptionProvider,
            "enrich_modification_option",
            lambda self, option: {
                **option,
                "mass_shift": 79.966331,
                "residues": "STY",
                "term_specificity": "none",
                "formula": "H O(3) P",
                "allowed_term_specificities": ["none"],
                "allowed_sites_by_term_specificity": {"none": ["S", "T", "Y"]},
            },
        )
        fresh_gui.create_runs_step(wizard, refresh_ui=lambda: None)

    draft = wizard.get_pending_modification_draft()
    assert wizard.active_modification_profile == "newprof"
    assert draft["profile"] == "newprof"
    assert draft["selected_option"]["ontology_id"] == "UNIMOD:21"
    assert draft["residues"] == "STY"
    assert draft["mass_shift"] == "79.966331"


def test_runs_step_custom_modification_preserves_term_specificity():
    wizard = WizardState()
    wizard.register_modification_profile("default")
    wizard.set_active_modification_profile("default")
    mock_ui = MockUIContext()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("gui_nicegui.ui", mock_ui)
        monkeypatch.setattr("gui_nicegui.JSpreadsheetEditor.prepare_client_runtime", lambda: None)
        monkeypatch.setattr(
            "gui_nicegui.OntologyOptionProvider.get_modification_options",
            lambda self, custom_options=None, query=None: [],
        )
        create_runs_step(wizard, refresh_ui=lambda: None)

    _pick_element(mock_ui.inputs, "Modification Name").value = "My Lab Label"
    _pick_element(mock_ui.inputs, "Residues").value = "M"
    _pick_element(mock_ui.inputs, "Mass Shift").value = "42.0"
    _pick_element(mock_ui.selects, "Mode").value = "fixed"
    _pick_element(mock_ui.selects, "Term Specificity").value = "protein-n-term"

    add_button = next(button for button in mock_ui.buttons if button.text.startswith("Add modification to "))
    add_button.on_click()

    assert len(wizard.modifications) == 1
    assert wizard.modifications[0]["term_specificity"] == "protein-n-term"


def test_runs_step_custom_name_only_appears_for_custom_modifications():
    wizard = WizardState()
    wizard.register_modification_profile("default")
    wizard.set_active_modification_profile("default")
    mock_ui = MockUIContext()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("gui_nicegui.ui", mock_ui)
        monkeypatch.setattr("gui_nicegui.JSpreadsheetEditor.prepare_client_runtime", lambda: None)
        monkeypatch.setattr(
            "gui_nicegui.OntologyOptionProvider.get_modification_options",
            lambda self, custom_options=None, query=None: [],
        )
        create_runs_step(wizard, refresh_ui=lambda: None)

    custom_name_input = _pick_element(mock_ui.inputs, "Modification Name")

    assert custom_name_input.visible is True

    find_button = next(button for button in mock_ui.buttons if button.text == "Find UniMod entry")
    find_button.on_click()

    unimod_dialog = mock_ui.dialogs[0]
    search_input = _pick_element(unimod_dialog.inputs, "Search UniMod")
    search_input.value = "carbamidomethyl"
    search_button = next(button for button in unimod_dialog.buttons if button.text == "Search")
    search_button.on_click()
    results_select = _pick_element(unimod_dialog.selects, "UniMod results")
    results_select.value = "UNIMOD:4"
    apply_button = next(button for button in unimod_dialog.buttons if button.text == "Apply UniMod selection")
    apply_button.on_click()

    assert custom_name_input.visible is False


def test_runs_step_invalid_mass_shift_notifies_instead_of_raising():
    wizard = WizardState()
    wizard.register_modification_profile("default")
    wizard.set_active_modification_profile("default")
    mock_ui = MockUIContext()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("gui_nicegui.ui", mock_ui)
        monkeypatch.setattr("gui_nicegui.JSpreadsheetEditor.prepare_client_runtime", lambda: None)
        monkeypatch.setattr(
            "gui_nicegui.OntologyOptionProvider.get_modification_options",
            lambda self, custom_options=None, query=None: [],
        )
        create_runs_step(wizard, refresh_ui=lambda: None)

        _pick_element(mock_ui.inputs, "Modification Name").value = "My Lab Label"
        _pick_element(mock_ui.inputs, "Mass Shift").value = "not-a-number"
        _pick_element(mock_ui.selects, "Mode").value = "fixed"

        add_button = next(button for button in mock_ui.buttons if button.text.startswith("Add modification to "))
        add_button.on_click()

    assert wizard.modifications == []
    assert mock_ui.notifications[-1] == {
        "message": "Error adding modification: could not convert string to float: 'not-a-number'",
        "type": "negative",
    }


def test_runs_step_keeps_explicit_zero_mass_shift_for_ontology_selection():
    wizard = WizardState()
    wizard.register_modification_profile("default")
    wizard.set_active_modification_profile("default")
    mock_ui = MockUIContext()

    provider_options = [
        {
            "label": "Carbamidomethyl",
            "value": "UNIMOD:4",
            "kind": "ontology",
            "ontology_id": "UNIMOD:4",
            "mode": "fixed",
            "residues": "C",
            "term_specificity": "none",
            "mass_shift": 57.021464,
        }
    ]

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("gui_nicegui.ui", mock_ui)
        monkeypatch.setattr("gui_nicegui.JSpreadsheetEditor.prepare_client_runtime", lambda: None)
        monkeypatch.setattr(
            "gui_nicegui.OntologyOptionProvider.get_modification_options",
            lambda self, custom_options=None, query=None: provider_options
            if query and query.lower() in {"unimod:4", "carbamidomethyl"}
            else [],
        )
        create_runs_step(wizard, refresh_ui=lambda: None)

    find_button = next(button for button in mock_ui.buttons if button.text == "Find UniMod entry")
    find_button.on_click()

    unimod_dialog = mock_ui.dialogs[0]
    search_input = _pick_element(unimod_dialog.inputs, "Search UniMod")
    search_input.value = "carbamidomethyl"
    search_button = next(button for button in unimod_dialog.buttons if button.text == "Search")
    search_button.on_click()

    results_select = _pick_element(unimod_dialog.selects, "UniMod results")
    results_select.value = "UNIMOD:4"

    apply_button = next(button for button in unimod_dialog.buttons if button.text == "Apply UniMod selection")
    apply_button.on_click()

    _pick_element(mock_ui.inputs, "Mass Shift").value = "0.0"

    add_button = next(button for button in mock_ui.buttons if button.text.startswith("Add modification to "))
    add_button.on_click()

    assert len(wizard.modifications) == 1
    assert wizard.modifications[0]["mass_shift"] == 0.0


def test_modification_option_provider_supports_direct_search_queries():
    try:
        from ontology_provider import OntologyOptionProvider

        class MockLiveAdapter:
            def search(self, term, limit=None):
                if term in {"carbamidomethyl", "UNIMOD:4", "acetyl"}:
                    return ["UNIMOD:4", "UNIMOD:99999"]
                return []

            def get_label(self, curie):
                return {
                    "UNIMOD:4": "Carbamidomethyl",
                    "UNIMOD:99999": "Carbamidomethyl derivative",
                }.get(curie)

        provider = OntologyOptionProvider(oak_adapter=MockLiveAdapter())
        title_options = provider.get_modification_options(query="carbamidomethyl")
        accession_options = provider.get_modification_options(query="UNIMOD:4")
        alt_title_options = provider.get_modification_options(query="acetyl")

        assert [option["value"] for option in title_options] == ["UNIMOD:4", "UNIMOD:99999"]
        assert [option["value"] for option in accession_options] == ["UNIMOD:4", "UNIMOD:99999"]
        assert [option["value"] for option in alt_title_options] == ["UNIMOD:4", "UNIMOD:99999"]
        assert all(option["kind"] == "ontology" for option in title_options)
    except ImportError as e:
        pytest.skip(f"ontology_provider module not yet implemented: {e}")


def test_modification_bridge_round_trips_existing_rows():
    wizard = WizardState()
    wizard.add_modification(
        mode="fixed",
        kind="ontology",
        name="Carbamidomethyl",
        ontology_id="UNIMOD:4",
        residues="C",
        profile="default",
    )

    bridge = JSpreadsheetBridge(wizard, entity_type="modifications")
    data = bridge.get_spreadsheet_data()

    assert "headers" in data
    assert "data" in data
    assert "mode" in data["headers"]
    assert "name" in data["headers"]
    assert data["data"][0][data["headers"].index("name")] == "Carbamidomethyl"

    bridge.handle_cell_edit(
        row_index=0,
        col_index=data["headers"].index("mode"),
        new_value="variable",
    )

    assert wizard.modifications[0]["mode"] == "variable"
