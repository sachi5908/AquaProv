"""Small reusable controls for editable reference lines and plot notes."""
from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QLineEdit
from .ui.color_button import ColorButton


def add_fields(w, layout, definitions):
    fields = []
    for name, label, default, *limits in definitions:
        if isinstance(default, list):
            widget = QComboBox(); widget.addItems(default)
        elif isinstance(default, bool):
            widget = QCheckBox(label); widget.setChecked(default)
        elif isinstance(default, (int, float)):
            widget = QDoubleSpinBox(); widget.setDecimals(3)
            widget.setRange(*(limits[0] if limits else (0, 100)))
            widget.setValue(default)
        elif name.endswith('_color_edit'):
            widget = ColorButton(default, allow_auto=not default)
        else:
            widget = QLineEdit(default)
        setattr(w, name, widget)
        if isinstance(widget, QCheckBox):
            layout.addWidget(widget); fields.append(widget)
        else:
            fields.append(w._add_field(layout, label, widget))
    return fields


def build_reference_controls(w, *, x=False, note=False):
    card, layout = w._card('Reference lines and notes', 'These controls change the display. Calculations keep their selected scientific settings.')
    definitions = [
        ('reference_show_check', 'Show reference line(s)', True),
        ('reference_color_edit', 'Reference line colour', '#888888'),
        ('reference_width_spin', 'Reference line width (pt)', .65, (0, 8)),
        ('reference_style_combo', 'Reference line style', ['--', ':', '-', '-.']),
    ]
    add_fields(w, layout, definitions)
    if x:
        add_fields(w, layout, [('reference_x_check', 'Show vertical zero line', True),
                              ('reference_y_check', 'Show horizontal zero line', True)])
    if note:
        add_fields(w, layout, [
            ('note_show_check', 'Show plot note', True),
            ('note_text_edit', 'Note text (blank = automatic; use {n}, {count}, {tolerance})', ''),
            ('note_x_spin', 'Note horizontal position (%)', 3., (0, 100)),
            ('note_y_spin', 'Note vertical position (%)', 95., (0, 100)),
            ('note_align_combo', 'Note alignment', ['left', 'right', 'center']),
            ('note_vertical_combo', 'Note vertical alignment', ['top', 'bottom', 'center']),
            ('note_color_edit', 'Note colour', '#243447'),
            ('note_size_spin', 'Note font size (pt)', 7., (4, 48)),
        ])
        w.note_text_edit.setToolTip('Use \\n for a line break. Automatic counts are recalculated from the data.')
    w.control_tabs.widget(1).widget().layout().insertWidget(2, card)
    w.reference_card = card


def reference_options(w):
    result = dict(show=w.reference_show_check.isChecked(), color=w.reference_color_edit.text(),
                  width=w.reference_width_spin.value(), linestyle=w.reference_style_combo.currentText())
    if hasattr(w, 'reference_x_check'):
        result['x'] = w.reference_x_check.isChecked()
        result['y'] = w.reference_y_check.isChecked()
    if hasattr(w, 'note_show_check'):
        result['note'] = dict(show=w.note_show_check.isChecked(), text=w.note_text_edit.text(),
            x=w.note_x_spin.value()/100, y=w.note_y_spin.value()/100,
            ha=w.note_align_combo.currentText(), va=w.note_vertical_combo.currentText(),
            color=w.note_color_edit.text(), size=w.note_size_spin.value())
    return result
