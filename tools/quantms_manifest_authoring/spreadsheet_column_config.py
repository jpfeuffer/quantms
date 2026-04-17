#!/usr/bin/env python3
"""
Column configuration builder for jspreadsheet-ce with dropdown support.

Builds column configurations from field metadata and provides dropdown options
from the ontology provider for constrained fields (e.g., instrument).
"""

from typing import Dict, List, Any, Union
from ontology_provider import OntologyOptionProvider


class ColumnConfigBuilder:
    """Builds jspreadsheet-ce column configurations with dropdown support."""

    # Map field names to ontology provider field names for dropdown options
    DROPDOWN_FIELD_MAPPING = {
        "instrument": "instrument",
    }

    def __init__(self, option_provider=None):
        """
        Initialize the builder.

        Args:
            option_provider: Optional OntologyOptionProvider instance.
                           If None, creates a new one.
        """
        self.option_provider = option_provider or OntologyOptionProvider()

    def build_column_config(
        self,
        headers: List[str],
        field_info_getter=None,
        dropdown_sources: Dict[str, List[Union[str, Dict[str, str]]]] | None = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Build column configurations for headers.

        Args:
            headers: List of column header names (field names)
            field_info_getter: Optional callable to get field metadata.
                             Takes field name, returns dict with 'type', 'required', etc.
                             If None, no type metadata is included.

        Returns:
            Dictionary mapping header names to column config dicts.
            Each config includes type info and source options for dropdowns.

        Example:
            {
                'file': {'type': 'str', 'required': True},
                'instrument': {
                    'type': 'dropdown',
                    'source': [
                        {'id': 'Q-TOF', 'name': 'Q-TOF'},
                        {'id': 'Orbitrap', 'name': 'Orbitrap'},
                        ...
                    ]
                }
            }
        """
        config = {}

        for header in headers:
            col_config = {}

            # Get field metadata if provider available
            if field_info_getter:
                try:
                    field_meta = field_info_getter(header)
                    # Store original type from metadata
                    col_config["type"] = field_meta.get("type", "str")
                    col_config["required"] = field_meta.get("required", False)
                except Exception:
                    # If field info lookup fails, just continue
                    col_config["type"] = "str"

            # Prefer explicit dropdown sources supplied by the caller.
            if dropdown_sources and header in dropdown_sources:
                options = dropdown_sources[header]
                if options:
                    col_config["type"] = "dropdown"
                    col_config["source"] = self._convert_options_to_jspreadsheet_format(options)

            # Check if this field should be a dropdown
            elif header in self.DROPDOWN_FIELD_MAPPING:
                ontology_field = self.DROPDOWN_FIELD_MAPPING[header]
                options = self.option_provider.get_options(ontology_field)

                if options:
                    # Mark as dropdown and include options
                    col_config["type"] = "dropdown"
                    # Convert options to jspreadsheet-ce format (id/name)
                    col_config["source"] = self._convert_options_to_jspreadsheet_format(options)

            config[header] = col_config

        return config

    def _convert_options_to_jspreadsheet_format(
        self, options: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        """
        Convert ontology options from {'label': '...', 'value': '...'} format
        to jspreadsheet-ce format {'id': '...', 'name': '...'}.

        Args:
            options: List of dicts with 'label' and 'value' keys

        Returns:
            List of dicts with 'id' and 'name' keys
        """
        converted = []
        for opt in options:
            if isinstance(opt, dict):
                # Convert label/value to id/name for jspreadsheet-ce
                value = opt.get("value") or opt.get("id")
                label = opt.get("label") or opt.get("name")
                if value is not None and label is not None:
                    converted.append({"id": value, "name": label})
            elif isinstance(opt, str):
                # Already a string, use as both id and name
                converted.append({"id": opt, "name": opt})
        return converted

    def get_dropdown_options_for_field(self, field: str) -> List[Union[str, Dict[str, str]]]:
        """
        Get dropdown options for a specific field.

        Args:
            field: Field name (e.g., 'instrument')

        Returns:
            List of options from ontology provider, or empty list if not a dropdown field
        """
        if field not in self.DROPDOWN_FIELD_MAPPING:
            return []

        ontology_field = self.DROPDOWN_FIELD_MAPPING[field]
        return self.option_provider.get_options(ontology_field)
