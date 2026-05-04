#!/usr/bin/env python3
"""
Shared ontology/CV option provider for authoring fields.

Provides controlled dropdown options for ontology-backed authoring fields using
Oaklib for ontology-based lookups, with graceful fallback to local definitions
when Oaklib is unavailable.

Supported fields:
- enzyme: proteolytic enzymes (Oaklib + fallback)
- dissociation_method: MS dissociation methods (Oaklib + fallback)
- instrument: MS instruments (Oaklib + fallback)
- organism: biological organisms (Oaklib + fallback)
- organism_part: tissue/cellular compartments (Oaklib + fallback)
- disease: disease states (Oaklib + fallback)
- cell_type: cell types (Oaklib + fallback)
"""

from typing import List, Union, Dict, Any, Optional

try:
    from oaklib import get_adapter as _oak_get_adapter
    OAK_AVAILABLE = True
except ImportError:
    OAK_AVAILABLE = False

from modification_catalog import (
    build_bundled_modification_options,
    get_bundled_modification_search_terms,
    merge_modification_options,
    normalize_custom_modification_options,
)


# Local fallback definitions for when Oaklib is unavailable
FALLBACK_ENZYME_OPTIONS = [
    {"label": "Trypsin", "value": "Trypsin"},
    {"label": "Pepsin", "value": "Pepsin"},
    {"label": "Chymotrypsin", "value": "Chymotrypsin"},
    {"label": "Lys-C", "value": "Lys-C"},
    {"label": "Arg-C", "value": "Arg-C"},
    {"label": "Asp-N", "value": "Asp-N"},
    {"label": "Glu-C", "value": "Glu-C"},
    {"label": "Semi-tryptic", "value": "Semi-tryptic"},
    {"label": "Elastase", "value": "Elastase"},
    {"label": "Thermolysin", "value": "Thermolysin"},
    {"label": "Cyanogen bromide", "value": "Cyanogen bromide"},
]

FALLBACK_DISSOCIATION_METHOD_OPTIONS = [
    {"label": "HCD", "value": "HCD"},
    {"label": "CID", "value": "CID"},
    {"label": "ETD", "value": "ETD"},
    {"label": "UVPD", "value": "UVPD"},
    {"label": "ECD", "value": "ECD"},
    {"label": "IRMPD", "value": "IRMPD"},
    {"label": "PSD", "value": "PSD"},
    {"label": "LIFT", "value": "LIFT"},
]

FALLBACK_INSTRUMENT_OPTIONS = [
    {"label": "Q-TOF", "value": "Q-TOF"},
    {"label": "Orbitrap", "value": "Orbitrap"},
    {"label": "Ion Trap", "value": "Ion Trap"},
    {"label": "MALDI-TOF", "value": "MALDI-TOF"},
    {"label": "Tribrid", "value": "Tribrid"},
    {"label": "Q Exactive", "value": "Q Exactive"},
    {"label": "Orbitrap Exploris 480", "value": "Orbitrap Exploris 480"},
    {"label": "Orbitrap Fusion Lumos", "value": "Orbitrap Fusion Lumos"},
    {"label": "LTQ Orbitrap Velos", "value": "LTQ Orbitrap Velos"},
    {"label": "TripleTOF 6600", "value": "TripleTOF 6600"},
    {"label": "timsTOF Pro", "value": "timsTOF Pro"},
]

FALLBACK_ORGANISM_OPTIONS = [
    {"label": "Homo sapiens", "value": "Homo sapiens"},
    {"label": "Mus musculus", "value": "Mus musculus"},
    {"label": "Arabidopsis thaliana", "value": "Arabidopsis thaliana"},
    {"label": "Caenorhabditis elegans", "value": "Caenorhabditis elegans"},
    {"label": "Drosophila melanogaster", "value": "Drosophila melanogaster"},
    {"label": "Saccharomyces cerevisiae", "value": "Saccharomyces cerevisiae"},
    {"label": "Escherichia coli", "value": "Escherichia coli"},
    {"label": "Chlorocebus aethiops", "value": "Chlorocebus aethiops"},
]

FALLBACK_ORGANISM_PART_OPTIONS = [
    {"label": "Liver", "value": "Liver"},
    {"label": "Brain", "value": "Brain"},
    {"label": "Heart", "value": "Heart"},
    {"label": "Kidney", "value": "Kidney"},
    {"label": "Muscle", "value": "Muscle"},
    {"label": "Blood", "value": "Blood"},
    {"label": "Serum", "value": "Serum"},
    {"label": "Plasma", "value": "Plasma"},
]

FALLBACK_DISEASE_OPTIONS = [
    {"label": "Normal", "value": "Normal"},
    {"label": "Diabetes", "value": "Diabetes"},
    {"label": "Cancer", "value": "Cancer"},
    {"label": "Alzheimer's disease", "value": "Alzheimer's disease"},
    {"label": "Parkinson's disease", "value": "Parkinson's disease"},
]

FALLBACK_CELL_TYPE_OPTIONS = [
    {"label": "Neuron", "value": "Neuron"},
    {"label": "Fibroblast", "value": "Fibroblast"},
    {"label": "Hepatocyte", "value": "Hepatocyte"},
    {"label": "T cell", "value": "T cell"},
    {"label": "B cell", "value": "B cell"},
    {"label": "Macrophage", "value": "Macrophage"},
]

# Mapping of field names to their corresponding fallback options
FALLBACK_OPTIONS_MAP = {
    "enzyme": FALLBACK_ENZYME_OPTIONS,
    "dissociation_method": FALLBACK_DISSOCIATION_METHOD_OPTIONS,
    "instrument": FALLBACK_INSTRUMENT_OPTIONS,
    "organism": FALLBACK_ORGANISM_OPTIONS,
    "organism_part": FALLBACK_ORGANISM_PART_OPTIONS,
    "disease": FALLBACK_DISEASE_OPTIONS,
    "cell_type": FALLBACK_CELL_TYPE_OPTIONS,
}

PSI_MS_INSTRUMENT_ROOT = "MS:1000463"


class OntologyOptionProvider:
    """
    Provides ontology-backed option choices for authoring fields.

    Falls back to local definitions when Oaklib is unavailable.
    Supports injectable Oaklib adapter for testing and flexibility.
    """

    def __init__(self, oak_adapter=None):
        """
        Initialize the option provider.

        Args:
            oak_adapter: Optional Oaklib adapter instance for ontology lookups.
                        If None, will attempt to create one if OAK_AVAILABLE.
                        Can be injected for testing purposes.
        """
        self._oak_adapter = oak_adapter
        self._modification_adapter = oak_adapter if oak_adapter is not None else None
        self._oak_adapter_is_injected = oak_adapter is not None

    def get_options(
        self, field: str
    ) -> List[Union[str, Dict[str, str]]]:
        """
        Get available options for a given field.

        Args:
            field: Field name (e.g., 'enzyme', 'dissociation_method')

        Returns:
            List of options, each as a string or dict with 'label' and 'value' keys.
            Returns empty list if field is unknown.
        """
        if field not in FALLBACK_OPTIONS_MAP:
            # Unknown field - return empty list
            return []

        # Try to load from Oaklib first (injected adapter or OAK_AVAILABLE)
        # Fall back to local definitions if no Oaklib path is available
        try:
            options = self._get_options_from_oaklib(field)
            if options:
                return options
        except Exception:
            # Fall back to local options if Oaklib lookup fails
            pass

        # Return fallback options
        return FALLBACK_OPTIONS_MAP.get(field, []).copy()

    def _get_options_from_oaklib(
        self, field: str
    ) -> Optional[List[Dict[str, str]]]:
        """
        Attempt to load options from Oaklib.

        Uses the injected adapter or creates a new one if OAK_AVAILABLE.
        Works with injected adapters even if Oaklib is not installed globally.
        Maps field names to ontology term collections and queries for curated terms.

        Args:
            field: Field name to look up in ontology

        Returns:
            List of dicts with 'label' and 'value' keys, or None if lookup fails.
        """
        try:
            # Use injected adapter or initialize if needed
            adapter = self._oak_adapter
            if adapter is None:
                # Only attempt to create adapter if OAK_AVAILABLE
                if not OAK_AVAILABLE:
                    return None
                # Attempt to create adapter for PSI-MS ontology (minimal production path)
                adapter = _oak_get_adapter("sqlite:obo:psi-ms")
                self._oak_adapter = adapter

            if field == "instrument":
                return self._get_instrument_options_from_subtree(adapter)

            # Other fields still use a simple lexical fallback path for now.
            field_mapping = {
                "enzyme": ["protease", "enzyme"],
                "dissociation_method": ["dissociation method"],
                "organism": ["organism", "species"],
                "organism_part": ["tissue", "organ", "cellular component"],
                "disease": ["disease", "disorder"],
                "cell_type": ["cell type", "cell"],
            }

            if field not in field_mapping:
                return None

            options = []
            seen_labels = set()
            for search_term in field_mapping[field]:
                if not hasattr(adapter, "search"):
                    continue
                try:
                    try:
                        matches = list(adapter.search(search_term, limit=50))
                    except TypeError:
                        matches = list(adapter.search(search_term))
                except Exception:
                    continue

                for curie in matches:
                    label = adapter.get_label(curie)
                    if label and label not in seen_labels:
                        options.append({"label": label, "value": label})
                        seen_labels.add(label)

            return options if options else None

        except Exception:
            # If anything goes wrong (adapter creation, search, etc), return None
            # to gracefully fall back to local definitions
            return None

    def _get_instrument_options_from_subtree(self, adapter) -> Optional[List[Dict[str, str]]]:
        """
        Get PSI-MS instrument options from the instrument subtree.

        Uses the PSI-MS root term `MS:1000463` (instrument) and walks descendants
        instead of performing a broad keyword search.
        Values remain human-readable labels because the rest of the authoring
        flow stores instrument names, not CURIEs.
        """
        if not hasattr(adapter, "descendants"):
            return None

        try:
            descendants = list(adapter.descendants(PSI_MS_INSTRUMENT_ROOT, reflexive=False))
        except TypeError:
            descendants = list(adapter.descendants(PSI_MS_INSTRUMENT_ROOT))
            descendants = [curie for curie in descendants if curie != PSI_MS_INSTRUMENT_ROOT]

        options = []
        seen_labels = set()
        for curie in descendants:
            try:
                label = adapter.get_label(curie)
            except Exception:
                continue

            if not label or label in seen_labels:
                continue

            options.append({"label": label, "value": label})
            seen_labels.add(label)

        options.sort(key=lambda option: option["label"].lower())
        return options if options else None

    def get_supported_fields(self) -> List[str]:
        """
        Get list of supported field names.

        Returns:
            List of field names that have option providers.
        """
        return list(FALLBACK_OPTIONS_MAP.keys())

    def get_modification_options(
        self,
        custom_options: Optional[List[Union[str, Dict[str, Any]]]] = None,
    ) -> List[Dict[str, Any]]:
        """Get dropdown-ready modification options with live-first lookup and offline fallback."""
        live_options = self._get_modification_options_from_oaklib()
        if live_options:
            base_options = live_options
        else:
            base_options = build_bundled_modification_options()

        custom_normalized = normalize_custom_modification_options(custom_options)
        return merge_modification_options(base_options, custom_normalized)

    def _get_modification_options_from_oaklib(self) -> Optional[List[Dict[str, Any]]]:
        """Attempt to resolve modification options from a live ontology adapter."""
        adapter = self._modification_adapter
        if adapter is None:
            if self._oak_adapter_is_injected and self._oak_adapter is not None:
                adapter = self._oak_adapter
            elif not OAK_AVAILABLE:
                return None
            else:
                try:
                    adapter = _oak_get_adapter("sqlite:obo:unimod")
                    self._modification_adapter = adapter
                except Exception:
                    return None

        if not hasattr(adapter, "search") or not hasattr(adapter, "get_label"):
            return None

        options: List[Dict[str, Any]] = []
        seen_values = set()
        seen_labels = set()

        for search_term in get_bundled_modification_search_terms():
            try:
                try:
                    matches = list(adapter.search(search_term, limit=25))
                except TypeError:
                    matches = list(adapter.search(search_term))
            except Exception:
                continue

            for curie in matches:
                try:
                    label = adapter.get_label(curie)
                except Exception:
                    continue

                if not label or label in seen_labels or curie in seen_values:
                    continue

                options.append(
                    {
                        "label": label,
                        "value": curie,
                        "kind": "ontology",
                        "ontology_id": curie,
                        "name": label,
                    }
                )
                seen_values.add(curie)
                seen_labels.add(label)

        options.sort(key=lambda option: option["label"].lower())
        return options if options else None
