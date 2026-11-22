"""Shared data, figure studio, analysis and export controls."""
from __future__ import annotations
import importlib
import re
import sys
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd
from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QSpinBox,
    QStatusBar,
    QTabWidget,
    QAbstractItemView,
    QVBoxLayout,
    QWidget,
)

from ..workspace import WorkspaceMixin
from ..plot_style import PlotStyle
from .color_button import ColorButton


from ..core.catalog import APP_NAME, APP_TITLE, DIAGRAMS, DIAGRAM_GROUPS, STATISTICAL_VIEWS, EXPLORATORY_VIEWS, NUMERIC_COLUMNS, MARKERS
from ..core.data import normalize_headers, read_csv, read_excel
from ..modules.maps.locations_ui import LocationWorkspaceMixin
from .theme import apply_workbench_style
from .colour_scale import ColourScaleCombo
from .icons import decorate_button
from .artwork import BrandLogo, app_icon
from .loading import BusyOverlay, loading_checkpoint, plot_loading, run_worker
from ..core.progress import progress_stage, report_progress, check_cancelled, JobCancelled
from .plot_data import PlotDataMixin
from .data_table import DataFrameTable
from ..core.results_export import RESULT_FORMATS, FORMAT_NAMES, result_export_paths, validate_export_name
from ..core.export_files import write_export_files
from .export_feedback import (confirm_export_overwrite, dismiss_export_success,
                              show_export_error, show_export_success)

class Workbench(PlotDataMixin, LocationWorkspaceMixin, WorkspaceMixin, QMainWindow):
    def __init__(self):
        super().__init__()
        # Desktop plots are prepared offscreen and then attached to Qt canvases.
        # Leave an embedding application's preselected pyplot backend alone.
        if 'matplotlib.pyplot' not in sys.modules:
            import matplotlib
            matplotlib.use('Agg')
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(app_icon())
        self.resize(1420, 900)
        self.setMinimumSize(1100, 720)
        self.data = None
        self.map_data = None
        self.source_path = None
        self.excel_sheets = []
        self.preview_pixmap = None
        self.preview_tempdir = None
        self.generated_plot = None
        self.map_preview_pixmap = None
        self.analysis_result = None
        self.analysis_canvas = None
        self.analysis_scroll_area = None
        self.analysis_toolbar = None
        self.figure_navigation = None
        self.plot_figures = []
        self.figure_is_map = False
        self.map_basemap = None
        self.rendered_style = PlotStyle()
        self._build_ui()
        report_progress(65, 'Applying workspace appearance')
        loading_checkpoint()
        apply_workbench_style(self)
        loading_checkpoint()
        self._build_menus()
        report_progress(80, 'Connecting workspace controls')
        self.diagram_combo.currentTextChanged.connect(self._analysis_controls_changed)
        self._analysis_controls_changed()
        self._update_generate_button(self.preview_tabs.currentIndex())

    def _build_ui(self):
        central = QWidget()
        page = QVBoxLayout(central)
        page.setContentsMargins(16, 12, 16, 12)
        page.setSpacing(18)

        header = QHBoxLayout()
        brand = QVBoxLayout()
        title = QLabel("Aqua<span style='color:#24b8ae'>Prov</span>")
        title.setObjectName("appTitle")
        title.setTextFormat(Qt.TextFormat.RichText)
        subtitle = QLabel("Water chemistry · irrigation · multivariate analysis · auditable results")
        subtitle.setObjectName("subtitle")
        title.setParent(central)
        title.hide()
        brand.addWidget(BrandLogo(180, 72))
        brand.addWidget(subtitle)
        header.addLayout(brand)
        header.addStretch(1)
        self.file_badge = QLabel("NO DATA LOADED")
        self.file_badge.setObjectName("fileBadge")
        header.addWidget(self.file_badge, alignment=Qt.AlignmentFlag.AlignVCenter)
        page.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(12)
        splitter.addWidget(self._build_sidebar())
        splitter.addWidget(self._build_workspace())
        splitter.setSizes([370, 1000])
        page.addWidget(splitter, 1)

        self.setCentralWidget(central)
        status = QStatusBar()
        status.showMessage("Import a CSV or Excel workbook to get started.")
        self.setStatusBar(status)
        self.status = status

    def _card(self, title, subtitle=None):
        loading_checkpoint()
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 17)
        layout.setSpacing(11)
        heading = QLabel(title)
        heading.setObjectName("cardTitle")
        layout.addWidget(heading)
        if subtitle:
            note = QLabel(subtitle)
            note.setObjectName("muted")
            note.setWordWrap(True)
            layout.addWidget(note)
        return card, layout

    def _build_sidebar(self):
        scroll = QScrollArea()
        scroll.setObjectName("sidebarScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("sidebarContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 6, 0)
        layout.setSpacing(14)

        data_card, data_layout = self._card("Dataset", "Load a water analysis table. Headers are checked and familiar lab names are mapped automatically.")
        self.import_button = QPushButton("＋   Import CSV or Excel")
        self.import_button.setText('Import CSV or Excel')
        decorate_button(self.import_button, 'import')
        self.import_button.setObjectName("secondaryButton")
        self.import_button.clicked.connect(self.load_data)
        data_layout.addWidget(self.import_button)
        self.sheet_combo = QComboBox()
        self.sheet_combo.setVisible(False)
        self.sheet_combo.currentTextChanged.connect(self.load_selected_sheet)
        data_layout.addWidget(self.sheet_combo)
        self.dataset_info = QLabel("No file selected")
        self.dataset_info.setObjectName("muted")
        self.dataset_info.setWordWrap(True)
        data_layout.addWidget(self.dataset_info)
        layout.addWidget(data_card)

        chart_card, chart_layout = self._card("Diagram & method")
        self.chart_card = chart_card
        self.diagram_search = QLineEdit()
        self.diagram_search.setPlaceholderText('Search diagrams and analyses…')
        chart_layout.addWidget(self.diagram_search)
        self.diagram_combo = QComboBox()
        self.diagram_combo.addItems(DIAGRAMS.keys())
        self.diagram_search.textChanged.connect(self._filter_diagrams)
        self._add_field(chart_layout, "Diagram type", self.diagram_combo)
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(("mg/L", "meq/L"))
        self._add_field(chart_layout, "Concentration unit", self.unit_combo)
        layout.addWidget(chart_card)

        self.analysis_card, analysis_layout = self._card(
            "Analysis settings", "Choose measurements deliberately. IDs, coordinates and styling are not statistical variables.")
        self.ec_unit_combo = QComboBox()
        self.ec_unit_combo.addItems(("uS/cm", "mS/cm", "dS/m"))
        self._add_field(analysis_layout, "Measured EC unit (at 25 °C)", self.ec_unit_combo)
        self.variable_list = QListWidget()
        self.variable_list.setMinimumHeight(170)
        self.variable_list.itemChanged.connect(self._limit_scatter_pair_selection)
        self._add_field(analysis_layout, "Measurement variables (checked = included)", self.variable_list)
        self.scatter_pair_check = QCheckBox("Generate a single two-variable scatter plot")
        self.scatter_pair_check.setToolTip(
            "For Scatter matrix, check exactly two variables. The first checked variable in the list is X.")
        self.scatter_pair_check.toggled.connect(self._scatter_pair_toggled)
        analysis_layout.addWidget(self.scatter_pair_check)
        self.missing_combo = QComboBox()
        self.missing_combo.addItem("Stop on missing measurements", "raise")
        self.missing_combo.addItem("Exclude incomplete rows (reported)", "drop")
        self.missing_combo.setCurrentIndex(1)
        self._add_field(analysis_layout, "Missing measurements · statistics only", self.missing_combo)
        self.constant_combo = QComboBox()
        self.constant_combo.addItem("Stop on constant variables", "raise")
        self.constant_combo.addItem("Exclude constant variables (reported)", "drop")
        self._add_field(analysis_layout, "Constant variables", self.constant_combo)
        self.scale_check = QCheckBox("Standardize PCA / HCA (sample SD)")
        self.scale_check.setChecked(True)
        analysis_layout.addWidget(self.scale_check)
        self.component_spin = QSpinBox()
        self.component_spin.setRange(1, 2147483647)
        self.component_spin.setValue(3)
        self._add_field(analysis_layout, "PCA retained components", self.component_spin)
        self.rotation_combo = QComboBox()
        self.rotation_combo.addItems(("none", "varimax"))
        self._add_field(analysis_layout, "PCA rotation (Kaiser-normalized Varimax)", self.rotation_combo)
        self.cluster_spin = QSpinBox()
        self.cluster_spin.setRange(1, 2147483647)
        self.cluster_spin.setValue(3)
        self._add_field(analysis_layout, "Ward cluster count", self.cluster_spin)
        self.significance_combo = QComboBox()
        self.significance_combo.addItem("Raw two-sided p-values", "raw")
        self.significance_combo.addItem("Benjamini–Hochberg FDR q-values", "fdr")
        self._add_field(analysis_layout, "Correlation significance", self.significance_combo)
        self.correlation_annotate_check = QCheckBox('Show correlation coefficients and significance')
        self.correlation_annotate_check.setChecked(True)
        analysis_layout.addWidget(self.correlation_annotate_check)
        self.analysis_note = QLabel("No automatic log transform, imputation or outlier removal.")
        self.analysis_note.setWordWrap(True)
        analysis_layout.addWidget(self.analysis_note)
        layout.addWidget(self.analysis_card)

        style_card, style_layout = self._card("Sample appearance", "Color, grouping and symbols require Generate. Some legacy diagrams use fixed scientific colors and shapes.")
        self.label_combo = QComboBox()
        self.label_combo.addItem("(single group)")
        self._add_field(style_layout, "Group samples by", self.label_combo)
        self.color_combo = QComboBox()
        self.color_combo.addItem("(single color)")
        self._add_field(style_layout, "Color by numeric column", self.color_combo)
        color_row = QHBoxLayout()
        color_label = QLabel("Single color")
        self.single_color_label = color_label
        color_label.setObjectName("fieldLabel")
        color_row.addWidget(color_label)
        color_row.addStretch(1)
        self.color_button = ColorButton("#2878A5")
        self.color_button.setObjectName("colorButton")
        self.color_button.setAccessibleName('Choose sample colour')
        color_row.addWidget(self.color_button)
        style_layout.addLayout(color_row)
        row = QHBoxLayout()
        self.marker_combo = QComboBox()
        self.marker_combo.addItems(MARKERS)
        self._add_field(row, "Marker", self.marker_combo, stretch=1)
        self.size_spin = QDoubleSpinBox()
        self.size_spin.setRange(1, 1000)
        self.size_spin.setValue(36)
        self.size_spin.setDecimals(2)
        self._add_field(row, "Size", self.size_spin, stretch=1)
        style_layout.addLayout(row)
        self.alpha_spin = QDoubleSpinBox()
        self.alpha_spin.setRange(0.05, 1.0)
        self.alpha_spin.setSingleStep(0.05)
        self.alpha_spin.setValue(0.8)
        self._add_field(style_layout, "Opacity", self.alpha_spin)
        layout.addWidget(style_card)

        export_card, export_layout = self._card("Figure export")
        map_card, map_layout = self._card("Sample locations", "Plot X/Y on a real map. Select the source coordinate system; it cannot be inferred from X/Y alone.")
        self.location_card = map_card
        self.map_background_combo = QComboBox()
        from ..basemaps import BASEMAPS
        for key, provider in BASEMAPS.items():
            self.map_background_combo.addItem(provider['title'], key)
        self._add_field(map_layout, "Map background", self.map_background_combo)
        from ..locations import CRS_CHOICES
        self.map_crs_combo = QComboBox()
        self.map_crs_combo.addItem("(select coordinate system)", None)
        for title, code in CRS_CHOICES.items():
            self.map_crs_combo.addItem(title, code)
        self._add_field(map_layout, "Source coordinate system", self.map_crs_combo)
        self.map_zone_spin = QSpinBox()
        self.map_zone_spin.setRange(0, 60)
        self.map_zone_spin.setSpecialValueText("Select zone")
        self._add_field(map_layout, "UTM zone (1–60)", self.map_zone_spin)
        self.map_hemisphere_combo = QComboBox()
        self.map_hemisphere_combo.addItem("(select hemisphere)", None)
        self.map_hemisphere_combo.addItem("Northern hemisphere", "N")
        self.map_hemisphere_combo.addItem("Southern hemisphere", "S")
        self._add_field(map_layout, "UTM hemisphere", self.map_hemisphere_combo)
        self.map_crs_combo.currentIndexChanged.connect(self._map_controls_changed)
        self.map_background_combo.currentIndexChanged.connect(self._map_controls_changed)
        self._map_controls_changed()
        self.map_x_combo = QComboBox()
        self.map_x_combo.addItem("(select X coordinate)")
        self._add_field(map_layout, "X = longitude / easting", self.map_x_combo)
        self.map_y_combo = QComboBox()
        self.map_y_combo.addItem("(select Y coordinate)")
        self._add_field(map_layout, "Y = latitude / northing", self.map_y_combo)
        self.map_value_combo = QComboBox()
        self.map_value_combo.addItem("(single color)")
        self._add_field(map_layout, "Color points by numeric value", self.map_value_combo)
        self.map_label_combo = QComboBox()
        self.map_label_combo.addItem("(no point labels)")
        self._add_field(map_layout, "Label points by", self.map_label_combo)
        note = QLabel('Online basemaps need internet. Only visible tiles are requested; measurements stay local. Choose the source CRS to align locations and boundaries. Plain coordinates work offline.')
        note.setWordWrap(True)
        note.setObjectName('muted')
        map_layout.addWidget(note)
        map_button = QPushButton('Show sample locations')
        map_button.setObjectName('secondaryButton')
        map_button.clicked.connect(lambda: self.preview_tabs.setCurrentWidget(self.map_page))
        map_layout.addWidget(map_button)
        layout.addWidget(map_card)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText('Set automatically when you generate')
        self.name_edit.setToolTip('Generate sets this to the plot type. You can edit it before exporting.')
        self._add_field(export_layout, "File name", self.name_edit)
        folder_row = QHBoxLayout()
        self.folder_edit = QLineEdit(str(Path.cwd()))
        self.folder_edit.setPlaceholderText("Choose output folder")
        folder_button = QPushButton("Browse")
        folder_button.setObjectName("flatButton")
        folder_button.clicked.connect(self.choose_folder)
        folder_row.addWidget(self.folder_edit, 1)
        folder_row.addWidget(folder_button)
        self._add_field(export_layout, "Save to", folder_row)
        self.format_combo = QComboBox()
        self.format_combo.addItems(("png", "pdf", "svg", "tiff", "jpg"))
        self._add_field(export_layout, "File format", self.format_combo)
        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(72, 1200)
        self.dpi_spin.setSingleStep(50)
        self.dpi_spin.setValue(300)
        self._add_field(export_layout, "Image resolution (DPI)", self.dpi_spin)
        self.generate_button = QPushButton("Preview diagram")
        decorate_button(self.generate_button, 'generate')
        self.generate_button.setObjectName("primaryButton")
        self.generate_button.clicked.connect(self.generate)
        self.save_button = QPushButton()
        decorate_button(self.save_button, 'export')
        self.save_button.setObjectName("secondaryButton")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save_image)
        self.format_combo.currentTextChanged.connect(self._update_figure_export_label)
        self._update_figure_export_label()
        export_layout.addWidget(self.save_button)
        layout.addWidget(export_card)
        layout.addStretch(1)

        panel = self._organize_sidebar((data_card, chart_card, self.analysis_card, style_card, map_card, export_card))
        content.deleteLater()
        scroll.deleteLater()
        return panel

    def _build_workspace(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        self._build_workspace_tools(layout)

        self.preview_tabs = QTabWidget()
        self.preview_tabs.setObjectName("previewTabs")
        self.preview_tabs.setDocumentMode(True)
        self.preview_tabs.tabBar().setExpanding(False)
        self.preview_tabs.tabBar().setDrawBase(False)
        self.preview_tabs.setUsesScrollButtons(True)

        data_page = QWidget()
        data_page_layout = QVBoxLayout(data_page)
        data_page_layout.setContentsMargins(0, 12, 0, 0)
        data_card, data_layout = self._card("Data preview", "First rows from the imported worksheet")
        self.table = DataFrameTable()
        self.table.setObjectName("dataTable")
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMinimumHeight(225)
        data_layout.addWidget(self.table)
        self.table_info = QLabel("Import a dataset to preview its columns and sample values.")
        self.table_info.setObjectName("muted")
        data_layout.addWidget(self.table_info)
        data_page_layout.addWidget(data_card)
        self.preview_tabs.addTab(data_page, "Data")

        plot_page = QWidget()
        plot_page_layout = QVBoxLayout(plot_page)
        plot_page_layout.setContentsMargins(0, 12, 0, 0)
        plot_card, plot_layout = self._card("Plot preview")
        self.plot_image = QLabel("Your diagram preview will appear here")
        self.plot_image.setObjectName("plotPreview")
        self.plot_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.plot_image.setMinimumHeight(360)
        self.plot_image.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        plot_layout.addWidget(self.plot_image, 1)
        self.interactive_panel = QWidget()
        self.interactive_layout = QVBoxLayout(self.interactive_panel)
        self.interactive_layout.setContentsMargins(0, 0, 0, 0)
        self.interactive_panel.setVisible(False)
        plot_layout.addWidget(self.interactive_panel, 1)
        self.plot_details = QLabel("")
        self.plot_details.setObjectName("muted")
        plot_layout.addWidget(self.plot_details)
        plot_page_layout.addWidget(plot_card, 1)
        self.preview_tabs.addTab(plot_page, "Figure studio")
        self.map_page = QWidget()
        map_page_layout = QVBoxLayout(self.map_page)
        map_page_layout.setContentsMargins(0, 12, 0, 0)
        map_card, map_layout = self._card("Map preview")
        self.map_image = QLabel("Choose coordinate columns, then preview the map")
        self.map_image.setObjectName("plotPreview")
        self.map_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.map_image.setMinimumHeight(360)
        self.map_image.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        map_layout.addWidget(self.map_image, 1)
        self.map_interactive_panel = QWidget()
        self.map_interactive_layout = QVBoxLayout(self.map_interactive_panel)
        self.map_interactive_layout.setContentsMargins(0, 0, 0, 0)
        self.map_interactive_panel.setVisible(False)
        map_layout.addWidget(self.map_interactive_panel, 1)
        self.map_details = QLabel("")
        self.map_details.setObjectName("muted")
        self.map_details.setWordWrap(True)
        self.map_details.setTextFormat(Qt.TextFormat.PlainText)
        map_layout.addWidget(self.map_details)
        self.map_status = QLabel('Choose a basemap or use plain coordinates offline.')
        self.map_status.setWordWrap(True)
        self.map_status.setTextFormat(Qt.TextFormat.PlainText)
        map_layout.addWidget(self.map_status)
        self.map_retry_button = QPushButton('Retry background')
        self.map_retry_button.setEnabled(False)
        self.map_retry_button.clicked.connect(self._retry_map_background)
        map_layout.addWidget(self.map_retry_button)
        attribution = QLabel('The selected basemap attribution is included in the figure and export.')
        attribution.setOpenExternalLinks(True)
        map_layout.addWidget(attribution)
        map_page_layout.addWidget(map_card, 1)
        self.preview_tabs.addTab(self.map_page, "Locations")
        results_page = QWidget()
        results_layout = QVBoxLayout(results_page)
        self.result_combo = QComboBox()
        self.result_combo.currentTextChanged.connect(self._show_result_table)
        results_layout.addWidget(self.result_combo)
        self.result_table = DataFrameTable()
        self.result_table.setObjectName("dataTable")
        self.result_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        results_layout.addWidget(self.result_table, 1)
        self.result_notes = QLabel("Generate a new irrigation or statistical analysis to view numerical results.")
        self.result_notes.setWordWrap(True)
        self.result_notes.setTextFormat(Qt.TextFormat.PlainText)
        results_layout.addWidget(self.result_notes)
        self.results_format_combo = QComboBox()
        self.results_format_combo.setObjectName('resultsExportFormat')
        self.results_format_combo.setAccessibleName('Results and methods export format')
        for label, format in RESULT_FORMATS:
            self.results_format_combo.addItem(label, format)
        self.results_format_field = self._add_field(results_layout, 'Report format', self.results_format_combo)
        self.tables_button = QPushButton()
        decorate_button(self.tables_button, 'export')
        self.tables_button.setObjectName("secondaryButton")
        self.tables_button.setEnabled(False)
        self.tables_button.clicked.connect(self.export_analysis_tables)
        self.results_format_combo.currentIndexChanged.connect(self._update_results_export_label)
        self._update_results_export_label()
        results_layout.addWidget(self.tables_button)
        self.preview_tabs.addTab(results_page, "Results && methods")
        self.preview_tabs.currentChanged.connect(self._update_generate_button)
        layout.addWidget(self.preview_tabs, 1)
        self.plot_loader = BusyOverlay(self.preview_tabs, 'plotLoader')
        return panel

    def _update_generate_button(self, index):
        is_map = self.preview_tabs.widget(index) is self.map_page
        self.generate_button.setText("Generate map" if is_map else "Generate figure")

    def _filter_diagrams(self, text):
        view = self.diagram_combo.view()
        for i in range(self.diagram_combo.count()):
            view.setRowHidden(i, text.casefold() not in self.diagram_combo.itemText(i).casefold())
        if text:
            self.diagram_combo.showPopup()

    def _analysis_controls_changed(self, *args):
        name = self.diagram_combo.currentText()
        module = DIAGRAMS.get(name, ("", ""))[0]
        statistical = module == 'multivariate'
        exploratory = module == 'exploration'
        irrigation = module in ('ussl', 'wilcox')
        self.analysis_card.setVisible(statistical or irrigation or exploratory)
        self.exploration_card.setVisible(exploratory)
        time_series = EXPLORATORY_VIEWS.get(name) == 'time_series'
        measured_series = EXPLORATORY_VIEWS.get(name) == 'measured_series'
        for field in self.series_fields:
            field.setVisible(measured_series)
        self.measurement_combo.parentWidget().setVisible(exploratory and not measured_series)
        for control in (self.time_combo, self.date_format_combo, self.series_group_combo):
            control.parentWidget().setVisible(time_series)
        for control in (self.bootstrap_statistic, self.confidence_spin, self.resamples_spin, self.seed_spin):
            control.parentWidget().setVisible(exploratory and not time_series and not measured_series)
        self.ec_unit_combo.parentWidget().setVisible(irrigation)
        view = STATISTICAL_VIEWS.get(name, '')
        for widget, visible in (
            (self.variable_list, statistical or measured_series), (self.missing_combo, statistical or (exploratory and not measured_series)),
            (self.constant_combo, statistical and view != 'scatter_matrix'), (self.component_spin, view.startswith('pca')),
            (self.rotation_combo, view.startswith('pca') and view != 'pca_scree'),
            (self.cluster_spin, view == 'hca'),
            (self.significance_combo, view in ('pearson', 'spearman')),
        ):
            widget.parentWidget().setVisible(visible)
        self.scale_check.setVisible(view.startswith('pca') or view == 'hca')
        self.correlation_annotate_check.setVisible(view in ('pearson', 'spearman'))
        self.scatter_pair_check.setVisible(view == 'scatter_matrix')
        self.unit_combo.setEnabled(not (statistical or exploratory))
        self.analysis_note.setText(
            'Graphical boundaries approximate the supplied reference. Review flagged classifications. '
            'EC must be reported at 25 °C; it is never estimated from TDS.' if irrigation else
            'Select exactly two measurement variables. The first checked variable in the list is plotted on X and the second on Y. '
            'Missing-value policies still apply; constant measurements can be plotted.'
            if view == 'scatter_matrix' and self.scatter_pair_check.isChecked() else
            'No automatic log transform, imputation or outlier removal. Constant variables are undefined for correlation. '
            'Saved images use the last generated result; regenerate after changing settings.')

    def _scatter_pair_toggled(self, checked):
        if checked:
            selected = [self.variable_list.item(i) for i in range(self.variable_list.count())
                        if self.variable_list.item(i).checkState() == Qt.CheckState.Checked]
            if len(selected) > 2:
                with QSignalBlocker(self.variable_list):
                    for item in selected:
                        item.setCheckState(Qt.CheckState.Unchecked)
                self.statusBar().showMessage('Single scatter mode enabled. Check any two measurement variables.')
        self._analysis_controls_changed()

    def _limit_scatter_pair_selection(self, item):
        if (not self.scatter_pair_check.isChecked()
                or STATISTICAL_VIEWS.get(self.diagram_combo.currentText()) != 'scatter_matrix'
                or item.checkState() != Qt.CheckState.Checked):
            return
        selected = [self.variable_list.item(i) for i in range(self.variable_list.count())
                    if self.variable_list.item(i).checkState() == Qt.CheckState.Checked]
        if len(selected) > 2:
            with QSignalBlocker(self.variable_list):
                item.setCheckState(Qt.CheckState.Unchecked)
            self.statusBar().showMessage('Single scatter mode accepts exactly two variables; the third selection was ignored.')

    def _populate_variables(self, frame):
        self.variable_list.clear()
        name = self.diagram_combo.currentText()
        raw_measurements = (STATISTICAL_VIEWS.get(name) == 'scatter_matrix'
                            or EXPLORATORY_VIEWS.get(name) == 'measured_series')
        recommended = {'pH', 'EC', 'Ca', 'Mg', 'Na', 'K', 'HCO3', 'Cl', 'SO4', 'NO3', 'F'}
        excluded = {'Sample', 'Label', 'Color', 'Size', 'Alpha', 'Marker'}
        for column in frame:
            if column in excluded:
                continue
            if column not in self._numeric_columns:
                continue
            item = QListWidgetItem(column)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            constant = self._numeric_columns[column]
            item.setCheckState(Qt.CheckState.Checked if column in recommended and (raw_measurements or not constant) else Qt.CheckState.Unchecked)
            item.setToolTip('Constant: available in measured-series and scatter plots; correlation/PCA is undefined.'
                            if constant else 'Include only scientifically relevant measurements, not IDs or coordinates.')
            self.variable_list.addItem(item)

    def _clear_analysis(self):
        import matplotlib.pyplot as plt
        if self.figure_navigation is not None:
            self.figure_navigation.disconnect()
            self.figure_navigation = None
        self.reset_view_button.setEnabled(False)
        if self.map_basemap is not None:
            self.map_basemap.close()
            self.map_basemap.deleteLater()
            self.map_basemap = None
        self.map_retry_button.setEnabled(False)
        self.map_status.setText('')
        self.map_details.setText('')
        self.map_preview_pixmap = None
        self.map_image.setPixmap(QPixmap())
        self.map_image.setText('Choose coordinate columns and a source CRS, then Generate map')
        for figure in self.plot_figures:
            plt.close(figure)
        self.plot_figures = []
        self.figure_combo.clear()
        self._refresh_legend_items()
        for control in (self.elevation_spin, self.azimuth_spin, self.view_button):
            control.setEnabled(False)
        self.map_interactive_panel.setVisible(False)
        self.map_image.setVisible(True)
        if self.analysis_result is not None:
            plt.close(self.analysis_result.figure)
        self.analysis_result = None
        self._dispose_figure_view()
        self.interactive_panel.setVisible(False)
        self.plot_image.setVisible(True)
        self.result_combo.clear()
        self.result_table.clear()
        self.tables_button.setEnabled(False)
        self.result_notes.setText('Generate an irrigation or statistical analysis to view results.')

    def _run_plot_job(self, callback):
        import matplotlib
        import matplotlib.pyplot as plt
        def calculate():
            before = set(plt.get_fignums())
            try:
                result = callback()
                check_cancelled()
                return result
            except JobCancelled:
                for number in set(plt.get_fignums()) - before:
                    plt.close(number)
                raise
        self._plot_job_running = True
        try:
            # Interactive backends supplied by external integrations must retain
            # their GUI-thread ownership. The desktop application uses Agg.
            with progress_stage(20, 78, 'Calculating and building figure'):
                if str(matplotlib.get_backend()).lower() != 'agg':
                    return calculate()
                return run_worker(calculate)
        finally:
            self._plot_job_running = False

    def _report_plot_error(self, title, error):
        self.plot_loader.fail()
        if isinstance(error, JobCancelled):
            return
        if getattr(self, '_auto_updating', False):
            self._auto_update_error = True
            message = 'Auto update: ' + str(error)
            self.statusBar().showMessage(message)
            self.run_note.setText(message)
            if not self.plot_figures:
                self.generated_plot = None
                self.save_button.setEnabled(False)
                self.plot_image.setText(message)
                self.map_image.setText(message)
        else:
            QMessageBox.critical(self, title, str(error))

    @plot_loading
    def generate_analysis(self):
        import matplotlib.pyplot as plt
        self._clear_analysis()
        self.generated_plot = None
        self.save_button.setEnabled(False)
        self.generate_button.setEnabled(False)
        self.generate_button.setText('Computing analysis…')
        before = set(plt.get_fignums())
        try:
            name = self.diagram_combo.currentText()
            module_name, required = DIAGRAMS[name]
            options = {'ec_unit': self.ec_unit_combo.currentText()}
            required = set(required.split())
            text_columns = ()
            missing_policy = 'drop'
            if module_name == 'multivariate':
                columns = [self.variable_list.item(i).text() for i in range(self.variable_list.count())
                           if self.variable_list.item(i).checkState() == Qt.CheckState.Checked]
                options = dict(columns=columns, view=STATISTICAL_VIEWS[name],
                    missing=self.missing_combo.currentData(), constants=self.constant_combo.currentData(),
                    scale=self.scale_check.isChecked(), rotation=self.rotation_combo.currentText(),
                    n_components=self.component_spin.value(), n_clusters=self.cluster_spin.value(),
                    significance=self.significance_combo.currentData(), annotate=self.correlation_annotate_check.isChecked(),
                    scatter_pair=(STATISTICAL_VIEWS[name] == 'scatter_matrix'
                                  and self.scatter_pair_check.isChecked()))
                if options['view'].endswith('_3d') and hasattr(self, 'origin_lines_check'):
                    options['show_origin_lines'] = self.origin_lines_check.isChecked()
                    options['projection'] = 'ortho' if self.projection_combo.currentIndex() else 'persp'
                required.update(columns)
                missing_policy = self.missing_combo.currentData()
            elif module_name == 'exploration':
                view = EXPLORATORY_VIEWS[name]
                options = dict(view=view, column=self.measurement_combo.currentText(),
                               missing=self.missing_combo.currentData())
                required.add(self.measurement_combo.currentText())
                missing_policy = self.missing_combo.currentData()
                if view == 'measured_series':
                    from ..measurement_series import options as series_options
                    module_name = 'measurement_series'
                    required.clear()
                    options = series_options(self)
                    options['columns'] = [self.variable_list.item(i).text() for i in range(self.variable_list.count())
                                          if self.variable_list.item(i).checkState() == Qt.CheckState.Checked]
                    if self.series_order_edit.text().strip():
                        order = [c.strip() for c in self.series_order_edit.text().split(';')]
                        if len(order) != len(set(order)) or set(order) != set(options['columns']):
                            raise ValueError('Series column order must contain each selected measurement once.')
                        options['columns'] = order
                elif view == 'bootstrap':
                    options.update(statistic=self.bootstrap_statistic.currentText(),
                        confidence=self.confidence_spin.value(), resamples=self.resamples_spin.value(),
                        seed=self.seed_spin.value())
                else:
                    text_columns = (self.time_combo.currentText(),)
                    options.update(time_column=self.time_combo.currentText(),
                        date_format=self.date_format_combo.currentText(),
                        group_column=self.series_group_combo.currentText() if self.series_group_combo.currentIndex() > 0 else None)
            frame = self._make_frame(required, strict=True, text_columns=text_columns, missing=missing_policy)
            unit = self.unit_combo.currentText()
            def calculate():
                module = importlib.import_module(f'aquaprovpy.{module_name}')
                return module.plot(frame, unit=unit, figname=None, **options)
            result = self._run_plot_job(calculate)
            result.metadata.update(source_file=str(self.source_path) if self.source_path else None,
                source_sheet=self.sheet_combo.currentText() if self.excel_sheets else None,
                gui_options=options)
            self.analysis_result = result
            self._install_figures([result.figure], [name])
            from dataclasses import asdict
            result.metadata['figure_style'] = asdict(self.rendered_style)
            self.generated_plot = ('analysis', name)
            self.result_combo.addItems(list(result.tables))
            self.result_notes.setText('\n'.join(result.warnings) if result.warnings else
                                      'Analysis complete. Export all tables, methods and warnings in the selected report format.')
            self.tables_button.setEnabled(True)
            self.save_button.setEnabled(True)
            self.preview_tabs.setCurrentIndex(1)
            self.plot_details.setText(f'{name} · n = {result.metadata.get("n_used", len(frame))} · '
                                     'Interactive preview; numerical outputs in Results & methods')
            self.plot_details.setWordWrap(True)
            self.statusBar().showMessage('Analysis ready. Review Results & methods before publication.' if result.warnings
                                         else 'Analysis ready. Save the figure or export numerical results.')
        except Exception as exc:
            self.plot_loader.hide()
            self._clear_analysis()
            for number in set(plt.get_fignums()) - before:
                plt.close(number)
            self._report_plot_error('Analysis could not be generated', exc)
        finally:
            self.generate_button.setEnabled(True)
            self._update_generate_button(self.preview_tabs.currentIndex())

    def _show_result_table(self, name):
        if self.analysis_result is None or name not in self.analysis_result.tables:
            return
        self.result_table.set_frame(self.analysis_result.tables[name], results=True)

    def _analysis_export_target(self):
        name = self.name_edit.text().strip()
        if not name:
            raise ValueError('Enter a file name in Figure export, or generate a plot to fill it automatically.')
        validate_export_name(name)
        stem = Path(name).stem if Path(name).suffix.lower() in ('.png', '.pdf', '.svg', '.jpg', '.tiff', '.xlsx', '.docx', '.csv', '.json') else name
        validate_export_name(stem)
        folder = self.folder_edit.text().strip()
        if not folder:
            raise ValueError('Choose an output folder in Figure export using Browse.')
        directory = Path(folder).expanduser().resolve()
        if directory.exists() and not directory.is_dir():
            raise ValueError('The output location is a file. Choose a folder using Browse.')
        directory.mkdir(parents=True, exist_ok=True)
        return directory, stem

    def save_analysis_image(self):
        self._save_current_figures()

    def _update_generated_filename(self):
        if self.generated_plot[0] == 'map':
            title = 'Sample locations'
        elif hasattr(self, 'active_plot_title'):
            title = self.active_plot_title.text()
        else:
            title = self.diagram_combo.currentText()
        name = re.sub(r'[^a-z0-9]+', '_', title.lower()).strip('_')[:100] or 'figure'
        if self.name_edit.text() != name:
            self.name_edit.setText(name)
            if hasattr(self, '_setting_changed'):
                self._setting_changed()

    def _update_figure_export_label(self, *_):
        format = self.format_combo.currentText().upper()
        self.save_button.setText(f'Export {format}')
        self.save_button.setToolTip(f'Export the generated figure(s) as {format} to the selected folder')
        self.save_button.setAccessibleName(f'Export figure as {format}')

    def _update_results_export_label(self, *_):
        format = self.results_format_combo.currentData()
        label = FORMAT_NAMES[format]
        self.tables_button.setText(f'Export {label}')
        self.tables_button.setToolTip(f'Export all result tables, methods and warnings as {label} using the file name and folder above')
        self.tables_button.setAccessibleName(f'Export results and methods as {label}')

    def export_analysis_tables(self):
        if self.plot_loader.active:
            return
        dismiss_export_success(self)
        directory = None
        try:
            if self.analysis_result is None:
                raise ValueError('Generate a plot with numerical results before exporting a report.')
            directory, stem = self._analysis_export_target()
            format = self.results_format_combo.currentData()
            existing = result_export_paths(self.analysis_result, directory, stem, format)
            if not confirm_export_overwrite(self, existing, 'Replace existing results?'):
                self.statusBar().showMessage('Export cancelled. No files were replaced.')
                return
            result = self.analysis_result
            title = self.generated_plot[1] if self.generated_plot and self.generated_plot[0] == 'analysis' else 'AquaProv analysis'
            with self.plot_loader.busy(f'Exporting {FORMAT_NAMES[format]}\u2026', 'Results & methods'):
                paths = run_worker(lambda: result.export(directory, stem, format=format, title=title))
            self.statusBar().showMessage(f'Exported {len(paths)} result and methods files to {directory}')
        except Exception as exc:
            show_export_error(self, 'Could not export results', exc, directory or self.folder_edit.text().strip() or None)
            return
        show_export_success(self, paths, f'{FORMAT_NAMES[format]} results and methods')

    @staticmethod
    def _add_field(layout, label, widget, stretch=0):
        loading_checkpoint()
        wrapper = QWidget()
        column = QHBoxLayout(wrapper) if isinstance(widget, ColorButton) else QVBoxLayout(wrapper)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(5)
        text = QLabel(label)
        text.setObjectName("fieldLabel")
        text.setWordWrap(True)
        column.addWidget(text)
        if isinstance(widget, ColorButton):
            text.setBuddy(widget)
            widget.setAccessibleName('Choose ' + label.lower())
            column.addStretch(1)
            column.addWidget(widget)
            if widget.allow_auto:
                automatic = QPushButton('Auto')
                automatic.setObjectName('automaticColorButton')
                automatic.setToolTip('Use automatic colour')
                automatic.setAccessibleName('Use automatic ' + label.lower())
                automatic.clicked.connect(widget.clear)
                column.addWidget(automatic)
            layout.addWidget(wrapper, stretch)
            return wrapper
        if isinstance(widget, QLayout):
            column.addLayout(widget)
        elif isinstance(widget, ColourScaleCombo):
            row = QHBoxLayout()
            row.setSpacing(8)
            row.addWidget(widget, 3)
            row.addWidget(widget.preview, 2)
            column.addLayout(row)
            if widget.normalization_check is not None:
                column.addWidget(widget.normalization_check)
        else:
            column.addWidget(widget)
        layout.addWidget(wrapper, stretch)
        return wrapper

    def load_data(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Import water chemistry data", "",
            "Data files (*.csv *.xlsx *.xls);;CSV files (*.csv);;Excel workbooks (*.xlsx *.xls)",
        )
        if not filename:
            return
        from ..core.data_jobs import read_dataset
        path = Path(filename)
        try:
            with self.plot_loader.busy('Importing dataset…', path.name):
                with progress_stage(0, 55, 'Reading source file'):
                    frame, sheets, selected = run_worker(lambda: read_dataset(path))
                self.source_path = path
                self.excel_sheets = sheets
                with QSignalBlocker(self.sheet_combo):
                    self.sheet_combo.clear()
                    self.sheet_combo.addItems(sheets)
                    if selected:
                        self.sheet_combo.setCurrentText(selected)
                    self.sheet_combo.setVisible(len(sheets) > 1)
                with progress_stage(55, 98, 'Preparing dataset'):
                    self._accept_frame(frame)
        except Exception as exc:
            QMessageBox.critical(self, "Could not import file", str(exc))

    def load_selected_sheet(self, sheet):
        if not self.source_path or not self.excel_sheets or not sheet:
            return
        from ..core.data_jobs import read_dataset
        path = self.source_path
        try:
            with self.plot_loader.busy('Loading worksheet…', sheet):
                with progress_stage(0, 55, 'Reading worksheet'):
                    frame, _, _ = run_worker(lambda: read_dataset(path, sheet))
                with progress_stage(55, 98, 'Preparing dataset'):
                    self._accept_frame(frame)
        except Exception as exc:
            QMessageBox.critical(self, "Could not load worksheet", str(exc))

    def _accept_frame(self, frame):
        self._dismiss_missing_notice()
        self._last_missing_notice = None
        from ..core.data_jobs import prepare_dataset
        with progress_stage(0, 70, 'Checking dataset and measurement columns'):
            frame, self.map_data, renamed, ec_unit, self._numeric_columns = run_worker(lambda: prepare_dataset(frame))
        self.ec_unit_combo.setCurrentText(ec_unit)
        self.data = frame
        self.generated_plot = None
        self.save_button.setEnabled(False)
        self._clear_analysis()
        self.preview_pixmap = None
        self.plot_image.setPixmap(QPixmap())
        self.plot_image.setText("Dataset changed · generate a new preview")
        self.map_preview_pixmap = None
        self.map_image.setPixmap(QPixmap())
        self.map_image.setText("Dataset changed · generate a new map")
        self._populate_variables(frame)
        self._populate_map_controls(frame)
        self._populate_exploration(frame)
        self.label_combo.clear()
        self.label_combo.addItem("(single group)")
        self.label_combo.addItems(list(frame.columns))
        self.label_combo.setCurrentText("Label" if "Label" in frame.columns else "(single group)")
        self.color_combo.clear()
        self.color_combo.addItem("(single color)")
        self.color_combo.addItems([column for column in frame.columns if pd.api.types.is_numeric_dtype(frame[column])])
        self.color_combo.setCurrentIndex(0)
        sheet = self.sheet_combo.currentText() if self.excel_sheets else ""
        self.dataset_info.setText(f"{len(frame):,} rows  ·  {len(frame.columns)} columns" + (f"  ·  {sheet}" if sheet else ""))
        if hasattr(self, 'file_badge'):
            self.file_badge.setText("DATA LOADED")
        self._fill_table()
        source = self.source_path.name if self.source_path else 'in-memory data'
        self.statusBar().showMessage(f"Loaded {source}; mapped {len(renamed)} familiar source headings. Blanks preserved.")

    def _fill_table(self):
        self.table.set_frame(self.data)
        self.table_info.setText(f"Showing all {len(self.data):,} samples · blanks remain missing, not zero")

    def choose_color(self):
        self.color_button.choose_color()

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose output folder", self.folder_edit.text())
        if folder:
            self.folder_edit.setText(folder)

    def _make_frame(self, required, strict=False, *, text_columns=(), missing='drop', numeric_groups=None):
        from ..core.data_jobs import styled_plot_frame
        data = self.data
        appearance = dict(color_column=self.color_combo.currentText(), label_column=self.label_combo.currentText(),
                          color=self.color_button.text().lower(), marker=self.marker_combo.currentText(),
                          size=self.size_spin.value(), alpha=self.alpha_spin.value())
        with progress_stage(2, 20, 'Preparing plot data'):
            frame, self._plot_data_report = run_worker(lambda: styled_plot_frame(
                data, required, appearance, strict=strict, text_columns=text_columns,
                missing=missing, numeric_groups=numeric_groups))
        return frame

    @plot_loading
    def generate(self):
        if self.preview_tabs.currentWidget() is self.map_page:
            self.generate_map()
            return
        if DIAGRAMS[self.diagram_combo.currentText()][0] in ('ussl', 'wilcox', 'multivariate', 'exploration'):
            self.generate_analysis()
            return
        self._clear_analysis()
        self.generated_plot = None
        self.save_button.setEnabled(False)
        try:
            module_name, required_text = DIAGRAMS[self.diagram_combo.currentText()]
            frame = self._make_frame(set(required_text.split()), numeric_groups=DIAGRAM_GROUPS.get(module_name))
            image_format = 'png'
            if self.preview_tempdir is not None:
                self.preview_tempdir.cleanup()
            self.preview_tempdir = tempfile.TemporaryDirectory(prefix="aquaprov_preview_")
            self.generated_plot = None
            self.save_button.setEnabled(False)
            target = Path(self.preview_tempdir.name) / f"preview.{image_format}"
            self.generate_button.setEnabled(False)
            self.generate_button.setText("Generating preview…")
            self._render_plot(module_name, frame, self.unit_combo.currentText(), target, image_format, 120)
            self.generated_plot = ("diagram", module_name, frame.copy(deep=True), self.unit_combo.currentText())
            self.save_button.setEnabled(True)
            self.preview_tabs.setCurrentIndex(1)
            # The interactive canvas is the preview; no hidden PNG render/load.
            self.preview_pixmap = None
            self.plot_details.setText("Preview ready · export the figure at the selected format and DPI")
            self.statusBar().showMessage("Preview generated. Set the export options and export the figure.")
        except Exception as exc:
            self.plot_loader.hide()
            self.statusBar().showMessage("Could not generate the diagram.")
            self._report_plot_error("Diagram could not be generated", exc)
        finally:
            self.generate_button.setEnabled(True)
            self._update_generate_button(self.preview_tabs.currentIndex())

    def save_image(self):
        if self.generated_plot is None:
            QMessageBox.information(self, "Generate a preview first", "Generate a plot preview before saving the image.")
            return
        self._save_current_figures()

    def _save_current_figures(self):
        if self.plot_loader.active:
            return
        dismiss_export_success(self)
        output_dir = None
        try:
            if self.map_basemap is not None and self.map_basemap.busy:
                raise ValueError('The map background is still loading. Wait for it to finish before exporting.')
            if not self.plot_figures:
                raise ValueError('Generate a figure first.')
            output_dir, stem = self._analysis_export_target()
            image_format = self.format_combo.currentText().lower()
            targets = [output_dir / f'{stem}{"_" + str(i + 1).zfill(3) if len(self.plot_figures) > 1 else ""}.{image_format}'
                       for i in range(len(self.plot_figures))]
            if not confirm_export_overwrite(self, targets, 'Replace existing figures?'):
                self.statusBar().showMessage('Export cancelled. No files were replaced.')
                return
            # Rendered style and existing figures are authoritative: an un-applied
            # control edit must not silently change the saved scientific result.
            from ..core.plot_jobs import detached_figure
            from .loading import run_figure_worker
            figures, style, dpi = list(self.plot_figures), self.rendered_style, self.dpi_spin.value()
            def write(staged):
                for index, (figure, target) in enumerate(zip(figures, staged), 1):
                    with detached_figure(figure):
                        style.export(figure, target, dpi)
                    report_progress(95 * index / len(figures), f'Saved figure {index} of {len(figures)}')
            with self.plot_loader.busy(f'Exporting {image_format.upper()}\u2026', 'Saving figure files'):
                paths = run_figure_worker(figures, lambda: write_export_files(targets, write))
            if self.analysis_result is not None:
                self.analysis_result.metadata['last_figure_export'] = {
                    'format': image_format, 'dpi': self.dpi_spin.value(),
                    'camera': [{'elevation': float(ax.elev), 'azimuth': float(ax.azim)}
                               for ax in self.analysis_result.figure.axes if hasattr(ax, 'elev')]}
            self.statusBar().showMessage(f'Saved {len(paths)} figure(s) to {output_dir}')
        except Exception as exc:
            show_export_error(self, 'Could not save figure', exc, output_dir or self.folder_edit.text().strip() or None)
            return
        show_export_success(self, paths, image_format.upper() + (' figure' if len(paths) == 1 else ' figures'))

    def _render_plot(self, module_name, frame, unit, target, image_format, dpi):
        from ..core.plot_jobs import render_diagram
        style, title = self.plot_style(), self.diagram_combo.currentText()
        figures, labels, outputs = self._run_plot_job(lambda: render_diagram(
            module_name, frame, unit, target, image_format, dpi, style, title, save=False))
        self._install_figures(figures, labels, prepared=True)
        return outputs

    def _show_preview(self, path, map_view=False):
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            raise RuntimeError(f"Could not preview the generated image: {path}")
        if map_view or (self.generated_plot and self.generated_plot[0] == "map"):
            self.map_preview_pixmap = pixmap
        else:
            self.preview_pixmap = pixmap
        self._fit_preview()

    def _fit_preview(self):
        if self.preview_pixmap and not self.preview_pixmap.isNull():
            self.plot_image.setText("")
            self.plot_image.setPixmap(self.preview_pixmap.scaled(
                self.plot_image.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        if self.map_preview_pixmap and not self.map_preview_pixmap.isNull():
            self.map_image.setText("")
            self.map_image.setPixmap(self.map_preview_pixmap.scaled(
                self.map_image.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_preview()

    def closeEvent(self, event):
        dismiss_export_success(self)
        self._clear_analysis()
        if self.preview_tempdir is not None:
            self.preview_tempdir.cleanup()
        super().closeEvent(event)

