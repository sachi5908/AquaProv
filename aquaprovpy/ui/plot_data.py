"""Report missing-sample exclusions after the completed plot is visible."""
from collections import Counter

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from ..core.plot_data import complete_samples
from ..core.progress import progress_stage
from .loading import run_worker


class PlotDataMixin:
    def _prepare_plot_data(self, frame, numeric_columns, *, text_columns=(), missing='drop', numeric_groups=None):
        with progress_stage(2, 18, 'Checking required measurements'):
            prepared, self._plot_data_report = run_worker(lambda: complete_samples(
                frame, numeric_columns, text_columns=text_columns, missing=missing, numeric_groups=numeric_groups))
        prepared.attrs['plot_input_filter'] = self._plot_data_report
        return prepared

    def _begin_plot_data_report(self):
        self._dismiss_missing_notice()
        self._plot_data_report = None

    def _attach_plot_data_report(self):
        report = self._plot_data_report
        if report and report.get('groups'):
            groups = report['groups']
            summary = '; '.join(f'{name}: n = {group["n_available"]}' for name, group in groups.items())
            self.plot_details.setText(self.plot_details.text() + '\n' + summary)
            for figure in self.plot_figures:
                figure._aquaprov_input_filter = report
        if not report or not report['excluded_samples']:
            return
        rows = report['excluded_samples']
        summary = f'Excluded {len(rows)} of {report["n_input"]} samples with missing or unusable values in the required columns.'
        for figure in self.plot_figures:
            figure._aquaprov_input_filter = report
        result = self.analysis_result
        if result is not None:
            positions = report['used_row_positions_1based']
            # Engines receive only complete samples. Map their positional audit
            # fields back to the original input before exporting methods/tables.
            for key in ('excluded_row_positions_1based', 'excluded_sample_rows_1based'):
                if key in result.metadata:
                    result.metadata[key] = [positions[i - 1] for i in result.metadata[key]]
            result.metadata['n_input'] = report['n_input']
            result.metadata['input_filter'] = report
            result.metadata['excluded_row_positions_1based'] = sorted(set(
                result.metadata.get('excluded_row_positions_1based', []) + [row['data_row'] for row in rows]))
            if result.metadata.get('method') == 'observed time series':
                table = result.tables['observations']
                table['source_row_position'] = table['source_row_position'].map(lambda i: positions[int(i) - 1])
            elif result.metadata.get('method') == 'iid percentile bootstrap':
                table = result.tables['analysis_data']
                table.index = pd.Index([positions[int(i) - 1] for i in table.index], name=table.index.name)
            elif result.metadata.get('method') == 'Ward minimum variance':
                table = result.tables['membership']
                table['input_row_position'] = table['input_row_position'].map(lambda i: positions[int(i) - 1])
            result.tables['excluded_samples'] = pd.DataFrame([
                dict(row, missing_columns=', '.join(row['missing_columns']),
                     invalid_columns=', '.join(row['invalid_columns'])) for row in rows])
            result.warnings.append(summary)
            self.result_combo.addItem('excluded_samples')
            self.result_notes.setText('\n'.join(result.warnings))
        self.statusBar().showMessage(summary)

    def _show_missing_notice(self):
        report = getattr(self, '_plot_data_report', None)
        if not report or not self.isVisible():
            return
        rows = report['excluded_samples'] + report.get('partial_samples', [])
        if not rows:
            return
        signature = (getattr(self, '_active_plot', self.diagram_combo.currentText()),
                     repr(report))
        if getattr(self, '_auto_updating', False) and signature == getattr(self, '_last_missing_notice', None):
            return
        self._last_missing_notice = signature
        counts = Counter(column for row in rows for column in row['missing_columns'] + row['invalid_columns'])
        details = []
        for row in rows:
            reasons = []
            if row['missing_columns']:
                reasons.append('missing: ' + ', '.join(row['missing_columns']))
            if row['invalid_columns']:
                reasons.append('non-numeric or non-finite: ' + ', '.join(row['invalid_columns']))
            details.append(f"{row['sample']} (data row {row['data_row']}, source index {row['source_index']}): " + '; '.join(reasons))
        notice = QMessageBox(self.window())
        notice.setObjectName('missingSamplesNotice')
        notice.setWindowTitle('Plot created — samples excluded')
        notice.setIcon(QMessageBox.Icon.Information)
        notice.setTextFormat(Qt.TextFormat.PlainText)
        result = self.analysis_result
        n_used = result.metadata.get('n_used', report['n_available']) if result is not None else report['n_available']
        excluded_count = len(report['excluded_samples'])
        message = f'Plot created using n = {n_used} samples.\n\n{excluded_count} of {report["n_input"]} samples were ignored because required values were missing or unusable.'
        if report.get('partial_samples'):
            notice.setWindowTitle('Plot created — available measurements')
            message += (f'\n{len(report["partial_samples"])} samples contribute to the panels or ions with available measurements. '
                        'Missing measurements are omitted from the other panels or shown as gaps.')
            message += '\n\n' + '; '.join(f'{name}: n = {group["n_available"]}'
                                          for name, group in report['groups'].items())
        notice.setText(message)
        notice.setInformativeText('Affected columns: ' + ', '.join(f'{column} ({count})' for column, count in counts.items()) +
                                 '\n\nSamples: ' + ', '.join(row['sample'] for row in rows[:12]) +
                                 (' …' if len(rows) > 12 else '') + '\nYour original dataset has not been changed.')
        notice.setDetailedText('\n'.join(details))
        notice.setStandardButtons(QMessageBox.StandardButton.Ok)
        notice.setWindowModality(Qt.WindowModality.NonModal)
        notice.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        notice.finished.connect(lambda *_: setattr(self, '_missing_notice', None))
        self._missing_notice = notice
        notice.show()

    def _dismiss_missing_notice(self):
        notice = getattr(self, '_missing_notice', None)
        if notice is not None:
            self._missing_notice = None
            notice.close()

    def hideEvent(self, event):
        self._dismiss_missing_notice()
        super().hideEvent(event)
