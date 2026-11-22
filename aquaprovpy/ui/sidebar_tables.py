"""Place module data and results in the inspector without duplicating tables."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QHeaderView


def _configure_table(table, name, height):
    table.setProperty('sidebarTable', True)
    table.setAccessibleName(name)
    table.setMinimumWidth(0)
    table.setFixedHeight(height)
    table.setAlternatingRowColors(True)
    table.setWordWrap(False)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    table.horizontalHeader().setMinimumSectionSize(58)
    table.horizontalHeader().setStretchLastSection(False)
    table.verticalHeader().setVisible(True)
    table.verticalHeader().setDefaultSectionSize(26)


def dock_sidebar_tables(workspace):
    """Move data and result widgets into the inspector, keeping their connections."""
    _configure_table(workspace.table, 'Imported dataset', 300)
    workspace.table_info.setWordWrap(True)
    dataset = workspace.import_button.parentWidget().layout()
    dataset.addWidget(workspace.table)
    dataset.addWidget(workspace.table_info)

    workspace.sidebar_results_card, results = workspace._card('Results & methods')
    _configure_table(workspace.result_table, 'Analysis results', 240)
    workspace.result_combo.setAccessibleName('Choose a result table')
    for control in (workspace.result_combo, workspace.result_table, workspace.result_notes,
                    workspace.results_format_field, workspace.tables_button):
        results.addWidget(control)
    export = workspace.control_tabs.widget(3).widget().layout()
    export.insertWidget(export.count() - 1, workspace.sidebar_results_card)

    def sync_results(*_):
        available = workspace.result_combo.count() > 0
        workspace.result_combo.setVisible(available)
        workspace.result_table.setVisible(available)

    model = workspace.result_combo.model()
    for signal in (model.rowsInserted, model.rowsRemoved, model.modelReset):
        signal.connect(sync_results)
    sync_results()
