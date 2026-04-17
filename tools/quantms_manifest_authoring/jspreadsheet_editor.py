#!/usr/bin/env python3
"""
Utilities for embedding jspreadsheet-ce in NiceGUI with Python backend sync.

Provides a wrapper that manages the JavaScript initialization and callbacks
between the spreadsheet and Python WizardState.

Event Bridge Pattern:
- JavaScript emits JSON events with type, widget_id, and payload
- Python handlers receive events and update WizardState
- NiceGUI's callback mechanism bridges the two
"""

import json
import uuid
from pathlib import Path
from typing import Any, Callable

from nicegui import app, context, ui
from jspreadsheet_bridge import JSpreadsheetBridge
from gui_wizard_state import WizardState


class JSpreadsheetEditor:
    """
    NiceGUI wrapper for jspreadsheet-ce with Python backend integration.

    Manages:
    - Initialization of spreadsheet with data from WizardState
    - Cell edit callbacks from JavaScript via real event bridge
    - Row delete callbacks from JavaScript via real event bridge
    - Persistent state synchronization via JSpreadsheetBridge
    - Proper mounting into NiceGUI container (not document.body)
    """

    ASSET_ROUTE = '/quantms-manifest/vendor'

    def __init__(self, wizard: WizardState, on_change: Callable[[], None]):
        """
        Initialize the spreadsheet editor.

        Args:
            wizard: WizardState instance to sync with
            on_change: Callback to invoke when data changes (for UI refresh)
        """
        self.wizard = wizard
        self.bridge = JSpreadsheetBridge(wizard)
        self.on_change = on_change
        self.container = None

        self.widget_id = f"jse_{uuid.uuid4().hex[:8]}"

    @classmethod
    def prepare_client_runtime(cls) -> None:
        cls._ensure_cdn_loaded()
        cls._ensure_event_bridge_registered()

    @classmethod
    def _get_registry(cls, attribute: str, factory: Callable[[], Any]):
        value = getattr(cls, attribute, None)
        if value is None:
            value = factory()
            setattr(cls, attribute, value)
        return value

    @classmethod
    def _asset_root(cls) -> Path:
        return Path(__file__).parent / 'assets' / 'vendor'

    @classmethod
    def _client_key(cls) -> int:
        return getattr(context.client, 'id', id(context.client))

    @classmethod
    def _head_html(cls) -> str:
        return f"""
            <link rel=\"stylesheet\" href=\"{cls.ASSET_ROUTE}/jsuites/jsuites.css\" />
            <link rel=\"stylesheet\" href=\"{cls.ASSET_ROUTE}/jspreadsheet-ce/jspreadsheet.css\" />
        """

    @classmethod
    def _asset_loader_script(cls) -> str:
        jsuites_src = f"{cls.ASSET_ROUTE}/jsuites/jsuites.js"
        jspreadsheet_src = f"{cls.ASSET_ROUTE}/jspreadsheet-ce/jspreadsheet.js"
        return f"""
            window.__quantmsSpreadsheetErrors = window.__quantmsSpreadsheetErrors || [];
            window.__quantmsSpreadsheetAssetsPromise = window.__quantmsSpreadsheetAssetsPromise || (async () => {{
                const loadScript = (src, globalName) => new Promise((resolve, reject) => {{
                    if (typeof window[globalName] !== 'undefined') {{
                        resolve(window[globalName]);
                        return;
                    }}

                    const script = document.createElement('script');
                    script.src = src;
                    script.async = false;
                    script.onload = () => {{
                        if (typeof window[globalName] === 'undefined') {{
                            reject(new Error(`${{globalName}} global missing after loading ${{src}}`));
                            return;
                        }}
                        resolve(window[globalName]);
                    }};
                    script.onerror = () => reject(new Error(`Failed to load ${{src}}`));
                    document.head.appendChild(script);
                }});

                window.formula = window.formula || null;
                await loadScript({json.dumps(jsuites_src)}, 'jSuites');
                await loadScript({json.dumps(jspreadsheet_src)}, 'jspreadsheet');
                return true;
            }})().catch((error) => {{
                const message = error && error.message ? error.message : String(error);
                window.__quantmsSpreadsheetErrors.push(message);
                throw error;
            }});
        """

    @staticmethod
    def _ensure_cdn_loaded():
        """Ensure jspreadsheet libraries are served locally and loaded once per client."""
        static_registered = JSpreadsheetEditor._get_registry('_static_assets_registered', lambda: False)
        if not static_registered:
            app.add_static_files(JSpreadsheetEditor.ASSET_ROUTE, str(JSpreadsheetEditor._asset_root()))
            JSpreadsheetEditor._static_assets_registered = True

        loaded_clients = JSpreadsheetEditor._get_registry('_cdn_loaded_clients', set)
        client_key = JSpreadsheetEditor._client_key()
        if client_key in loaded_clients:
            return

        ui.add_head_html(JSpreadsheetEditor._head_html())
        loaded_clients.add(client_key)

        def load_assets() -> None:
            context.client.run_javascript(JSpreadsheetEditor._asset_loader_script())

        if getattr(context.client, 'has_socket_connection', False):
            load_assets()
        else:
            on_connect = getattr(context.client, 'on_connect', None)
            if callable(on_connect):
                on_connect(load_assets)

    @staticmethod
    def _ensure_event_bridge_registered() -> None:
        registered_clients = JSpreadsheetEditor._get_registry('_event_bridge_clients', set)
        client_key = JSpreadsheetEditor._client_key()
        if client_key in registered_clients:
            return

        ui.on('spreadsheet_event', JSpreadsheetEditor._dispatch_spreadsheet_event)
        registered_clients.add(client_key)

    @staticmethod
    def _dispatch_spreadsheet_event(event_data) -> None:
        if not isinstance(event_data, dict):
            return

        widget_id = event_data.get('widget_id')
        if not widget_id:
            return

        instances = JSpreadsheetEditor._get_registry('_instances', dict)
        editor = instances.get(widget_id)
        if editor is not None:
            editor._handle_spreadsheet_event(event_data)

    def render(self) -> None:
        """Render the spreadsheet editor in NiceGUI into proper container."""
        self.container = ui.element('div').classes('w-full min-h-96 overflow-auto rounded border border-gray-200 bg-white')

        self._get_registry('_instances', dict)[self.widget_id] = self
        self.prepare_client_runtime()

        if not self.wizard or not self.wizard.runs:
            return

        if getattr(context.client, 'has_socket_connection', False):
            self._initialize_spreadsheet()
        else:
            on_connect = getattr(context.client, 'on_connect', None)
            if callable(on_connect):
                on_connect(self._initialize_spreadsheet)

    def _initialize_spreadsheet(self) -> None:
        if not self.container or not self.wizard or not self.wizard.runs:
            return

        self._initialize_data()
        self._create_spreadsheet_widget()

    def _initialize_data(self) -> None:
        """Initialize spreadsheet with data from wizard state."""
        spreadsheet_data = self.bridge.get_spreadsheet_data()
        headers = spreadsheet_data["headers"]
        data = spreadsheet_data["data"]
        column_config = spreadsheet_data.get("column_config", {})
        container_id = self.container.html_id if self.container else None
        headers_json = json.dumps(headers)
        data_json = json.dumps(data)
        column_config_json = json.dumps(column_config)
        widget_id_json = json.dumps(self.widget_id)
        container_id_json = json.dumps(container_id)

        script = f"""
            window.__quantmsSpreadsheetData = window.__quantmsSpreadsheetData || {{}};
            window.__quantmsSpreadsheetData[{widget_id_json}] = {{
                headers: {headers_json},
                data: {data_json},
                column_config: {column_config_json},
                widget_id: {widget_id_json},
                container_id: {container_id_json}
            }};
        """

        context.client.run_javascript(script)

    def _create_spreadsheet_widget(self) -> None:
        widget_id = self.widget_id
        script = f"""
        (function() {{
            const emitSpreadsheetEvent = (payload) => {{
                if (window.emitEvent) {{
                    window.emitEvent('spreadsheet_event', payload);
                    return;
                }}
                if (window.nicegui && window.nicegui.emitEvent) {{
                    window.nicegui.emitEvent('spreadsheet_event', payload);
                    return;
                }}

                window.pendingSpreadsheetEvents = window.pendingSpreadsheetEvents || [];
                window.pendingSpreadsheetEvents.push(payload);
            }};

            function initializeSpreadsheet() {{
                const spreadsheetData = window.__quantmsSpreadsheetData && window.__quantmsSpreadsheetData[{json.dumps(widget_id)}];
                if (!spreadsheetData) {{
                    console.error('Spreadsheet data not found for widget {widget_id}');
                    return false;
                }}

                const headers = spreadsheetData.headers || [];
                const data = spreadsheetData.data || [];
                const columnConfig = spreadsheetData.column_config || {{}};
                const containerId = spreadsheetData.container_id;
                const widgetId = spreadsheetData.widget_id;

                if (headers.length === 0) {{
                    console.log('No spreadsheet data available');
                    return false;
                }}

                // Lookup container first, before calculating widths
                const container = document.getElementById(containerId);
                if (!container) {{
                    console.error('Container element not found:', containerId);
                    return false;
                }}

                // Calculate responsive column widths based on container width
                const containerWidth = container.offsetWidth || container.clientWidth || 800;
                const minFileColWidth = 200;  // Minimum width for file column
                const minOtherColWidth = 100;  // Minimum width for other columns

                const numCols = headers.length;
                const fileColsCount = 1;  // 'file' column
                const otherColsCount = numCols - fileColsCount;

                // Reserve space for file column, distribute remainder equally
                const remainingWidth = Math.max(0, containerWidth - minFileColWidth - (otherColsCount * minOtherColWidth));
                const additionalFileWidth = remainingWidth * 0.6;  // File column gets 60% of extra space
                const additionalOtherWidth = remainingWidth * 0.4 / Math.max(1, otherColsCount);

                const columns = headers.map(header => {{
                    const title = header
                        .replace(/_/g, ' ')
                        .replace(/\\b\\w/g, letter => letter.toUpperCase());
                    const width = header === 'file'
                        ? Math.max(minFileColWidth, minFileColWidth + additionalFileWidth)
                        : Math.max(minOtherColWidth, minOtherColWidth + additionalOtherWidth);
                    return {{ title, width }};
                }});

                // Merge dropdown configuration from columnConfig into columns
                headers.forEach((header, index) => {{
                    if (columnConfig[header]) {{
                        const config = columnConfig[header];
                        if (config.type === 'dropdown' && config.source) {{
                            // Merge dropdown properties into column definition
                            columns[index].type = 'dropdown';
                            columns[index].source = config.source;
                        }}
                    }}
                }});

                if (window.jspreadsheet && typeof window.jspreadsheet.destroy === 'function' && container.spreadsheet) {{
                    try {{
                        window.jspreadsheet.destroy(container, false);
                    }} catch (error) {{
                        console.warn('Failed to destroy previous spreadsheet instance', error);
                    }}
                }}

                container.innerHTML = '';
                window.__quantmsSpreadsheetInstances = window.__quantmsSpreadsheetInstances || {{}};

                const spreadsheet = window.jspreadsheet(container, {{
                    tabs: false,
                    toolbar: false,
                    worksheets: [{{
                        worksheetName: 'Runs',
                        data: data,
                        columns: columns,
                        minDimensions: [headers.length, Math.max(data.length, 5)],
                        tableOverflow: true,
                        editable: true,
                        allowInsertColumn: false,
                        allowDeleteColumn: false,
                        allowManualInsertColumn: false,
                        allowInsertRow: false,
                        allowManualInsertRow: false,
                        onchange: function(worksheet, cell, x, y, value) {{
                            emitSpreadsheetEvent({{
                                type: 'cell_edit',
                                widget_id: widgetId,
                                row: y,
                                col: x,
                                value: value,
                            }});
                        }},
                        ondeleterow: function(worksheet, rows) {{
                            emitSpreadsheetEvent({{
                                type: 'row_delete',
                                widget_id: widgetId,
                                rows: rows,
                            }});
                        }},
                    }}],
                }});

                container.dataset.quantmsSpreadsheetWidget = widgetId;
                window.__quantmsSpreadsheetInstances[widgetId] = spreadsheet;
                return true;
            }}

            function waitForSpreadsheet() {{
                if (typeof window.jspreadsheet !== 'undefined' && typeof window.jSuites !== 'undefined') {{
                    initializeSpreadsheet();
                    return;
                }}

                window.setTimeout(waitForSpreadsheet, 100);
            }}

            waitForSpreadsheet();
        }})();
        """

        context.client.run_javascript(script)

    def _handle_spreadsheet_event(self, event_data) -> None:
        """Route JavaScript spreadsheet events to appropriate Python handlers."""
        if not isinstance(event_data, dict):
            return

        if event_data.get('widget_id') != self.widget_id:
            return

        event_type = event_data.get('type')
        if event_type == 'cell_edit':
            row = event_data.get('row')
            col = event_data.get('col')
            value = event_data.get('value')
            if row is not None and col is not None:
                self.handle_cell_edit(row, col, value)
        elif event_type == 'row_delete':
            rows = event_data.get('rows')
            if rows is not None:
                self.handle_row_delete(rows)
            else:
                row = event_data.get('row')
                if row is not None:
                    self.handle_row_delete(row)

    def handle_cell_edit(self, row_index: int, col_index: int, new_value: Any) -> None:
        """Handle a cell edit from the spreadsheet."""
        try:
            self.bridge.handle_cell_edit(row_index, col_index, new_value)
        except Exception as e:
            ui.notify(f"Error updating cell: {e}", type="negative")

    def handle_row_delete(self, row_index: Any) -> None:
        """Handle one or more row deletions from the spreadsheet."""
        try:
            if isinstance(row_index, list):
                for index in sorted((int(value) for value in row_index), reverse=True):
                    self.bridge.handle_row_delete(index)
            else:
                self.bridge.handle_row_delete(int(row_index))
            self.on_change()
        except Exception as e:
            ui.notify(f"Error deleting row: {e}", type="negative")

    def refresh(self) -> None:
        """Refresh the spreadsheet with current wizard state."""
        if getattr(context.client, 'has_socket_connection', False):
            self._initialize_spreadsheet()

    def append_row(self, file_path: str) -> None:
        """Append a new row to the spreadsheet."""
        try:
            self.bridge.handle_row_append(file_path)
            self.on_change()
        except Exception as e:
            ui.notify(f"Error adding file: {e}", type="negative")
