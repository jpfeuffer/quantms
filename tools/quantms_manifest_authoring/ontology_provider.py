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

UNIMOD_POSITION_TO_TERM_SPECIFICITY = {
    "anywhere": "none",
    "any n-term": "n-term",
    "any c-term": "c-term",
    "protein n-term": "protein-n-term",
    "protein c-term": "protein-c-term",
}


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
        query: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get dropdown-ready modification options with live-first lookup and offline fallback."""
        normalized_query = (query or "").strip()
        live_options = self._get_modification_options_from_oaklib(query=normalized_query or None)
        if live_options:
            base_options = live_options
        else:
            base_options = build_bundled_modification_options()
            if normalized_query:
                query_text = normalized_query.lower()
                base_options = [option for option in base_options if self._matches_bundled_modification_query(option, query_text)]

        custom_normalized = normalize_custom_modification_options(custom_options)
        return merge_modification_options(base_options, custom_normalized)

    def _get_modification_search_terms(self, query: Optional[str] = None) -> List[str]:
        """Build UniMod search terms, normalizing shorthand accessions to canonical CURIEs."""
        normalized_query = (query or "").strip()
        if not normalized_query:
            return get_bundled_modification_search_terms()

        upper_query = normalized_query.upper()
        if normalized_query.isdigit():
            return [f"UNIMOD:{normalized_query}"]

        if upper_query.startswith("UNIMOD:"):
            accession = normalized_query.split(":", 1)[1].strip()
            if accession.isdigit():
                return [f"UNIMOD:{accession}"]

        return [normalized_query]

    def _matches_bundled_modification_query(self, option: Dict[str, Any], query_text: str) -> bool:
        """Return True when a bundled modification option matches the offline query text."""
        haystacks: List[str] = [
            str(option.get("label", "")),
            str(option.get("name", "")),
            str(option.get("value", "")),
            str(option.get("ontology_id", "")),
            str(option.get("classification", "")),
            str(option.get("description", "")),
        ]

        for field_name in ("aliases", "search_terms"):
            field_value = option.get(field_name)
            if isinstance(field_value, (list, tuple, set)):
                haystacks.extend(str(entry) for entry in field_value)
            elif field_value:
                haystacks.append(str(field_value))

        return any(query_text in haystack.lower() for haystack in haystacks if haystack)

    def _build_modification_option_from_ols_record(self, record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize an OLS raw search record into a dropdown-ready modification option."""
        label = record.get("label")
        value = record.get("obo_id") or record.get("short_form")
        if not value:
            iri = record.get("iri") or ""
            if "/obo/UNIMOD_" in iri:
                value = f"UNIMOD:{iri.rsplit('UNIMOD_', 1)[-1]}"

        if not label or not value:
            return None

        description = record.get("description")
        if isinstance(description, list):
            description = " ".join(item for item in description if item)

        synonyms = record.get("synonym") or record.get("related_synonyms")
        if isinstance(synonyms, str):
            synonyms = [synonyms]

        return {
            "label": label,
            "value": value,
            "kind": "ontology",
            "ontology_id": value,
            "name": label,
            "description": description,
            "aliases": synonyms or [],
            "iri": record.get("iri"),
        }

    def enrich_modification_option(self, option: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Hydrate a selected UniMod search option with term-level metadata when available."""
        if not option or option.get("kind") != "ontology":
            return option

        adapter = self._modification_adapter or self._oak_adapter
        if adapter is None or not hasattr(adapter, "client") or not hasattr(adapter.client, "get_term"):
            return option

        iri = option.get("iri")
        if not iri:
            ontology_id = str(option.get("ontology_id") or option.get("value") or "").strip()
            if ontology_id.upper().startswith("UNIMOD:"):
                iri = f"http://purl.obolibrary.org/obo/{ontology_id.upper().replace(':', '_')}"

        if not iri:
            return option

        focus_ontology = str(getattr(adapter, "focus_ontology", "unimod") or "unimod").lower()

        try:
            term_response = adapter.client.get_term(focus_ontology, iri)
        except Exception:
            return option

        term = self._extract_ols_term(term_response)
        if not term:
            return option

        enriched_option = dict(option)
        enriched_option.update(self._build_modification_option_details_from_ols_term(term))

        description = term.get("description")
        if isinstance(description, list):
            description = " ".join(item for item in description if item)
        if description and not enriched_option.get("description"):
            enriched_option["description"] = description

        synonyms = term.get("synonyms") or term.get("obo_synonym")
        if isinstance(synonyms, str):
            synonyms = [synonyms]
        if synonyms and not enriched_option.get("aliases"):
            enriched_option["aliases"] = synonyms

        return enriched_option

    def _extract_ols_term(self, term_response: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract the first term entry from an OLS term response."""
        if not isinstance(term_response, dict):
            return None

        if term_response.get("obo_id"):
            return term_response

        embedded = term_response.get("_embedded") or {}
        terms = embedded.get("terms") or []
        if terms:
            return terms[0]

        return None

    def _build_modification_option_details_from_ols_term(self, term: Dict[str, Any]) -> Dict[str, Any]:
        """Extract user-facing UniMod metadata from an OLS term record."""
        details: Dict[str, Any] = {}
        xrefs = term.get("obo_xref") or []
        specificity_groups: Dict[str, Dict[str, Any]] = {}

        for xref in xrefs:
            if not isinstance(xref, dict):
                continue

            xref_id = str(xref.get("id") or "").strip()
            description = xref.get("description")
            if not xref_id or description is None:
                continue

            description_text = str(description).strip()
            if xref_id == "delta_mono_mass":
                try:
                    details["mass_shift"] = float(description_text)
                except ValueError:
                    pass
                continue

            if xref_id == "delta_composition":
                details["formula"] = description_text
                continue

            if not xref_id.startswith("spec_"):
                continue

            _, group_id, field_name = xref_id.split("_", 2)
            group = specificity_groups.setdefault(group_id, {"site": []})
            if field_name == "site":
                group.setdefault("site", []).append(description_text)
            else:
                group[field_name] = description_text

        allowed_sites_by_term_specificity: Dict[str, List[str]] = {}
        allowed_term_specificities: List[str] = []

        for group_id in sorted(specificity_groups, key=lambda value: int(value)):
            group = specificity_groups[group_id]
            if str(group.get("hidden", "0")).strip().lower() in {"1", "true", "yes"}:
                continue

            position = str(group.get("position") or "").strip().lower()
            term_specificity = UNIMOD_POSITION_TO_TERM_SPECIFICITY.get(position)
            if not term_specificity:
                continue

            if term_specificity not in allowed_term_specificities:
                allowed_term_specificities.append(term_specificity)

            sites = allowed_sites_by_term_specificity.setdefault(term_specificity, [])
            for raw_site in group.get("site", []):
                normalized_site = self._normalize_unimod_site(raw_site)
                if normalized_site and normalized_site not in sites:
                    sites.append(normalized_site)

        if allowed_term_specificities:
            details["allowed_term_specificities"] = allowed_term_specificities
            details["allowed_sites_by_term_specificity"] = allowed_sites_by_term_specificity

            default_term_specificity = allowed_term_specificities[0]
            if "none" in allowed_term_specificities:
                default_term_specificity = "none"

            details["term_specificity"] = default_term_specificity
            default_sites = allowed_sites_by_term_specificity.get(default_term_specificity) or []
            if default_sites:
                details["residues"] = "".join(default_sites)

        return details

    def _normalize_unimod_site(self, site: Any) -> Optional[str]:
        """Normalize UniMod site strings into residue codes when possible."""
        site_text = str(site or "").strip()
        if len(site_text) == 1 and site_text.isalpha():
            return site_text.upper()
        return None

    def _get_modification_options_from_oaklib(self, query: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
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
                    try:
                        adapter = _oak_get_adapter("ols:unimod")
                        self._modification_adapter = adapter
                    except Exception:
                        return None

        options: List[Dict[str, Any]] = []
        seen_values = set()
        seen_labels = set()

        search_terms = self._get_modification_search_terms(query)

        if hasattr(adapter, "client") and hasattr(adapter.client, "search"):
            params = {
                "type": "class",
                "local": "true",
                "fieldList": "iri,label,obo_id,short_form,description,synonym",
                "rows": 50,
                "start": 0,
            }
            focus_ontology = getattr(adapter, "focus_ontology", None)
            if focus_ontology:
                params["ontology"] = str(focus_ontology).lower()

            for search_term in search_terms:
                if not search_term:
                    continue
                try:
                    records = list(adapter.client.search(search_term, params=params))
                except Exception:
                    continue

                for record in records:
                    option = self._build_modification_option_from_ols_record(record)
                    if not option:
                        continue

                    option_value = option.get("value")
                    option_label = option.get("label")
                    if option_value in seen_values or option_label in seen_labels:
                        continue

                    options.append(option)
                    seen_values.add(option_value)
                    seen_labels.add(option_label)

            options.sort(key=lambda option: option["label"].lower())
            return options if options else None

        if not hasattr(adapter, "search") or not hasattr(adapter, "get_label"):
            return None

        for search_term in search_terms:
            if not search_term:
                continue
            try:
                try:
                    matches = list(adapter.search(search_term, limit=50))
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
