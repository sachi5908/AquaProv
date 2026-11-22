"""Publication workspace controls, separate from scientific calculations."""
from dataclasses import asdict
from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QAbstractButton, QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox,
    QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QScrollArea, QSpinBox, QTabWidget, QToolBox, QVBoxLayout, QWidget,
)

from .plot_style import PlotStyle
from .ui.icons import action_icon, decorate_button
from .ui.sidebar_scroll import SidebarWheelFilter
from .ui.colour_scale import ColourScaleCombo
from .ui.color_button import ColorButton
from .ui.legend_items import LegendItemsControl


class WorkspaceMixin:
    def _scroll_tab(self, tabs, name, cards):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget()
        content.setObjectName('sidebarContent')
        layout = QVBoxLayout(content)
        layout.setContentsMargins(6, 8, 6, 8)
        for card in cards:
            layout.addWidget(card)
        layout.addStretch()
        scroll.setWidget(content)
        tabs.addTab(scroll, name)
        return layout

    def _organize_sidebar(self, cards):
        panel = QWidget()
        self._sidebar_wheel_filter = SidebarWheelFilter(panel)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        self.control_tabs = QTabWidget()
        self.control_tabs.setObjectName('controlTabs')
        self.control_tabs.setDocumentMode(True)
        self.control_tabs.tabBar().setExpanding(False)
        self.control_tabs.tabBar().setDrawBase(False)
        self.control_tabs.setUsesScrollButtons(True)
        data, chart, analysis, appearance, map_card, export = cards
        self.appearance_card = appearance
        self._scroll_tab(self.control_tabs, 'Data', [data, map_card])
        self._scroll_tab(self.control_tabs, 'Analysis', [chart, analysis, self._exploration_card()])
        self._scroll_tab(self.control_tabs, 'Style', [appearance, self._publication_card()])
        self._scroll_tab(self.control_tabs, 'Export', [export])
        layout.addWidget(self.control_tabs, 1)
        self.run_note = QLabel('Import data, choose an analysis, then Generate. Styling never changes measurements.')
        self.run_note.setWordWrap(True)
        self.run_note.setObjectName('muted')
        layout.addWidget(self.run_note)
        layout.addWidget(self.generate_button)
        panel.setMinimumWidth(320)
        panel.setMaximumWidth(460)
        return panel

    def _exploration_card(self):
        self.exploration_card, layout = self._card('Time series & uncertainty',
            'Original units. Bootstrap intervals require independent observations; no forecasts or measurement-error propagation.')
        self.measurement_combo = QComboBox()
        self.time_combo = QComboBox()
        self.date_format_combo = QComboBox()
        self.date_format_combo.addItems(['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%Y-%m-%d %H:%M:%S'])
        self.series_group_combo = QComboBox()
        self.series_group_combo.addItem('(single series)')
        self.bootstrap_statistic = QComboBox()
        self.bootstrap_statistic.addItems(['mean', 'median'])
        self.confidence_spin = QDoubleSpinBox()
        self.confidence_spin.setRange(50, 99.9)
        self.confidence_spin.setValue(95)
        self.resamples_spin = QSpinBox()
        self.resamples_spin.setRange(2, 2147483647)
        self.resamples_spin.setValue(2000)
        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, 2147483647)
        self.seed_spin.setValue(42)
        for label, control in [('Measurement', self.measurement_combo), ('Date/time column', self.time_combo),
                ('Date string format', self.date_format_combo), ('Site / series group', self.series_group_combo),
                ('Bootstrap statistic', self.bootstrap_statistic), ('Confidence (%)', self.confidence_spin),
                ('Resamples', self.resamples_spin), ('Random seed', self.seed_spin)]:
            self._add_field(layout, label, control)
        from .measurement_series import build_controls
        build_controls(self, layout)
        return self.exploration_card

    def _publication_card(self):
        card, layout = self._card('Publication figure',
            'Adjust fonts, labels, colors and export size.')
        card.setObjectName('publicationCard')
        self.style_controls = {}
        defaults = asdict(PlotStyle())
        sections = QToolBox()
        sections.setObjectName('styleSections')
        sections.layout().setSpacing(6)
        section_layouts = {}
        for title, icon in (('Typography', 'settings'), ('Labels & ticks', 'generate'),
                            ('Canvas & grid', 'library'), ('Legend & color scale', 'color'),
                            ('Dimensions & export', 'export')):
            page = QWidget()
            page.setObjectName('styleSectionContent')
            fields = QVBoxLayout(page)
            fields.setContentsMargins(10, 12, 10, 12)
            fields.setSpacing(10)
            section_layouts[title] = fields
            sections.addItem(page, action_icon(icon, '#006d75'), title.replace('&', '&&'))
        # Native toolbox size hints omit stylesheet padding on Windows.
        for header in sections.findChildren(QAbstractButton, options=Qt.FindChildOption.FindDirectChildrenOnly):
            header.setMinimumHeight(38)
            header.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(sections)
        from matplotlib import font_manager
        from .plot_legends import LEGEND_POSITIONS
        choices = {
            'font_family': ['Original'] + sorted({f.name for f in font_manager.fontManager.ttflist}),
            'grid': ['Original', 'Show', 'Hide'],
            'legend': list(LEGEND_POSITIONS),
            'size_mode': ['Original', 'Custom'],
            'font_weight': ['normal', 'bold'], 'font_style': ['normal', 'italic'],
            'title_weight': ['Original', 'normal', 'bold'],
            'title_style': ['Original', 'normal', 'italic'],
            'title_position': ['Original', 'Left', 'Center', 'Right'],
            'x_rotation': ['Original', '0', '30', '45', '60', '90'],
            'y_rotation': ['Original', '0', '30', '45', '60', '90'],
            'legend_frame': ['Original','Show','Hide'],
        }
        labels = {'font_family': 'Font family', 'font_size': 'Annotation size (pt)',
            'title_size': 'Title size (pt)', 'label_size': 'Axis label size (pt)',
            'tick_size': 'Tick size (pt)', 'legend_size': 'Legend size (pt)',
            'text_color': 'Title / axis / legend color', 'figure_color': 'Figure background',
            'axes_color': 'Plot background', 'grid': 'Grid visibility', 'grid_color': 'Grid color',
            'grid_width': 'Grid width (pt)', 'border_width': 'Axis border width (pt)', 'border_color': 'Axis border colour',
            'legend': 'Legend position (also draggable)', 'cmap': 'Colour scale',
            'normalize_cmap': 'Normalize colour scale to 0–1',
            'size_mode': 'Figure sizing', 'width': 'Width (inches)', 'height': 'Height (inches)',
            'transparent': 'Transparent background', 'tight': 'Crop to content',
            'title': 'Manual plot title (optional)', 'font_weight': 'Font weight', 'font_style': 'Font style',
            'title_weight': 'Title weight', 'title_style': 'Title style', 'title_position': 'Title position',
            'x_label': 'X axis label (blank = original)', 'y_label': 'Y axis label (blank = original)',
            'z_label': 'Z axis label (blank = original)', 'colorbar_label': 'Color scale label (blank = original)',
            'x_rotation': 'X tick-label rotation (degrees)', 'y_rotation': 'Y tick-label rotation (degrees)'}
        labels.update(title_visible='Show plot title', top_right_spines='Show top and right borders',
                      colorbar_visible='Show colourbar', layout_padding='Layout padding (inches; blank = original)')
        labels['reference_note_visible'] = 'Show reference footnote'
        labels['three_d_bounds'] = '3D plot bounds (left, bottom, right, top; 0–1; blank = automatic)'
        labels.update(legend_columns='Legend columns (blank = original)',legend_frame='Legend frame',
                      legend_hidden_entries='Legend items for this plot',
                      legend_anchor='Legend anchor (x, y fractions; blank = position preset)',
                      colorbar_label_size='Colourbar label size (pt; blank = axis size)',
                      colorbar_tick_size='Colourbar tick size (pt; blank = tick size)')
        for dimension in ('x', 'y', 'z'):
            labels[dimension + '_label_visible'] = 'Show ' + dimension.upper() + ' axis label'
            labels[dimension + '_limits'] = dimension.upper() + ' limits (min, max; blank = automatic)'
            labels[dimension + '_ticks'] = dimension.upper() + ' ticks (comma-separated; blank = automatic)'
            labels[dimension + '_tick_format'] = dimension.upper() + ' tick format (e.g. .2f; blank = automatic)'
        for dimension in ('x', 'y'):
            labels[dimension + '_tick_divisor'] = dimension.upper() + ' tick divisor (e.g. 1000 for m to km)'
        for key, value in defaults.items():
            if key.startswith('title') or key in ('font_family', 'font_size', 'label_size', 'tick_size', 'legend_size', 'text_color', 'font_weight', 'font_style'):
                target = section_layouts['Typography']
            elif key.startswith(('x_', 'y_', 'z_')) or key == 'colorbar_label':
                target = section_layouts['Labels & ticks']
            elif key.startswith('legend') or key.startswith('colorbar_') or key in ('cmap', 'normalize_cmap'):
                target = section_layouts['Legend & color scale']
            elif key in ('size_mode', 'width', 'height', 'transparent', 'tight'):
                target = section_layouts['Dimensions & export']
            else:
                target = section_layouts['Canvas & grid']
            if key == 'legend_hidden_entries':
                widget = LegendItemsControl()
                widget.selectionChanged.connect(lambda: self._legend_items_edited())
            elif key == 'cmap':
                widget = ColourScaleCombo(original=True, default=value)
            elif key in choices:
                widget = QComboBox()
                widget.addItems(choices[key])
                widget.setCurrentText(str(value))
            elif isinstance(value, bool):
                widget = QCheckBox(labels[key])
                widget.setChecked(value)
            elif isinstance(value, (float, int)):
                widget = QDoubleSpinBox()
                if key in ('grid_width', 'border_width'):
                    widget.setRange(0.1, 5)
                elif key in ('width', 'height'):
                    widget.setRange(2, 24)
                else:
                    widget.setRange(4, 48)
                widget.setSingleStep(0.1 if 'width' in key or key == 'height' else 1)
                widget.setValue(value)
            elif key.endswith('color'):
                widget = ColorButton(value)
            else:
                widget = QLineEdit(value)
            widget.setObjectName('style_' + key)
            self.style_controls[key] = widget
            if isinstance(widget, QCheckBox):
                target.addWidget(widget)
            else:
                self._add_field(target, labels[key], widget)
        self.style_controls['font_family'].setToolTip(
            'Original keeps the diagram typography. Choose a font to override it.')
        self.style_controls['legend'].setToolTip(
            'Original shows the legend at its automatic position. Hide hides the whole legend; '
            'use Legend items to choose individual entries.')
        self.style_controls['reference_note_visible'].setToolTip(
            'Show source-reference footnotes on irrigation plots. References remain in Results & methods.')
        self.style_controls['normalize_cmap'].setToolTip(
            'Show continuous colour scales from 0 (low) to 1 (high). '
            'Measurements, calculations and category colours stay unchanged. '
            'Uncheck to restore the original scale labels.')
        self.style_controls['cmap'].setToolTip(
            'Apply a palette to numeric colours and show their colourbar. '
            'For sample plots, choose Color by numeric column to use a numeric scale.')
        self.style_controls['colorbar_visible'].setToolTip(
            'Show or hide the numeric colour scale. Single-colour and categorical '
            'plots use sample/group colours instead of a numeric colourbar.')
        self.colour_scale_note = QLabel()
        self.colour_scale_note.setWordWrap(True)
        self.colour_scale_note.setObjectName('muted')
        self.colour_scale_note.hide()
        section_layouts['Legend & color scale'].insertWidget(0, self.colour_scale_note)
        section_layouts['Legend & color scale'].insertWidget(
            1, self.style_controls['legend_hidden_entries'].parentWidget())
        self.style_controls['title'].setPlaceholderText('Automatic plot title')
        self.style_controls['title'].setClearButtonEnabled(True)
        self.style_controls['title'].setToolTip(
            'Leave blank to use the automatic title. The title is saved separately for each plot; sample names and counts are retained.')
        self.style_controls['title_size'].setToolTip('Font size for the main plot title only.')
        for key in ('title_weight', 'title_style'):
            self.style_controls[key].setToolTip(
                'Applies only to the main plot title. Original follows the plot typography.')
        self.style_controls['title_position'].setToolTip(
            'Align the main plot title left, center or right. Original restores its automatic position.')
        self.style_controls['transparent'].setToolTip('Transparent figure background for PNG, PDF and SVG exports.')
        self.style_controls['tight'].setToolTip('Crop empty margins; the exported dimensions may change to fit the content.')
        actions = QGridLayout()
        actions.setSpacing(8)
        actions.setColumnStretch(0, 1)
        actions.setColumnStretch(1, 1)
        for index, (label, icon, tooltip, callback) in enumerate((
                ('Apply style', 'settings', 'Apply style to the current figure', self.apply_plot_style),
                ('Reset style', 'reset', 'Restore the original publication style', self.reset_plot_style),
                ('Save preset', 'save', 'Save this publication style as a preset', self.save_style_preset),
                ('Load preset', 'open', 'Load a saved publication style preset', self.load_style_preset))):
            button = decorate_button(QPushButton(label), icon, size=14, tint='white' if index == 0 else '#006d75')
            button.setObjectName('stylePrimaryAction' if index == 0 else 'styleAction')
            button.setToolTip(tooltip)
            button.clicked.connect(callback)
            actions.addWidget(button, index // 2, index % 2)
        layout.addLayout(actions)
        return card

    def _pick_style_color(self, button):
        if isinstance(button, ColorButton):
            button.choose_color()
            return
        color = QColorDialog.getColor(QColor(button.text()), self, 'Publication color')
        if color.isValid():
            button.setText(color.name())

    def plot_style(self):
        values = {}
        for key, control in self.style_controls.items():
            if isinstance(control, LegendItemsControl):
                values[key] = control.value()
            elif isinstance(control, QComboBox):
                values[key] = control.currentText()
            elif isinstance(control, QCheckBox):
                values[key] = control.isChecked()
            elif isinstance(control, QDoubleSpinBox):
                values[key] = control.value()
            else:
                values[key] = control.text()
        return PlotStyle(**values).validate()

    def _set_style(self, style):
        for key, value in asdict(style).items():
            control = self.style_controls[key]
            if isinstance(control, LegendItemsControl):
                control.setValue(value)
            elif isinstance(control, QComboBox):
                if control.findText(str(value)) < 0:
                    control.addItem(str(value))
                control.setCurrentText(str(value))
            elif isinstance(control, QCheckBox):
                control.setChecked(value)
            elif isinstance(control, QDoubleSpinBox):
                control.setValue(value)
            else:
                control.setText(value)

    def _refresh_legend_items(self):
        from .plot_legends import available_legend_labels
        self.style_controls['legend_hidden_entries'].set_entries(
            available_legend_labels(self.plot_figures))

    def _legend_items_edited(self):
        if hasattr(self, '_style_control_edited'):
            self._style_control_edited('legend_hidden_entries')

    def apply_plot_style(self):
        from .ui.loading import run_figure_worker
        from .core.plot_jobs import detached_figure
        from .core.progress import report_progress
        try:
            style = self.plot_style()
            if not self.plot_figures:
                self.statusBar().showMessage('Style selected. Generate a figure to preview it.')
                return
            figures = list(self.plot_figures)
            def prepare():
                for index, figure in enumerate(figures, 1):
                    with detached_figure(figure):
                        style.apply(figure)
                    report_progress(85 * index / len(figures), 'Applying figure style')
            with self.plot_loader.busy('Updating figure…', 'Applying figure style'):
                run_figure_worker(figures, prepare)
                self.rendered_style = style
                if self.analysis_canvas is not None:
                    self.analysis_canvas.physical_size = self._figure_physical_size(self.analysis_canvas.figure)
                    if self.analysis_scroll_area is not None:
                        self.analysis_scroll_area.refresh_size(self.analysis_canvas.physical_size)
                    self.analysis_canvas.draw_idle()
            self.rendered_style = style
            if self.analysis_result is not None:
                self.analysis_result.metadata['figure_style'] = asdict(style)
            self._refresh_legend_items()
            self.statusBar().showMessage('Presentation updated; numerical results unchanged. Review labels and legend before export.')
        except Exception as exc:
            self._report_plot_error('Could not apply style', exc)

    def reset_plot_style(self):
        self._set_style(PlotStyle())
        self.apply_plot_style()

    def save_style_preset(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Save style preset', '', 'AquaProv style (*.json)')
        if path:
            try:
                self.plot_style().save(path)
            except Exception as exc:
                QMessageBox.critical(self, 'Could not save preset', str(exc))

    def load_style_preset(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Load style preset', '', 'AquaProv style (*.json)')
        if path:
            try:
                self._set_style(PlotStyle.load(path))
                self.apply_plot_style()
            except Exception as exc:
                QMessageBox.critical(self, 'Could not load preset', str(exc))

    def _build_workspace_tools(self, layout):
        row = QHBoxLayout()
        self.figure_combo = QComboBox()
        self.figure_combo.setMinimumWidth(140)
        self.figure_combo.currentIndexChanged.connect(self._switch_figure)
        row.addWidget(QLabel('Figure'))
        row.addWidget(self.figure_combo, 1)
        row.addWidget(self._make_reset_view_button())
        self.elevation_spin = QSpinBox()
        self.elevation_spin.setRange(-90, 90)
        self.elevation_spin.setValue(30)
        self.azimuth_spin = QSpinBox()
        self.azimuth_spin.setRange(-180, 180)
        self.azimuth_spin.setValue(-60)
        for label, spin in [('3D elevation', self.elevation_spin), ('Azimuth', self.azimuth_spin)]:
            row.addWidget(QLabel(label))
            spin.setMaximumWidth(85)
            row.addWidget(spin)
        self.view_button = QPushButton('Apply view')
        self.view_button.clicked.connect(self._apply_camera)
        row.addWidget(self.view_button)
        for control in (self.elevation_spin, self.azimuth_spin, self.view_button):
            control.setEnabled(False)
        layout.addLayout(row)

    def _make_reset_view_button(self):
        self.reset_view_button = decorate_button(QPushButton('Reset view'), 'reset')
        self.reset_view_button.setEnabled(False)
        self.reset_view_button.setToolTip('Restore the original plot bounds and 3D camera')
        self.reset_view_button.clicked.connect(self.reset_view)
        return self.reset_view_button

    def reset_view(self):
        navigation = getattr(self, 'figure_navigation', None)
        if navigation is not None:
            navigation.reset()
            self.statusBar().showMessage('Original view restored.')

    def _sync_view_controls(self):
        if self.analysis_canvas is None:
            return
        for axis in self.analysis_canvas.figure.axes:
            if hasattr(axis, 'elev'):
                for widget, value in ((self.elevation_spin, axis.elev), (self.azimuth_spin, axis.azim)):
                    with QSignalBlocker(widget):
                        widget.setValue(round(value))
                break

    def _install_figures(self, figures, labels=None, map_view=False, *, prepared=False):
        from .figure_presentation import prepare_figure_title
        from .ui.loading import run_worker
        from .core.progress import progress_stage, report_progress
        from .core.plot_jobs import detached_figure
        self.plot_figures = list(figures)
        self.figure_is_map = map_view
        self.rendered_style = self.plot_style()
        labels = labels or [f'Figure {i + 1}' for i in range(len(figures))]
        style = self.rendered_style
        def prepare():
            for index, (figure, label) in enumerate(zip(figures, labels), 1):
                with detached_figure(figure):
                    prepare_figure_title(figure, label)
                    style.apply(figure)
                report_progress(100 * index / len(figures))
        if not prepared:
            with progress_stage(78, 88, 'Applying figure style and layout'):
                run_worker(prepare)
        report_progress(90, 'Installing interactive preview')
        self.figure_combo.blockSignals(True)
        self.figure_combo.clear()
        self.figure_combo.addItems(labels)
        self.figure_combo.blockSignals(False)
        self._switch_figure(0)
        self._refresh_legend_items()

    def _dispose_figure_view(self):
        view = self.analysis_scroll_area
        if view is not None:
            view.save_state()
        for widget in (self.analysis_toolbar, view if view is not None else self.analysis_canvas):
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.analysis_canvas = self.analysis_toolbar = self.analysis_scroll_area = None

    def _switch_figure(self, index):
        if not 0 <= index < len(self.plot_figures):
            return
        from .figure_canvas import PublicationCanvas, PreviewCanvas
        from .figure_navigation import FigureNavigation
        from .figure_viewport import FigureViewport
        if self.figure_navigation is not None:
            self.figure_navigation.disconnect()
        self._dispose_figure_view()
        figure = self.plot_figures[index]
        # Online maps keep screen-sized labels with the tile viewport. Plain
        # sample maps scale the entire page, like the other scientific plots.
        tile_view = self.figure_is_map and hasattr(figure, '_aquaprov_map_coordinates')
        self.analysis_canvas = (PreviewCanvas(figure) if tile_view else
                                PublicationCanvas(figure, self._figure_physical_size(figure)))
        target = self.map_interactive_panel if self.figure_is_map else self.interactive_panel
        layout = self.map_interactive_layout if self.figure_is_map else self.interactive_layout
        self.analysis_toolbar = None
        self.analysis_scroll_area = FigureViewport(self.analysis_canvas, self._figure_physical_size(figure))
        layout.addWidget(self.analysis_scroll_area, 1)
        self.figure_navigation = FigureNavigation(self.analysis_canvas, self._sync_view_controls)
        self.reset_view_button.setEnabled(bool(self.figure_navigation.axes))
        self.analysis_canvas.setToolTip('Scroll to enlarge the whole figure • Drag to scroll (3D: rotate) • Shift+scroll or Shift+drag zooms or pans the data • Reset view restores the starting view')
        target.setVisible(True)
        self.analysis_scroll_area.refresh_size()
        (self.map_image if self.figure_is_map else self.plot_image).setVisible(False)
        has_3d = any(hasattr(axis, 'view_init') for axis in figure.axes)
        for control in (self.elevation_spin, self.azimuth_spin, self.view_button):
            control.setEnabled(has_3d)
        if self.figure_is_map or getattr(self, 'defer_figure_draw', False):
            # Let Qt size newly visible maps and module panels before measuring
            # labels; an immediate draw can receive a transient tiny viewport.
            self.analysis_canvas.draw_idle()
        else:
            self.analysis_canvas.draw()

    def _figure_physical_size(self, figure):
        style = self.rendered_style
        return (style.width, style.height) if style.size_mode == 'Custom' else figure._aquaprov_original_size

    def _apply_camera(self):
        if self.analysis_canvas is None:
            return
        for axis in self.analysis_canvas.figure.axes:
            if hasattr(axis, 'view_init'):
                axis.view_init(elev=self.elevation_spin.value(), azim=self.azimuth_spin.value())
        self.analysis_canvas.draw_idle()

    def _build_menus(self):
        file_menu = self.menuBar().addMenu('&File')
        for text, shortcut, callback in [('Import data', 'Ctrl+O', self.load_data),
                ('Export figure', 'Ctrl+S', self.save_image), ('Generate', 'F5', self.generate)]:
            action = QAction(text, self)
            action.setShortcut(shortcut)
            action.triggered.connect(callback)
            file_menu.addAction(action)
        help_menu = self.menuBar().addMenu('&Help')
        action = QAction('Publication checklist / methods', self)
        action.triggered.connect(self._publication_help)
        help_menu.addAction(action)

    def _publication_help(self):
        QMessageBox.information(self, 'Publication checklist',
            '1. Confirm worksheet, units, missing values and sampling design.\n'
            '2. Select measurement variables deliberately; exclude IDs and coordinates.\n'
            '3. Review exclusions, method assumptions and warnings in Results & methods.\n'
            '4. Check axes, labels, colors, legends and the final physical figure size.\n'
            '5. Export PDF/SVG for vector artwork or PNG/TIFF at the journal DPI.\n'
            '6. Export full-precision tables and methods JSON alongside the figure.\n\n'
            'Time series are descriptive, not forecasts. Bootstrap intervals assume iid rows; '
            'they are not laboratory measurement-error intervals. No method automatically '
            'makes a dataset or interpretation publication-ready.\n\n'
            'AquaProv is distributed under GPL v3; original author attribution is retained in README.md.')

    def _populate_exploration(self, frame):
        numeric = [str(c) for c in frame if pd_numeric(frame[c])]
        for combo, values in [(self.measurement_combo, numeric), (self.time_combo, list(frame)),
                              (self.series_group_combo, ['(single series)'] + list(frame))]:
            combo.clear()
            combo.addItems(values)
        for column in frame:
            if any(word in str(column).lower() for word in ('date', 'time')):
                self.time_combo.setCurrentText(column)
                break


def pd_numeric(series):
    import pandas as pd
    return pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series)
