#!/usr/bin/env python3
"""Bundled modification option catalog for the manifest authoring UI."""

from typing import Any, Dict, Iterable, List, Optional


BUNDLED_MODIFICATION_OPTIONS: List[Dict[str, Any]] = [
    {
        "ontology_id": "UNIMOD:4",
        "name": "Carbamidomethyl",
        "label": "Carbamidomethyl",
        "value": "UNIMOD:4",
        "kind": "ontology",
        "mode": "fixed",
        "residues": ["C"],
        "term_specificity": "none",
        "mass_shift": 57.021464,
    },
    {
        "ontology_id": "UNIMOD:21",
        "name": "Phosphorylation",
        "label": "Phosphorylation",
        "value": "UNIMOD:21",
        "kind": "ontology",
        "mode": "variable",
        "residues": ["S", "T", "Y"],
        "term_specificity": "none",
        "mass_shift": 79.966331,
        "formula": "HO3P",
    },
    {
        "ontology_id": "UNIMOD:35",
        "name": "Oxidation",
        "label": "Oxidation",
        "value": "UNIMOD:35",
        "kind": "ontology",
        "mode": "variable",
        "residues": ["M"],
        "term_specificity": "none",
        "mass_shift": 15.994915,
    },
]


def get_bundled_modification_search_terms() -> List[str]:
    """Return the curated names used to seed live modification lookup."""
    terms = []
    seen = set()
    for option in BUNDLED_MODIFICATION_OPTIONS:
        term = option.get("name")
        if term and term not in seen:
            terms.append(term)
            seen.add(term)
    return terms


def normalize_modification_option(option: Any) -> Optional[Dict[str, Any]]:
    """Normalize a raw modification option into dropdown-ready dictionary form."""
    if option is None:
        return None

    if isinstance(option, str):
        return {
            "label": option,
            "value": option,
            "kind": "custom",
        }

    if not isinstance(option, dict):
        return None

    normalized = dict(option)
    label = normalized.get("label") or normalized.get("name")
    value = normalized.get("value") or normalized.get("ontology_id") or normalized.get("id") or label

    if not label or not value:
        return None

    normalized["label"] = label
    normalized["value"] = value

    if not normalized.get("kind"):
        normalized["kind"] = "ontology" if normalized.get("ontology_id") else "custom"

    if normalized["kind"] == "ontology" and not normalized.get("ontology_id"):
        normalized["ontology_id"] = value

    return normalized


def build_bundled_modification_options() -> List[Dict[str, Any]]:
    """Return a copy of the bundled fallback modification options."""
    return [dict(option) for option in BUNDLED_MODIFICATION_OPTIONS]


def normalize_custom_modification_options(
    custom_options: Iterable[Any] | None,
) -> List[Dict[str, Any]]:
    """Normalize custom modification options into dropdown-ready dictionaries."""
    if not custom_options:
        return []

    normalized_options: List[Dict[str, Any]] = []
    for option in custom_options:
        normalized = normalize_modification_option(option)
        if not normalized:
            continue
        normalized["kind"] = "custom"
        normalized_options.append(normalized)
    return normalized_options


def merge_modification_options(*option_groups: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge option groups while preserving order and skipping duplicate values."""
    merged: List[Dict[str, Any]] = []
    seen_values = set()
    seen_labels = set()

    for option_group in option_groups:
        for raw_option in option_group or []:
            option = normalize_modification_option(raw_option)
            if not option:
                continue

            option_value = option.get("value")
            option_label = option.get("label")
            if option_value in seen_values or option_label in seen_labels:
                continue

            merged.append(option)
            seen_values.add(option_value)
            seen_labels.add(option_label)

    return merged