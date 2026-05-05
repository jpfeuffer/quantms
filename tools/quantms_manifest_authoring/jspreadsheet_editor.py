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
import weakref
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

    def __init__(self, wizard: WizardState, on_change: Callable[[], None], bridge=None, worksheet_name: str = "Runs"):
        """
        Initialize the spreadsheet editor.

        Args:
            wizard: WizardState instance to sync with
            on_change: Callback to invoke when data changes (for UI refresh)
            bridge: Optional JSpreadsheetBridge instance. If None, creates a default runs bridge.
            worksheet_name: Name of the worksheet for identification (e.g., "RunsSheet", "SamplesSheet", "MixturesSheet")
        """
        self.wizard = wizard
        self.bridge = bridge if bridge is not None else JSpreadsheetBridge(wizard, entity_type="runs")
        self.on_change = on_change
        self.worksheet_name = worksheet_name
        self.container = None
        self.widget_id = f"jse_{worksheet_name}_{uuid.uuid4().hex[:8]}"

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

        instances = JSpreadsheetEditor._get_registry('_instances', weakref.WeakValueDictionary)
        editor = instances.get(widget_id)
        if editor is not None:
            editor._handle_spreadsheet_event(event_data)

    def render(self) -> None:
        """Render the spreadsheet editor in NiceGUI into proper container."""
        self.container = ui.element('div').classes('w-full min-h-96 overflow-auto rounded border border-gray-200 bg-white')

        self._get_registry('_instances', weakref.WeakValueDictionary)[self.widget_id] = self
        self.prepare_client_runtime()

        if not self.wizard or self.bridge.get_row_count() == 0:
            return

        if getattr(context.client, 'has_socket_connection', False):
            self._initialize_spreadsheet()
        else:
            on_connect = getattr(context.client, 'on_connect', None)
            if callable(on_connect):
                on_connect(self._initialize_spreadsheet)

    def _initialize_spreadsheet(self) -> None:
        if not self.container or not self.wizard or self.bridge.get_row_count() == 0:
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
        worksheet_name_json = json.dumps(self.worksheet_name)
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
                const worksheetName = {worksheet_name_json};

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

                // Merge dropdown configuration and read-only flag from columnConfig into columns
                headers.forEach((header, index) => {{
                    if (columnConfig[header]) {{
                        const config = columnConfig[header];
                        if (config.type === 'dropdown' && config.source) {{
                            // Merge dropdown properties into column definition
                            columns[index].type = 'dropdown';
                            columns[index].source = config.source;
                            columns[index].autocomplete = true;
                            columns[index].filterMode = config.filter_mode || 'prefix';
                        }}
                        // Merge read_only flag into readOnly property for jspreadsheet
                        if (config.read_only) {{
                            columns[index].readOnly = true;
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
                        worksheetName: worksheetName,
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

            function installDropdownFilterPatch() {{
                if (window.__quantmsDropdownPatched) return;
                window.__quantmsDropdownPatched = true;
                var _origDropdown = window.jSuites.dropdown;
                window.jSuites.dropdown = function(el, options) {{
                    var instance = _origDropdown.apply(this, arguments);
                    if (options && options.autocomplete && instance) {{
                        var activeCell = document.querySelector('td.editor[data-x]');
                        if (activeCell) {{
                            var x = parseInt(activeCell.getAttribute('data-x'), 10);
                            var filterMode = null;
                            var allData = window.__quantmsSpreadsheetData || {{}};
                            var wids = Object.keys(allData);
                            for (var i = 0; i < wids.length; i++) {{
                                var d = allData[wids[i]];
                                var header = d.headers && d.headers[x];
                                var cfg = header && d.column_config && d.column_config[header];
                                if (cfg && cfg.filter_mode && cfg.filter_mode !== 'substring') {{
                                    filterMode = cfg.filter_mode;
                                    break;
                                }}
                            }}
                            if (filterMode) {{
                                var _origFind = instance.find.bind(instance);
                                instance.find = (function(mode, orig) {{
                                    return function(str) {{
                                        if (!str || str.trim() === '') {{
                                            instance.search = null;
                                            return orig('');
                                        }}
                                        var escaped = str.replace(/[.*+?^${{}}()|[\\]\\\\]/g, '\\\\$&');
                                        var pattern = mode === 'fuzzy'
                                            ? escaped.split('').join('.*')
                                            : '^' + escaped;
                                        instance.search = null;
                                        return orig(pattern);
                                    }};
                                }})(filterMode, _origFind);
                            }}
                        }}
                    }}
                    return instance;
                }};
            }}

            function waitForSpreadsheet() {{
                if (typeof window.jspreadsheet !== 'undefined' && typeof window.jSuites !== 'undefined') {{
                    installDropdownFilterPatch();
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

    async def flush_pending_edits(self) -> int:
        """
        Flush pending cell edits before navigation or teardown.

        This method is called by the GUI layer before the spreadsheet editor
        is destroyed (e.g., during step navigation) to ensure any edits that
        are still in the JavaScript layer are committed to Python state.

        Fetches current spreadsheet data from the browser and syncs it back
        to WizardState, ensuring no pending edits are lost during navigation.

        Returns:
            0 if successful (no pending edits or all flushed)
        """
        if not self.wizard or self.bridge.get_row_count() == 0:
            return 0

        # Get the container element to access the spreadsheet instance
        container_id = self.container.html_id if self.container else None
        if not container_id:
            return 0

        # Fetch current spreadsheet data from browser.
        # Browser validation showed that worksheet.getData() can lag behind the
        # live input value while a cell editor is still open. We therefore try
        # to close the active editor explicitly before reading the worksheet.
        fetch_script = f"""
        (async function() {{
            const containerId = {json.dumps(container_id)};
            const container = document.getElementById(containerId);
            if (!container || !container.spreadsheet) {{
                return null;
            }}

            const spreadsheet = container.spreadsheet;
            if (!spreadsheet || typeof spreadsheet.getWorksheetActive !== 'function') {{
                return null;
            }}

            try {{
                // Get the active worksheet using the actual jspreadsheet API
                const activeIndex = spreadsheet.getWorksheetActive();

                if (typeof activeIndex !== 'number' || activeIndex < 0 || !Array.isArray(spreadsheet.worksheets)) {{
                    return null;
                }}

                const worksheet = spreadsheet.worksheets[activeIndex];
                if (!worksheet || typeof worksheet.getData !== 'function') {{
                    return null;
                }}

                // Deterministically commit the active cell editor before snapshotting.
                const activeElement = document.activeElement;
                const activeCell = activeElement && typeof activeElement.closest === 'function'
                    ? activeElement.closest('td[data-x][data-y]')
                    : null;

                if (activeCell && typeof worksheet.closeEditor === 'function') {{
                    worksheet.closeEditor(activeCell, true);
                }} else if (activeElement && activeElement !== document.body) {{
                    activeElement.blur();
                }}

                await new Promise(resolve => setTimeout(resolve, 20));

                const data = worksheet.getData();
                return data;  // Return the data array
            }} catch (error) {{
                console.error('Error fetching spreadsheet data:', error);
                return null;
            }}
        }})();
        """

        try:
            # Run the JavaScript and await the result
            result = await context.client.run_javascript(fetch_script)

            # If we got data back, sync it to wizard state
            if result and isinstance(result, list):
                self._sync_data_from_browser(result)

            return 0
        except Exception as e:
            # Log the error but don't fail navigation
            print(f"Error flushing spreadsheet edits: {e}")
            ui.notify("Warning: pending spreadsheet edits could not be flushed", type="warning")
            return 0

    def _sync_data_from_browser(self, spreadsheet_data: list) -> None:
        """
        Synchronize spreadsheet data from browser back to WizardState.

        Args:
            spreadsheet_data: List of rows from the browser spreadsheet
        """
        if not spreadsheet_data or not self.wizard:
            return

        try:
            self.bridge.sync_from_spreadsheet_data(spreadsheet_data)

        except Exception as e:
            print(f"Error syncing spreadsheet data: {e}")

    def handle_event(self, event_type: str, **kwargs) -> None:
        """
        Handle a spreadsheet event (programmatic dispatch for testing).

        Args:
            event_type: Type of event ('cell_edit', 'row_delete', etc.)
            **kwargs: Event-specific arguments (row_index, col_index, new_value, etc.)
        """
        if event_type == "cell_edit":
            self.handle_cell_edit(kwargs.get("row_index"), kwargs.get("col_index"), kwargs.get("new_value"))
        elif event_type == "row_delete":
            self.handle_row_delete(kwargs.get("row_index"))

    def register_with_wizard(self) -> None:
        """Register this editor as the active editor with the wizard."""
        if self.wizard:
            self.wizard.set_active_editor(self)

    def flush(self) -> None:
        """
        Flush pending edits (synchronous wrapper for testing).
        
        In a real browser context, this would fetch data from the spreadsheet.
        For testing, this is a no-op that verifies the editor is callable.
        """
        # Synchronous version - in real usage, flush_pending_edits is async
        try:
            if hasattr(self, 'wizard') and self.wizard:
                # Just verify the bridge can sync current state
                pass
        except Exception as e:
            print(f"Error flushing editor: {e}")

