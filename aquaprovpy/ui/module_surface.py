"""Plot library, figure preview and settings panel for each module."""

from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QPushButton, QSizePolicy, QSplitter, QStatusBar, QVBoxLayout, QWidget)
from .plot_browser import PlotBrowser
from .icons import decorate_button
from .branding import brand_stylesheet
from .theme import COMBO_ARROW, SPIN_UP_ARROW
from .module_view_tools import ModuleViewTools
from .sidebar_tables import dock_sidebar_tables
from .color_button import ColorButton
from .legend_items import LegendItemsControl
from .settings_sections import organize_settings


class QuickTypography(QFrame):
    """Visible typography controls synchronized with the detailed Style tab."""
    def __init__(self, workspace):
        super().__init__()
        self.workspace = workspace
        self.setObjectName("quickTypography")
        self.setStyleSheet(brand_stylesheet("""
            QFrame#quickTypography { background: transparent; border: 0; }
            QComboBox, QDoubleSpinBox { font-family: 'Segoe UI'; font-size: 9pt; color: @ink@;
                background: @soft@; border: 1px solid @border@; border-radius: 5px; padding: 4px 6px; }
            QComboBox::drop-down { border: 0; width: 22px; }
            QComboBox::down-arrow { image: url("__COMBO_ARROW__"); width: 9px; height: 9px; }
            QDoubleSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 16px; border: 0; background: transparent; }
            QDoubleSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 16px; border: 0; background: transparent; }
            QDoubleSpinBox::up-arrow { image: url("__SPIN_UP__"); width: 8px; height: 8px; }
            QDoubleSpinBox::down-arrow { image: url("__COMBO_ARROW__"); width: 8px; height: 8px; }
            QPushButton { font-size: 9pt; color: @ink@; background: white;
                border: 1px solid @border@; border-radius: 5px; padding: 0; }
            QPushButton:hover, QPushButton:checked { background: @selected@; border-color: @cyan@; }
        """).replace('__COMBO_ARROW__', COMBO_ARROW).replace('__SPIN_UP__', SPIN_UP_ARROW))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        self.font = QComboBox()
        source = workspace.style_controls['font_family']
        self.font.addItems([source.itemText(i) for i in range(source.count())])
        self.font.setFixedSize(138, 34)
        self.font.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.font.setMinimumContentsLength(9)
        self.font.setAccessibleName("Current plot font family")
        self.font.setToolTip('Font family for the current plot')
        layout.addWidget(self.font)
        self.size = QDoubleSpinBox()
        self.size.setRange(4, 48)
        self.size.setDecimals(0)
        self.size.setSuffix(" pt")
        self.size.setFixedSize(66, 34)
        self.size.setAccessibleName('Current plot font size')
        self.size.setToolTip("Base font size; title, labels, ticks and legend scale with it")
        layout.addWidget(self.size)
        self.bold = QPushButton("B")
        self.italic = QPushButton("I")
        for control, tooltip in ((self.bold, "Bold plot text"), (self.italic, "Italic plot text")):
            control.setCheckable(True)
            control.setFixedSize(32, 34)
            control.setToolTip(tooltip)
            control.setAccessibleName(tooltip)
            layout.addWidget(control)
        self.bold.setStyleSheet('font-weight: bold;')
        self.italic.setStyleSheet('font-style: italic;')
        self.color = QPushButton()
        self.color.setFixedSize(34, 30)
        self.color.setAccessibleName('Plot text color')
        self.color.clicked.connect(self._color)
        layout.addWidget(self.color)
        self.more = decorate_button(QPushButton(), 'settings')
        self.more.setFixedSize(32, 34)
        self.more.setAccessibleName('All style controls')
        self.more.setToolTip('All style controls: labels, fonts, grid, legend and export')
        self.more.clicked.connect(self._show_style)
        layout.addWidget(self.more)
        self.font.currentTextChanged.connect(lambda value: self._set('font_family', value))
        self.size.valueChanged.connect(self._size)
        self.bold.toggled.connect(lambda value: self._set('font_weight', 'bold' if value else 'normal'))
        self.italic.toggled.connect(lambda value: self._set('font_style', 'italic' if value else 'normal'))
        self.sync()

    def sync(self):
        # An unrelated text field can be temporarily incomplete while typing
        # (for example, a pair of limits). Sync only the bounded font controls;
        # full style validation belongs to the debounced render or Apply action.
        controls = self.workspace.style_controls
        for widget, value in ((self.font, controls['font_family'].currentText()), (self.size, controls['font_size'].value()),
                              (self.bold, controls['font_weight'].currentText() == 'bold'), (self.italic, controls['font_style'].currentText() == 'italic')):
            with QSignalBlocker(widget):
                if isinstance(widget, QComboBox):
                    if widget.findText(value) < 0:
                        widget.addItem(value)
                    widget.setCurrentText(value)
                elif isinstance(widget, QDoubleSpinBox):
                    widget.setValue(value)
                else:
                    widget.setChecked(value)
        text_color = controls['text_color'].text()
        self.color.setStyleSheet(f"QPushButton {{ background: {text_color}; border: 1px solid #b9cbd6; border-radius: 5px; }}"
                                "QPushButton:hover, QPushButton:focus { border: 2px solid #0095bf; }")
        self.color.setToolTip(f'Plot text color: {text_color}')

    def _show_style(self):
        self.workspace.settings_toggle.setChecked(True)
        self.workspace.control_tabs.setCurrentIndex(2)

    def _set(self, name, value):
        control = self.workspace.style_controls[name]
        control.setCurrentText(value)

    def _size(self, value):
        controls = self.workspace.style_controls
        ratio = value / controls['font_size'].value()
        for key in ('title_size', 'label_size', 'tick_size', 'legend_size'):
            controls[key].setValue(max(4, min(48, controls[key].value() * ratio)))
        controls['font_size'].setValue(value)

    def _color(self):
        self.workspace._pick_style_color(self.workspace.style_controls['text_color'])


class ModuleSurfaceMixin:
    def _build_ui(self):
        central = QWidget()
        page = QVBoxLayout(central)
        page.setContentsMargins(10, 8, 10, 8)
        page.setSpacing(8)
        self.active_plot_title = QLabel("Select a plot")
        self.active_plot_title.setObjectName("activePlotTitle")
        self.active_plot_title.setTextFormat(Qt.TextFormat.PlainText)
        self.active_plot_title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.active_plot_title.setMinimumWidth(110)
        # Keep public branding labels for standalone integrations.
        title = QLabel("AquaProv")
        title.setObjectName("appTitle")
        title.hide()
        title.setParent(central)
        subtitle = QLabel()
        subtitle.setObjectName("subtitle")
        subtitle.hide()
        subtitle.setParent(central)
        # One fallback toolbar for modules used directly. The shell adopts its
        # actual controls and hides this dock while the module is embedded.
        self.typography_dock = QWidget()
        self.typography_layout = QHBoxLayout(self.typography_dock)
        self.typography_layout.setContentsMargins(0, 0, 0, 0)
        page.addWidget(self.typography_dock)
        self.module_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.module_splitter.setChildrenCollapsible(False)
        self.module_splitter.setHandleWidth(6)
        self.plot_browser = PlotBrowser()
        self.inspector = self._build_sidebar()
        self.control_tabs.setTabText(1, "Settings")
        self.inspector.setMinimumWidth(300)
        self.inspector.setMaximumWidth(440)
        studio = QWidget()
        studio.setMinimumWidth(280)
        layout = QVBoxLayout(studio)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.quick_typography = QuickTypography(self)
        self.typography_layout.addWidget(self.active_plot_title, 1)
        self.typography_layout.addWidget(self.quick_typography)
        layout.addWidget(self._build_workspace(), 1)
        self.typography_layout.addWidget(self.view_tools)
        self.module_splitter.addWidget(self.plot_browser)
        self.module_splitter.addWidget(studio)
        self.module_splitter.addWidget(self.inspector)
        self.module_splitter.setSizes([238, 810, 360])
        self.module_splitter.setStretchFactor(1, 1)
        self.library_toggle.toggled.connect(self.plot_browser.setVisible)
        self.settings_toggle.toggled.connect(self.inspector.setVisible)
        page.addWidget(self.module_splitter, 1)
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self.status = self.statusBar()
        self.status.showMessage("Choose a plot from the library; import data to generate it.")

    def _build_workspace_tools(self, layout):
        self.view_tools = ModuleViewTools(self)

    def _build_workspace(self):
        panel = super()._build_workspace()
        dock_sidebar_tables(self)
        # Retain the shared renderer's page indices for automatic figure/map
        # routing. Modules expose only the active preview, with no center tabs.
        self.preview_tabs.setTabEnabled(0, False)
        self.preview_tabs.setTabEnabled(3, False)
        self.preview_tabs.tabBar().hide()
        self.preview_tabs.setCurrentIndex(1)
        for index in (1, 2):
            self.preview_tabs.widget(index).layout().setContentsMargins(0, 0, 0, 0)
        return panel

    def initialize_surface(self):
        # Plot navigation replaces the long method drop-down, leaving its unit control.
        self.diagram_search.hide()
        self.diagram_combo.parentWidget().hide()
        for name in ('spatial_method_combo', 'three_d_mode_combo'):
            if hasattr(self, name):
                getattr(self, name).parentWidget().hide()
        self.plot_information, information = self._card("Plot settings")
        self.plot_description = QLabel()
        self.plot_description.setWordWrap(True)
        self.plot_description.setObjectName('muted')
        information.addWidget(self.plot_description)
        # Keep title visibility beside the manual title in every module.
        information.addWidget(self.style_controls['title_visible'])
        # Use the existing, persisted style control directly in Settings so a
        # plot title can be edited without opening the typography toolbox.
        information.addWidget(self.style_controls['title'].parentWidget())
        self.title_settings = QWidget()
        title_settings_layout = QGridLayout(self.title_settings)
        title_settings_layout.setContentsMargins(0, 0, 0, 0)
        title_settings_layout.setColumnStretch(0, 1)
        title_settings_layout.setColumnStretch(1, 1)
        for index, key in enumerate(('title_size', 'title_weight', 'title_style', 'title_position')):
            title_settings_layout.addWidget(self.style_controls[key].parentWidget(), index // 2, index % 2)
        information.addWidget(self.title_settings)
        reset = QPushButton("Reset this plot's settings")
        decorate_button(reset, 'reset')
        reset.clicked.connect(self.reset_current_plot)
        information.addWidget(reset)
        self.control_tabs.widget(1).widget().layout().insertWidget(0, self.plot_information)
        settings = self.control_tabs.widget(1).widget().layout()
        settings.insertWidget(max(0, settings.count() - 1), self.appearance_card)
        self.style_controls['z_label'].parentWidget().setVisible(self.module_key == 'three_d')
        self.initialize_auto_update()
        organize_settings(self.control_tabs.widget(1).widget())
        for key, control in self.style_controls.items():
            if isinstance(control, LegendItemsControl):
                continue  # The checklist connects its presentation signal when built.
            elif isinstance(control, ColorButton):
                control.colorChanged.connect(lambda _, name=key: self._style_control_edited(name))
            elif isinstance(control, QComboBox):
                control.currentTextChanged.connect(lambda _, name=key: self._style_control_edited(name))
            elif isinstance(control, QDoubleSpinBox):
                control.valueChanged.connect(lambda _, name=key: self._style_control_edited(name))
            elif hasattr(control, 'toggled') and control.isCheckable():
                control.toggled.connect(lambda _, name=key: self._style_control_edited(name))
            elif isinstance(control, QPushButton):
                control.clicked.connect(lambda _, name=key: self._style_control_edited(name))
            else:
                signal = control.textChanged if key == 'title' else control.textEdited
                signal.connect(lambda _, name=key: self._style_control_edited(name))
        self.control_tabs.setCurrentIndex(0)

    def refresh_contextual_controls(self):
        """Expose only sample controls used by the selected renderer."""
        if self.module_key in ('groundwater', 'statistics'):
            from ..core.catalog import DIAGRAMS, STATISTICAL_VIEWS, EXPLORATORY_VIEWS
            name = self.diagram_combo.currentText()
            engine = DIAGRAMS[name][0]
            self.chart_card.setVisible(engine not in ('multivariate', 'exploration'))
            measured_series = EXPLORATORY_VIEWS.get(name) == 'measured_series'
            uses_samples = engine not in ('multivariate', 'exploration') or STATISTICAL_VIEWS.get(name) == 'pca_scores' or measured_series
            self.appearance_card.setVisible(uses_samples)
            # Series fills and symbols have per-series controls. The shared
            # size fallback and opacity still apply to the measured points.
            for widget in (self.label_combo, self.color_combo, self.marker_combo):
                widget.parentWidget().setVisible(not measured_series)
            for widget in (self.single_color_label, self.color_button):
                widget.setVisible(not measured_series)
        elif self.module_key == 'three_d':
            self.chart_card.hide()
            self.appearance_card.setVisible(self._active_plot != 'pca_loadings')
            for control in (self.single_color_label, self.color_button):
                control.setVisible(self._active_plot != 'xyz_scatter')

    def _style_control_edited(self, key):
        if self._restoring or getattr(self, '_switching_plot', False):
            return
        # Choosing a scale is an explicit request to display it, including on
        # imported figures saved with the bar hidden. Restoring a project or a
        # preset retains its saved visibility; a later Hide still takes effect.
        if ((key == 'cmap' and self.style_controls[key].currentText() != 'Original')
                or (key == 'normalize_cmap' and self.style_controls[key].isChecked())):
            self.style_controls['colorbar_visible'].setChecked(True)
        if key == 'title' and self.module_key == 'three_d' and self.style_controls['title'].text().strip():
            self.style_controls['title_visible'].setChecked(True)
        typography = ('font_size', 'label_size', 'tick_size', 'legend_size', 'font_weight', 'font_style', 'text_color')
        if key in typography and self.style_controls['font_family'].currentText() == 'Original':
            self.style_controls['font_family'].setCurrentText('DejaVu Sans')
        self.quick_typography.sync()
        self._setting_changed(update_kind='style')

    def _set_style(self, style):
        restoring = self._restoring
        self._restoring = True
        try:
            super()._set_style(style)
            if hasattr(self, 'quick_typography'):
                self.quick_typography.sync()
        finally:
            self._restoring = restoring
