"""Colourbar placement controls shared by native sample maps."""
from ...chart_controls import add_fields


def build(w, layout):
    w.map_colorbar_orientation_combo.addItem('Left of map', 'left')
    w.map_colorbar_orientation_combo.addItem('Above map', 'top')
    w._colorbar_fields = add_fields(w, layout, [
        ('map_colorbar_gap_spin', 'Colour scale gap (pt)', 6., (0,36)),
        ('map_colorbar_width_spin', 'Colour scale thickness (pt)', 6., (1,24)),
        ('map_colorbar_length_spin', 'Colour scale length (% of plot)', 100., (10,100)),
        ('map_colorbar_anchor_spin', 'Short scale alignment (0=start, 100=end)', 50., (0,100)),
    ])


def options(w):
    return dict(gap=w.map_colorbar_gap_spin.value(), width=w.map_colorbar_width_spin.value(),
                length=w.map_colorbar_length_spin.value()/100, anchor=w.map_colorbar_anchor_spin.value()/100)


def bind_style(w, show_control):
    """Keep duplicate analysis/style switches in agreement during user edits."""
    style_show = w.style_controls['colorbar_visible']
    style_grid = w.style_controls['grid']
    def user_edit():
        return not w._restoring and not getattr(w,'_switching_plot',False)
    show_control.toggled.connect(lambda checked: style_show.setChecked(checked) if user_edit() else None)
    style_show.toggled.connect(lambda checked: show_control.setChecked(checked) if user_edit() else None)
    w.map_grid_check.toggled.connect(lambda checked: style_grid.setCurrentText('Show' if checked else 'Hide') if user_edit() else None)
    style_grid.currentTextChanged.connect(lambda text: w.map_grid_check.setChecked(text=='Show') if user_edit() and text!='Original' else None)
