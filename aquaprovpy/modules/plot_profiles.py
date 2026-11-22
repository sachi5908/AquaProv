"""Independent plot settings, with migration from flat module project settings."""
from contextlib import ExitStack
from copy import deepcopy
from PySide6.QtCore import QSignalBlocker
from .plot_catalog import plot_choices


DATA_CONTROLS = {'map_crs_combo', 'map_zone_spin', 'map_hemisphere_combo', 'distance_combo',
                 'map_x_combo', 'map_y_combo', 'map_value_combo', 'map_label_combo',
                 'x_axis_combo', 'y_axis_combo', 'z_axis_combo', 'ec_unit_combo',
                 'measurement_combo', 'time_combo', 'series_group_combo', 'label_combo', 'color_combo'}
DATA_CONTROLS |= {'assessment_column_combo', 'selection_column_combo', 'assessment_coordinates_combo'}
DATA_CONTROLS |= {'analysis_crs_edit', 'spatial_source_crs_edit'}
COORDINATE_ASSUMPTIONS = {'map_crs_combo', 'map_zone_spin', 'map_hemisphere_combo', 'distance_combo', 'ec_unit_combo',
                         'assessment_coordinates_combo', 'selection_column_combo', 'selection_value_edit', 'one_per_well_check'}
COORDINATE_ASSUMPTIONS |= {'analysis_crs_edit', 'spatial_source_crs_edit'}


def clear_dataset_assumptions(state):
    """Remove stale CRS/unit assumptions from active and inactive plot profiles."""
    for profile in [state, *state.get('plot_profiles', {}).values()]:
        profile.pop('publication_panel', None)
        profile.pop('study_boundary', None)
        for name in ('boundary_enabled_check', 'boundary_extrapolate_check', 'boundary_samples_check'):
            profile.get('controls', {}).pop(name, None)
        profile.pop('measurement_schema', None)
        for key in COORDINATE_ASSUMPTIONS:
            profile.get('controls', {}).pop(key, None)


class PlotProfilesMixin:
    def initialize_plot_profiles(self):
        self._choices = plot_choices(self.module_key)
        self._route_names = {name for choice in self._choices for name, _ in choice.routes}
        self._switching_plot = False
        self._plot_profiles = {}
        self._plot_cache = {}
        self._active_plot = self._choice_from_controls().key
        self._plot_defaults = self._capture_profile()
        self._plot_defaults.pop('variables', None)
        for name in DATA_CONTROLS:
            self._plot_defaults['controls'].pop(name, None)
        self.plot_browser.populate(self._choices)
        self.plot_browser.plot_selected.connect(self.select_plot)
        for name in self._route_names:
            getattr(self, name).currentTextChanged.connect(self._route_control_changed)
        self._refresh_plot_caption()

    def _choice_from_controls(self):
        return next((choice for choice in self._choices if all(
            getattr(self, name).currentText() == value for name, value in choice.routes)), self._choices[0])

    def _capture_profile(self):
        state = self._capture_current_state()
        for name in self._route_names:
            state['controls'].pop(name, None)
        return state

    def _route_control_changed(self, *_):
        if self._restoring or self._switching_plot:
            return
        self._activate_plot(self._choice_from_controls())

    def select_plot(self, key):
        choice = next(choice for choice in self._choices if choice.key == key)
        with ExitStack() as stack:
            for name in self._route_names:
                stack.enter_context(QSignalBlocker(getattr(self, name)))
            for name, value in choice.routes:
                getattr(self, name).setCurrentText(value)
        self._activate_plot(choice)

    def _activate_plot(self, choice):
        if choice.key == self._active_plot:
            self._refresh_plot_caption()
            return
        self._dismiss_missing_notice()
        self._switching_plot = True
        try:
            self._stash_plot()
            self._cancel_auto_update()
            self._plot_profiles[self._active_plot] = self._capture_profile()
            self._active_plot = choice.key
            self._restore_current_state(deepcopy(self._plot_profiles.get(choice.key, self._plot_defaults)))
            self._invalidate_plot()
            self._refresh_plot_caption()
            restored = self._restore_cached_plot(choice.key)
            self.control_tabs.setCurrentIndex(0)
        finally:
            self._switching_plot = False
        self.settings_changed.emit()
        if not restored:
            self._queue_auto_update()
        elif self._pending_auto_updates:
            self._queue_auto_update('style')

    def _invalidate_plot(self):
        self._clear_analysis()
        self.generated_plot = None
        self.save_button.setEnabled(False)
        self.plot_image.setText("Settings ready · Generate this plot to view your data")
        self.statusBar().showMessage("Plot settings restored. Generate to update the figure.")

    def _refresh_plot_caption(self):
        choice = next(choice for choice in self._choices if choice.key == self._active_plot)
        self.active_plot_title.setText(choice.title)
        self.active_plot_title.setToolTip(choice.title)
        self.plot_description.setText(choice.description)
        self.plot_browser.select(choice.key)
        self._analysis_controls_changed()
        if self.module_key == 'maps':
            self._spatial_changed()
        self.preview_tabs.setCurrentIndex(2 if self.module_key == 'maps' and choice.key == 'locations' else 1)
        self.quick_typography.sync()
        self.refresh_contextual_controls()
        self._refresh_auto_update_note()
        refresh_inputs = getattr(self, '_refresh_input_status', None)
        if refresh_inputs is not None:
            refresh_inputs()

    def reset_current_plot(self):
        self._switching_plot = True
        try:
            self._cancel_auto_update()
            self._restore_current_state(deepcopy(self._plot_defaults))
            self._plot_profiles.pop(self._active_plot, None)
            self._invalidate_plot()
            self._refresh_plot_caption()
        finally:
            self._switching_plot = False
        self._setting_changed()

    def capture_state(self):
        current = self._capture_current_state()
        if hasattr(self, '_active_plot'):
            self._plot_profiles[self._active_plot] = self._capture_profile()
            current['active_plot'] = self._active_plot
            current['plot_profiles'] = deepcopy(self._plot_profiles)
        return current

    def restore_state(self, state):
        self._switching_plot = True
        try:
            profiles = state.get('plot_profiles', {})
            valid_keys = {choice.key for choice in self._choices}
            if not isinstance(profiles, dict) or any(not isinstance(value, dict) for value in profiles.values()):
                raise ValueError('Invalid saved plot settings.')
            self._plot_profiles = deepcopy({key: value for key, value in profiles.items() if key in valid_keys})
            self._restore_current_state(state)
            self._active_plot = self._choice_from_controls().key
            # Flat controls remain authoritative for migration and data/unit resets.
            self._refresh_plot_caption()
        finally:
            self._switching_plot = False
