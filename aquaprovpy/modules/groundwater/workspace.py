"""Groundwater chemistry, irrigation and contamination exploration workspace."""
from ..base import ModuleWorkspace
from ...core.catalog import GROUNDWATER_DIAGRAMS
from ...core.diagram_inputs import diagram_availability
from ...ui.loading import run_worker
from ...core.progress import progress_stage


class GroundwaterWorkspace(ModuleWorkspace):
    module_key = "groundwater"

    def __init__(self):
        super().__init__()
        self.configure_diagrams(GROUNDWATER_DIAGRAMS)
        self.hide_locations()
        self.run_note.setText("Import water analyses, choose a geochemical diagram, then Generate.")
        self.connect_settings()

    def populate_module_columns(self):
        data = self.data
        with progress_stage(70, 95, 'Checking available diagrams'):
            self._input_availability = run_worker(lambda: diagram_availability(data))
        current = self._active_plot
        if not self._input_availability[current][0]:
            # Prefer one overview figure after import over hundreds of individual
            # sample figures. Saved plot settings are restored by the shell later.
            available = [name for name in GROUNDWATER_DIAGRAMS
                         if self._input_availability[name][0] and name not in ('Stiff', 'Chernoff face')]
            if available:
                restoring = self._restoring
                ec_unit = self.ec_unit_combo.currentText()
                try:
                    self.select_plot(available[0])
                finally:
                    self.ec_unit_combo.setCurrentText(ec_unit)
                    self._restoring = restoring
        self._refresh_input_status()

    def _refresh_input_status(self):
        availability = getattr(self, '_input_availability', {})
        if not availability:
            return
        for choice in self._choices:
            ready, detail = availability[choice.key]
            item = self.plot_browser.items[choice.key]
            suffix = ' · needs subset' if 'at most 100' in detail else ' · needs data'
            item.setText(0, choice.title if ready else choice.title + suffix)
            item.setToolTip(0, choice.description + '\n\n' + detail)
        ready, detail = availability[self._active_plot]
        choice = next(choice for choice in self._choices if choice.key == self._active_plot)
        if not ready:
            alternatives = [name for name, (usable, _) in availability.items() if usable]
            if alternatives:
                detail += ' Available plots: ' + ', '.join(alternatives) + '.'
            detail = 'Dataset loaded. ' + detail
        self.plot_description.setText(choice.description + '\n' + detail)

    def _report_plot_error(self, title, error):
        availability = getattr(self, '_input_availability', {})
        current = availability.get(self._active_plot)
        if current and not current[0]:
            alternatives = [name for name, (usable, _) in availability.items() if usable]
            if alternatives:
                error = ValueError(str(error) + '\n\nThe dataset is loaded. Available plots: ' + ', '.join(alternatives) + '.')
        super()._report_plot_error(title, error)
