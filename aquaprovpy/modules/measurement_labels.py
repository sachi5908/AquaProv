"""Discard measurement-specific presentation overrides after a source change."""
import re


def bind_measurement_labels(workspace, combo, *, dimensions=(), colorbar=True):
    previous = combo.currentText()

    def changed(column):
        nonlocal previous
        old, previous = previous, column
        if (not old or not column or old == column or workspace._restoring
                or getattr(workspace, '_switching_plot', False)
                or getattr(workspace, '_updating_data', False)):
            return
        for dimension in dimensions:
            for suffix in ('label', 'limits', 'ticks', 'tick_format', 'tick_divisor'):
                workspace.style_controls[dimension + '_' + suffix].clear()
        if colorbar:
            workspace.style_controls['colorbar_label'].clear()
        title = workspace.style_controls['title']
        if re.search(r'(?<!\w)' + re.escape(old) + r'(?!\w)', title.text()):
            title.clear()

    combo.currentTextChanged.connect(changed)


def bind_scale_label(workspace, combo):
    """A saved log-scale caption cannot describe a subsequently linear scale."""
    def changed(*_):
        if workspace._restoring or getattr(workspace, '_switching_plot', False):
            return
        label = workspace.style_controls['colorbar_label']
        if re.search(r'\b(log(?:arithmic)?|linear)\s+scale\b', label.text(), re.I):
            label.clear()
    combo.currentIndexChanged.connect(changed)
