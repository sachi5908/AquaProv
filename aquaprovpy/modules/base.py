"""Shared workspace integration: project signals and serializable controls."""
from dataclasses import asdict
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QSignalBlocker
from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QLabel, QLineEdit, QPushButton, QSpinBox, QSizePolicy

from ..ui.workbench import Workbench
from ..ui.module_surface import ModuleSurfaceMixin
from ..ui.loading import loading_checkpoint, run_worker
from ..ui.auto_update import AutoUpdateMixin
from ..ui.plot_cache import PlotCacheMixin
from ..ui.color_button import ColorButton, ColorPalette
from ..plot_style import PlotStyle
from .registry import module_for
from .plot_profiles import PlotProfilesMixin, clear_dataset_assumptions


class ModuleWorkspace(PlotCacheMixin, AutoUpdateMixin, ModuleSurfaceMixin, PlotProfilesMixin, Workbench):
    data_changed = Signal(object, object)
    settings_changed = Signal()
    module_key = "groundwater"
    defer_figure_draw = True

    def __init__(self):
        self._restoring = True
        super().__init__()
        self.setWindowFlags(Qt.WindowType.Widget)
        self.setMinimumSize(0, 0)
        self.menuBar().hide()
        # The shell owns shortcuts so hidden modules cannot consume them.
        for menu in self.menuBar().actions():
            if menu.menu():
                for action in menu.menu().actions():
                    action.setShortcut("")
        module = module_for(self.module_key)
        self.findChild(QLabel, "appTitle").setText(module.title)
        self.findChild(QLabel, "subtitle").setText(module.description)
        self._restoring = False

    def configure_diagrams(self, names):
        with QSignalBlocker(self.diagram_combo):
            self.diagram_combo.clear()
            self.diagram_combo.addItems(names)
        self._analysis_controls_changed()

    def hide_locations(self):
        self.location_card.hide()
        self.preview_tabs.setTabVisible(self.preview_tabs.indexOf(self.map_page), False)

    def connect_settings(self):
        self.initialize_surface()
        self.initialize_plot_profiles()
        for widget in self.findChildren(QComboBox):
            loading_checkpoint()
            widget.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            widget.setMinimumContentsLength(10)
            widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            widget.currentIndexChanged.connect(self._setting_changed)
        for widget in self.findChildren(QLineEdit):
            widget.textEdited.connect(self._setting_changed)
        for widget in self.findChildren(QSpinBox) + self.findChildren(QDoubleSpinBox):
            widget.valueChanged.connect(self._setting_changed)
        for widget in self.findChildren(QCheckBox):
            if widget is not self.auto_update_check and not widget.property('styleControlAlias'):
                widget.toggled.connect(self._setting_changed)
        for widget in self.findChildren(ColorButton) + self.findChildren(ColorPalette):
            # A palette forwards changes from its own swatches. Style changes
            # have their own presentation-only update connection.
            if widget not in self.style_controls.values() and not isinstance(widget.parentWidget(), ColorPalette):
                widget.colorChanged.connect(self._setting_changed)
        self.variable_list.itemChanged.connect(self._setting_changed)
        for widget in self.style_controls.values():
            if isinstance(widget, QPushButton) and not isinstance(widget, ColorButton):
                widget.clicked.connect(self._setting_changed)

    def _setting_changed(self, *_, update_kind=None):
        if not self._restoring:
            self.settings_changed.emit()
            self._queue_auto_update(update_kind or self._auto_update_kind(self.sender()))

    def _accept_frame(self, frame):
        self._clear_plot_cache()
        self._updating_data = True
        try:
            super()._accept_frame(frame)
            self.populate_module_columns()
        finally:
            self._updating_data = False
        if not self._restoring:
            if hasattr(self, '_plot_profiles'):
                clear_dataset_assumptions({'plot_profiles': self._plot_profiles})
            self._project_source = None
            data = self.data
            self.data_changed.emit(run_worker(lambda: data.copy(deep=True)), {
                "path": str(self.source_path) if self.source_path else "",
                "sheet": self.sheet_combo.currentText() if self.excel_sheets else "",
                "ec_unit": self.ec_unit_combo.currentText(),
            })
            self._queue_auto_update()

    def populate_module_columns(self):
        pass

    def accept_project_data(self, frame, source):
        self._restoring = True
        try:
            self.source_path = Path(source["path"]) if source.get("path") else None
            # Saved data is embedded; restoring never reads a potentially moved source.
            self.excel_sheets = []
            self.sheet_combo.hide()
            self._accept_frame(frame)
            self.ec_unit_combo.setCurrentText(source.get("ec_unit", "uS/cm"))
            self._project_source = dict(source)
        finally:
            self._restoring = False

    def _capture_current_state(self):
        controls = {}
        for name, widget in vars(self).items():
            if name in ("sheet_combo", "folder_edit", "diagram_search", "figure_combo", "result_combo", "auto_update_check"):
                continue
            if isinstance(widget, QComboBox):
                controls[name] = widget.currentText()
            elif isinstance(widget, QLineEdit):
                controls[name] = widget.text()
            elif isinstance(widget, QCheckBox):
                controls[name] = widget.isChecked()
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                controls[name] = widget.value()
            elif isinstance(widget, (ColorButton, ColorPalette)):
                controls[name] = widget.text()
        state = {"controls": controls, "style": asdict(self.plot_style()), "missing_policy_version": 1,
                "variables": [self.variable_list.item(i).text() for i in range(self.variable_list.count())
                              if self.variable_list.item(i).checkState() == Qt.CheckState.Checked],
                "color": self.color_button.text()}
        return state

    def _restore_current_state(self, state):
        self._restoring = True
        try:
            # Older projects stored the former stop-on-blanks default. Adopt
            # complete samples once; later explicitly chosen policies persist.
            legacy_missing_policy = state.get('missing_policy_version', 0) < 1
            if legacy_missing_policy:
                with QSignalBlocker(self.missing_combo):
                    self.missing_combo.setCurrentIndex(self.missing_combo.findData('drop'))
            for name, value in state.get("controls", {}).items():
                if name == 'missing_combo' and legacy_missing_policy:
                    continue
                widget = getattr(self, name, None)
                if isinstance(widget, QComboBox) and isinstance(value, str):
                    if widget.findText(value) >= 0:
                        widget.setCurrentText(value)
                    elif name == 'map_background_combo':
                        # Retired/API-key providers in old projects use the
                        # working street map rather than a stale selection.
                        widget.setCurrentIndex(widget.findData('osm'))
                elif isinstance(widget, QLineEdit) and isinstance(value, str):
                    widget.setText(value)
                elif isinstance(widget, QCheckBox) and isinstance(value, bool):
                    widget.setChecked(value)
                elif isinstance(widget, (QSpinBox, QDoubleSpinBox)) and isinstance(value, (float, int)):
                    widget.setValue(value)
                elif isinstance(widget, (ColorButton, ColorPalette)) and isinstance(value, str):
                    widget.setText(value)
            if "style" in state:
                style = PlotStyle(**state["style"])
                style.validate()
                self._set_style(style)
            if "variables" in state:
                for index in range(self.variable_list.count()):
                    item = self.variable_list.item(index)
                    item.setCheckState(Qt.CheckState.Checked if item.text() in state["variables"] else Qt.CheckState.Unchecked)
            if isinstance(state.get("color"), str):
                from PySide6.QtGui import QColor
                color = QColor(state["color"])
                if color.isValid():
                    self.color_button.setText(state["color"])
            self._analysis_controls_changed()
        finally:
            self._restoring = False

    def show_result(self, result, title):
        self.analysis_result = result
        self._install_figures([result.figure], [title])
        self.generated_plot = ("analysis", title)
        result.metadata.update(source=self.source_path.as_posix() if self.source_path else None,
                               source_sheet=self._source_sheet(), figure_style=asdict(self.rendered_style))
        self.result_combo.addItems(list(result.tables))
        self.result_notes.setText("\n".join(result.warnings) or "Analysis complete. Export tables and methods alongside your figure.")
        self.tables_button.setEnabled(True)
        self.save_button.setEnabled(True)
        self.preview_tabs.setCurrentIndex(1)
        self.plot_details.setText(title + " · Interactive preview; numerical outputs in Results & methods")

    def _source_sheet(self):
        if self.excel_sheets:
            return self.sheet_combo.currentText()
        return (getattr(self, "_project_source", None) or {}).get("sheet") or None

    def generate_analysis(self):
        super().generate_analysis()
        if self.analysis_result is not None:
            self.analysis_result.metadata["source_sheet"] = self._source_sheet()

    def closeEvent(self, event):
        self._cancel_auto_update()
        self._clear_plot_cache()
        super().closeEvent(event)
