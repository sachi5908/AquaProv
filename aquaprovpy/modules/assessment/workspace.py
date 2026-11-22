"""Assessment controls, plot library, exports and portable replay."""

from copy import deepcopy
import json
from pathlib import Path

from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QLabel,
    QListWidget, QListWidgetItem, QLineEdit, QMessageBox, QPushButton, QSpinBox)

from ..base import ModuleWorkspace
from ..maps.boundary_ui import BoundaryWorkspaceMixin
from ..maps import spatial_controls
from .spatial_ui import AssessmentSpatialMixin
from ...assessment.engine import VIEWS, plot
from ...assessment.measurements import suggest_schema
from ...assessment.uncertainty import WHO_SCREENING, validate_profile
from ...assessment.replay import save_manifest
from ...ui.loading import plot_loading, run_worker


class AssessmentWorkspace(AssessmentSpatialMixin, BoundaryWorkspaceMixin, ModuleWorkspace):
    module_key = 'assessment'

    def __init__(self):
        self.study_boundary = None
        self.measurement_schema = None
        self.threshold_profile = deepcopy(WHO_SCREENING)
        self.censor_models = {}
        super().__init__()
        self.hide_locations()
        self.chart_card.hide()
        self.appearance_card.hide()
        mapping, layout = self._card('Measurement model', 'Keep raw values; review units, qualifiers, detection limits and laboratory SDs.')
        self.mapping_note = QLabel('Import data to configure measurement mappings.')
        self.mapping_note.setWordWrap(True)
        layout.addWidget(self.mapping_note)
        button = QPushButton('Review measurement mappings…')
        button.clicked.connect(self.edit_schema)
        layout.addWidget(button)
        self.selection_column_combo = QComboBox()
        self.selection_column_combo.addItem('(all records)')
        self.selection_value_edit = QLineEdit()
        self.selection_value_edit.setPlaceholderText('Exact campaign, year, aquifer or label')
        self.one_per_well_check = QCheckBox('Use first source record per well in the selected subset')
        self._add_field(layout, 'Subset column', self.selection_column_combo)
        self._add_field(layout, 'Keep rows equal to', self.selection_value_edit)
        layout.addWidget(self.one_per_well_check)
        self.control_tabs.widget(0).widget().layout().insertWidget(1, mapping)

        self.research_card, layout = self._card('Assessment settings')
        self.assessment_view_combo = QComboBox()
        self.assessment_view_combo.addItems(VIEWS.values())
        self.assessment_chart_combo = QComboBox()
        self.assessment_chart_combo.addItem('Dashboard')
        self._add_field(layout, 'Chart', self.assessment_chart_combo)
        self.assessment_bar_colors_edit = QLineEdit()
        self.assessment_bar_colors_edit.setPlaceholderText('Blank = sample colour; or comma-separated colours')
        self._add_field(layout, 'RMSE bar colours (table order)', self.assessment_bar_colors_edit)
        self.uncertainty_mode_combo = QComboBox()
        for title, value in [('Fixed detected values', 'fixed'), ('Sensitivity scenario (relative SD)', 'scenario'), ('Supplied laboratory SDs', 'laboratory')]:
            self.uncertainty_mode_combo.addItem(title, value)
        self.censoring_combo = QComboBox()
        for title, value in [('Exclude censored observations', 'exclude'), ('Uniform between zero and limit', 'uniform'), ('Fixed half-limit sensitivity', 'half_limit'), ('Supplied truncated lognormal model', 'lognormal')]:
            self.censoring_combo.addItem(title, value)
        self.censor_model_button = QPushButton('Load censored-distribution models (JSON)…')
        self.censor_model_button.clicked.connect(self.load_censor_models)
        self.priority_method_combo = QComboBox()
        self.priority_method_combo.addItem('Threshold ambiguity', 'ambiguity')
        self.priority_method_combo.addItem('Expected reduction in decision errors', 'evsi')
        def spin(name, minimum, maximum, default, decimal=False):
            widget = QDoubleSpinBox() if decimal else QSpinBox()
            widget.setRange(minimum, maximum)
            widget.setValue(default)
            setattr(self, name, widget)
            return widget
        spin('relative_sd_spin', 0, 100, 5, True)
        spin('error_correlation_spin', 0, .95, 0, True)
        self.error_correlation_spin.setSingleStep(.1)
        spin('draws_spin', 200, 20000, 2000)
        spin('assessment_seed_spin', 0, 2147483647, 42)
        spin('balance_tolerance_spin', .1, 100, 5, True)
        spin('budget_spin', 0, 1e9, 10, True)
        spin('assay_cost_spin', .01, 1e9, 1, True)
        spin('followup_relative_sd_spin', .01, 100, 5, True)
        spin('stability_repeats_spin', 1, 2147483647, 100)
        spin('well_resamples_spin', 2, 2147483647, 2000)
        spin('coda_clusters_spin', 1, 2147483647, 3)
        spin('folds_spin', 3, 10, 5)
        spin('spatial_threshold_spin', .000001, 1e9, .05, True)
        self.spatial_threshold_spin.setDecimals(6)
        self.spatial_threshold_check = QCheckBox('Evaluate spatial exceedance at the specified threshold')
        self.assessment_column_combo = QComboBox()
        self.assessment_coordinates_combo = QComboBox()
        self.assessment_coordinates_combo.addItem('(choose coordinate system)', None)
        self.assessment_coordinates_combo.addItem('WGS84 longitude / latitude', 'wgs84')
        self.assessment_coordinates_combo.addItem('Projected / local coordinates', 'projected')
        self.assessment_model_combo = QComboBox()
        self.assessment_model_combo.addItems(['spherical', 'exponential'])
        self.coda_list = QListWidget()
        self.coda_list.setMaximumHeight(170)
        self.profile_note = QLabel(self.threshold_profile['id'])
        self.profile_note.setWordWrap(True)
        self.profile_button = QPushButton('Load a threshold profile (JSON)…')
        self.profile_button.clicked.connect(self.load_profile)
        self.profile_reset_button = QPushButton('Use WHO 2022 selected chemicals')
        self.profile_reset_button.clicked.connect(self.reset_profile)
        self.setting_fields = {}
        for title, widget, views in [
            ('View', self.assessment_view_combo, set(VIEWS)),
            ('Balance review tolerance (%)', self.balance_tolerance_spin, {'qa'}),
            ('Uncertainty model', self.uncertainty_mode_combo, {'uncertainty', 'piper', 'screening', 'priorities'}),
            ('Scenario relative SD (%)', self.relative_sd_spin, {'uncertainty', 'piper', 'screening', 'priorities', 'scenarios'}),
            ('Shared log-error correlation', self.error_correlation_spin, {'uncertainty', 'piper', 'screening', 'priorities', 'scenarios'}),
            ('Non-detect method', self.censoring_combo, {'uncertainty', 'piper', 'screening', 'priorities'}),
            ('Censored-distribution models', self.censor_model_button, {'uncertainty', 'piper', 'screening', 'priorities'}),
            ('Monte Carlo draws', self.draws_spin, {'uncertainty', 'piper', 'screening', 'priorities', 'scenarios'}),
            ('Random seed', self.assessment_seed_spin, set(VIEWS)-{'qa'}),
            ('Assay budget (cost units)', self.budget_spin, {'priorities'}),
            ('Cost per assay (same units)', self.assay_cost_spin, {'priorities'}),
            ('Assay priority rule', self.priority_method_combo, {'priorities'}),
            ('Follow-up assay relative SD (%)', self.followup_relative_sd_spin, {'priorities'}),
            ('Selected threshold profile', self.profile_note, {'screening', 'priorities', 'scenarios'}),
            ('Profile import', self.profile_button, {'screening', 'priorities', 'scenarios'}),
            ('Default profile', self.profile_reset_button, {'screening', 'priorities', 'scenarios'}),
            ('Concentration components', self.coda_list, {'coda', 'stability'}),
            ('Ward cluster count', self.coda_clusters_spin, {'coda', 'stability'}),
            ('Cluster stability resamples', self.stability_repeats_spin, {'stability'}),
            ('Well bootstrap resamples', self.well_resamples_spin, {'wells'}),
            ('Measurement', self.assessment_column_combo, {'wells', 'spatial', 'spatial_map'}),
            ('Distance coordinates', self.assessment_coordinates_combo, {'spatial', 'spatial_map'}),
            ('Variogram model', self.assessment_model_combo, {'spatial', 'spatial_map'}),
            ('Geographic blocks', self.folds_spin, {'spatial', 'spatial_map'}),
            ('Exceedance evaluation', self.spatial_threshold_check, {'spatial', 'spatial_map'}),
            ('Threshold (normalized units)', self.spatial_threshold_spin, {'spatial', 'spatial_map'}),
        ]:
            wrapper = self._add_field(layout, title, widget)
            self.setting_fields[widget] = (wrapper, views)
        self.control_tabs.widget(1).widget().layout().insertWidget(0, self.research_card)
        self.replay_button = QPushButton('Export reproducible run (JSON)…')
        self.replay_button.setEnabled(False)
        self.replay_button.clicked.connect(self.export_replay)
        self.control_tabs.widget(3).widget().layout().insertWidget(0, self.replay_button)
        self.assessment_view_combo.currentTextChanged.connect(self._analysis_controls_changed)
        self.uncertainty_mode_combo.currentIndexChanged.connect(self._analysis_controls_changed)
        self.coda_list.itemChanged.connect(self._setting_changed)
        from ...chart_controls import add_fields, build_reference_controls
        self.assessment_appearance_card, appearance = self._card('Chart appearance')
        add_fields(self, appearance, [
            ('balance_band_check','Show charge-balance tolerance band',True),
            ('balance_band_color_edit','Tolerance band colour','#dcece5'),
            ('balance_band_alpha_spin','Tolerance band opacity',1.,(0,1)),
            ('balance_review_color_edit','Outside-tolerance point colour','#ce6b32'),
            ('chart_edge_color_edit','Point outline colour','#ffffff'),
            ('chart_edge_width_spin','Point outline width (pt)',.25,(0,5)),
            ('interval_color_edit','Interval colour (blank = point colour)',''),
            ('interval_width_spin','Interval line width (pt)',.75,(.1,6)),
            ('interval_cap_spin','Interval cap length (pt)',1.3,(0,12)),
            ('interval_cap_width_spin','Interval cap thickness (pt)',.75,(.1,6)),
        ])
        self.control_tabs.widget(1).widget().layout().insertWidget(1,self.assessment_appearance_card)
        build_reference_controls(self,note=True)
        self.assessment_chart_combo.currentTextChanged.connect(self._analysis_controls_changed)
        self.assessment_bar_colors_edit.textChanged.connect(self._analysis_controls_changed)
        self._build_assessment_maps()
        self.connect_settings()
        from ..measurement_labels import bind_measurement_labels
        bind_measurement_labels(self, self.assessment_column_combo, dimensions=('x', 'y'))

    def view_key(self):
        return next(k for k,v in VIEWS.items() if v == self.assessment_view_combo.currentText())

    def _analysis_controls_changed(self, *_):
        if hasattr(self, 'analysis_card'):
            self.analysis_card.hide()
            self.exploration_card.hide()
        if not hasattr(self, 'setting_fields'):
            return
        view = self.view_key()
        from ...assessment.charts import CHARTS
        available = CHARTS.get(view, ['Dashboard'])
        current = self.assessment_chart_combo.currentText()
        if [self.assessment_chart_combo.itemText(i) for i in range(self.assessment_chart_combo.count())] != available:
            with QSignalBlocker(self.assessment_chart_combo):
                self.assessment_chart_combo.clear()
                self.assessment_chart_combo.addItems(available)
                if current in available:
                    self.assessment_chart_combo.setCurrentText(current)
        for widget, (wrapper, views) in self.setting_fields.items():
            visible = view in views and widget is not self.assessment_view_combo
            if widget is self.relative_sd_spin:
                visible &= self.uncertainty_mode_combo.currentData() == 'scenario' or view == 'scenarios'
            wrapper.setVisible(visible)
        if hasattr(self, 'assessment_appearance_card'):
            chart = self.assessment_chart_combo.currentText()
            bars = chart == 'RMSE comparison'
            self.assessment_bar_colors_edit.parentWidget().setVisible(bars)
            individual = chart != 'Dashboard'
            self.appearance_card.setVisible(individual)
            # These charts use source rows / held-out blocks, not the generic
            # sample grouping or numeric-colour columns from legacy diagrams.
            self.label_combo.parentWidget().hide()
            self.color_combo.parentWidget().hide()
            self.marker_combo.parentWidget().setVisible(not bars)
            self.size_spin.parentWidget().setVisible(not bars)
            for widget in (self.single_color_label, self.color_button):
                widget.setVisible(chart != 'Held-out predictions')
                widget.setEnabled(not bars or not self.assessment_bar_colors_edit.text().strip())
            self.color_button.setToolTip('Clear RMSE bar colours to use a single fill colour.' if bars else 'Choose sample colour')
            self.assessment_appearance_card.setVisible(individual and view in ('qa','uncertainty'))
            self.reference_card.setVisible(individual and view in ('qa','uncertainty'))
            for name, widget in vars(self).items():
                if name.startswith('balance_band_') or name == 'balance_review_color_edit':
                    (widget if isinstance(widget,QCheckBox) else widget.parentWidget()).setVisible(view=='qa')
                elif name.startswith('interval_'):
                    widget.parentWidget().setVisible(view=='uncertainty')
        self._update_assessment_maps()

    def refresh_contextual_controls(self):
        self.chart_card.hide()
        self.appearance_card.show()
        self._analysis_controls_changed()

    def populate_module_columns(self):
        if not hasattr(self, 'assessment_column_combo') or self.data is None:
            return
        data = self.data
        self.measurement_schema = run_worker(lambda: suggest_schema(data))
        self.selection_column_combo.clear()
        self.selection_column_combo.addItems(['(all records)', *self.data.columns])
        self.selection_value_edit.clear()
        self.one_per_well_check.setChecked(False)
        self._refresh_mappings()
        self.assessment_coordinates_combo.setCurrentIndex(0)
        self.analysis_crs_edit.clear()
        self.spatial_source_crs_edit.clear()

    def _refresh_mappings(self):
        if not self.measurement_schema:
            return
        fields = self.measurement_schema['fields']
        selected = self.assessment_column_combo.currentText()
        self.assessment_column_combo.clear()
        self.assessment_column_combo.addItems(fields)
        if selected in fields:
            self.assessment_column_combo.setCurrentText(selected)
        elif 'Cr_total' in fields:
            self.assessment_column_combo.setCurrentText('Cr_total')
        elif 'NO3' in fields:
            self.assessment_column_combo.setCurrentText('NO3')
        self.coda_list.clear()
        for a in fields:
            if a in ('pH', 'EC', 'TDS', 'Alkalinity'):
                continue
            item = QListWidgetItem(a)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if a in ('Ca', 'Mg', 'Na', 'K', 'HCO3', 'Cl', 'SO4') else Qt.CheckState.Unchecked)
            self.coda_list.addItem(item)
        state = 'units reviewed' if self.measurement_schema.get('unit_assumptions_confirmed') else 'suggested units: review before interpretation'
        self.mapping_note.setText(f'{len(fields)} mapped measurements · {state}')

    def edit_schema(self):
        if self.data is None:
            QMessageBox.information(self, 'Import measurements', 'Import a dataset before mapping measurements.')
            return
        from .schema_dialog import SchemaDialog
        dialog = SchemaDialog(self.data, self.measurement_schema or suggest_schema(self.data), self)
        if dialog.exec():
            self._clear_plot_cache()
            self.measurement_schema = dialog.schema
            self._refresh_mappings()
            self._invalidate_plot()
            self._setting_changed()

    def load_profile(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Threshold profile', '', 'JSON (*.json)')
        if not path:
            return
        try:
            profile = validate_profile(json.loads(Path(path).read_text(encoding='utf-8')))
        except (ValueError, OSError, KeyError, TypeError) as exc:
            QMessageBox.warning(self, 'Invalid threshold profile', str(exc))
            return
        self.threshold_profile = profile
        self.profile_note.setText(profile['id'])
        self._invalidate_plot()
        self._setting_changed()

    def reset_profile(self):
        self.threshold_profile = deepcopy(WHO_SCREENING)
        self.profile_note.setText(self.threshold_profile['id'])
        self._invalidate_plot()
        self._setting_changed()

    def load_censor_models(self):
        from ...assessment.censoring import validate_censor_model
        path, _ = QFileDialog.getOpenFileName(self, 'Censored-distribution models', '', 'JSON (*.json)')
        if not path:
            return
        try:
            models = json.loads(Path(path).read_text(encoding='utf-8'))
            if not isinstance(models, dict) or not models:
                raise ValueError('Provide analyte names mapped to log_mean, log_sd and source.')
            for model in models.values():
                validate_censor_model(model)
        except (ValueError, OSError, TypeError) as exc:
            QMessageBox.warning(self, 'Invalid censored-distribution models', str(exc))
            return
        self.censor_models = models
        self.censor_model_button.setText(f'{len(models)} model(s) loaded · change JSON…')
        self._invalidate_plot()
        self._setting_changed()

    def _capture_current_state(self):
        state = super()._capture_current_state()
        state['measurement_schema'] = deepcopy(self.measurement_schema)
        state['threshold_profile'] = deepcopy(self.threshold_profile)
        state['censor_models'] = deepcopy(self.censor_models)
        if hasattr(self, 'coda_list'):
            state['coda_columns'] = self.selected_components()
        return state

    def _capture_profile(self):
        state = super()._capture_profile()
        state.pop('measurement_schema', None)  # Each dataset shares one measurement model.
        if self.data is None:
            state.pop('coda_columns', None)
        return state

    def _restore_current_state(self, state):
        state = deepcopy(state)
        spatial_controls.restore_defaults(state, switching=getattr(self,'_switching_plot',False))
        state['controls'].setdefault('assessment_map_output_combo','Prediction and uncertainty')
        self.censor_models = deepcopy(state.get('censor_models', {}))
        if state.get('measurement_schema') is not None:
            self.measurement_schema = deepcopy(state['measurement_schema'])
            self._refresh_mappings()
        if state.get('threshold_profile'):
            self.threshold_profile = validate_profile(deepcopy(state['threshold_profile']))
            self.profile_note.setText(self.threshold_profile['id'])
        super()._restore_current_state(state)
        if 'coda_columns' in state:
            with QSignalBlocker(self.coda_list):
                for i in range(self.coda_list.count()):
                    item = self.coda_list.item(i)
                    item.setCheckState(Qt.CheckState.Checked if item.text() in state['coda_columns'] else Qt.CheckState.Unchecked)

    def selected_components(self):
        return [self.coda_list.item(i).text() for i in range(self.coda_list.count())
                if self.coda_list.item(i).checkState() == Qt.CheckState.Checked]

    def analysis_config(self):
        view = self.view_key()
        from ...chart_controls import reference_options
        cfg = {'schema': deepcopy(self.measurement_schema), 'view': view,
               'chart': self.assessment_chart_combo.currentText(), 'chart_color': self.color_button.text(),
               'chart_size': self.size_spin.value(), 'chart_marker': self.marker_combo.currentText(),
               'balance_tolerance': self.balance_tolerance_spin.value(), 'seed': self.assessment_seed_spin.value(),
               'filter_column': self.selection_column_combo.currentText() if self.selection_column_combo.currentIndex() > 0 else None,
               'filter_value': self.selection_value_edit.text(), 'one_per_well': self.one_per_well_check.isChecked()}
        cfg['chart_appearance'] = dict(alpha=self.alpha_spin.value(), band=self.balance_band_check.isChecked(),
            band_color=self.balance_band_color_edit.text(),band_alpha=self.balance_band_alpha_spin.value(),
            review_color=self.balance_review_color_edit.text(),edgecolor=self.chart_edge_color_edit.text(),
            edgewidth=self.chart_edge_width_spin.value(),interval_color=self.interval_color_edit.text(),
            interval_width=self.interval_width_spin.value(),capsize=self.interval_cap_spin.value(),
            capwidth=self.interval_cap_width_spin.value(),reference=reference_options(self),
            bar_colors=self.assessment_bar_colors_edit.text())
        if view in ('uncertainty', 'piper', 'screening', 'priorities', 'scenarios'):
            cfg.update(draws=self.draws_spin.value(), uncertainty=self.uncertainty_mode_combo.currentData(),
                       relative_sd=self.relative_sd_spin.value()/100, censoring=self.censoring_combo.currentData(),
                       profile=deepcopy(self.threshold_profile), budget=self.budget_spin.value(), assay_cost=self.assay_cost_spin.value(),
                       error_correlation=self.error_correlation_spin.value())
            cfg.update(censor_models=deepcopy(self.censor_models), priority_method=self.priority_method_combo.currentData(),
                       followup_relative_sd=self.followup_relative_sd_spin.value()/100)
        if view in ('coda', 'stability'):
            cfg.update(columns=self.selected_components(), clusters=self.coda_clusters_spin.value(),
                       resamples=self.stability_repeats_spin.value() if view == 'stability' else 0)
        if view in ('spatial', 'spatial_map', 'wells'):
            cfg['column'] = self.assessment_column_combo.currentText()
        if view == 'wells':
            cfg['resamples'] = self.well_resamples_spin.value()
        if view in ('spatial', 'spatial_map'):
            cfg.update(self._assessment_spatial_config())
            cfg.update(coordinates=self.assessment_coordinates_combo.currentData(), folds=self.folds_spin.value(),
                       model=self.assessment_model_combo.currentText(),
                       threshold=self.spatial_threshold_spin.value() if self.spatial_threshold_check.isChecked() else None)
        return cfg

    @plot_loading
    def generate(self):
        self._clear_analysis()
        self.generated_plot = None
        self.save_button.setEnabled(False)
        try:
            if self.data is None or not self.measurement_schema:
                raise ValueError('Import data and review measurement mappings first.')
            config = self.analysis_config()
            data = self.data
            self.generate_button.setEnabled(False)
            def calculate():
                frame = data.copy(deep=True)
                return frame, plot(frame, config)
            frame, result = self._run_plot_job(calculate)
            self.show_result(result, VIEWS[config['view']])
            self._render_frame, self._render_config = frame, config
            self.replay_button.setEnabled(True)
        except Exception as exc:
            self._clear_analysis()
            self._report_plot_error('Assessment could not be generated', exc)
        finally:
            self.generate_button.setEnabled(True)

    def _clear_analysis(self):
        super()._clear_analysis()
        if hasattr(self, 'replay_button'):
            self.replay_button.setEnabled(False)

    def export_replay(self):
        if self.analysis_result is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Export reproducible assessment',
                  str(Path(self.folder_edit.text())/'assessment_run.json'), 'JSON (*.json)')
        if not path:
            return
        try:
            save_manifest(path, self._render_frame, self._render_config, self.analysis_result)
            self.statusBar().showMessage('Replay saved with embedded measurements, settings, versions and numerical hashes.')
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, 'Replay export failed', str(exc))
