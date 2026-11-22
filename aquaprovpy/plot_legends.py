"""Discover complete plot keys and retain their entries when users hide them."""
from matplotlib.legend import Legend
from matplotlib.lines import Line2D
from matplotlib.patches import Patch


OUTSIDE_POSITIONS = {'Outside right': 'outside right upper',
                     'Outside below': 'outside lower center'}
LEGEND_POSITIONS = ('Original', 'Hide', *OUTSIDE_POSITIONS,
                    'upper right', 'upper left', 'lower right', 'lower left',
                    'center right', 'center left')


def connect_legend_dragging(figure):
    """Repair handlers after worker rendering or replacement of packing boxes."""
    for legend in figure.findobj(Legend):
        if not legend.get_visible():
            legend.set_draggable(False)
            continue
        helper = legend._draggable
        if helper is not None:
            connected = all(cid in figure.canvas.callbacks.callbacks.get(event, {})
                            for event, cid in zip(('pick_event', 'button_release_event'), helper.cids))
            if helper.offsetbox is not legend._legend_box or not connected:
                legend.set_draggable(False)
        legend.set_draggable(True)


def prepare_legend_position(figure, position):
    """Create a reversible shared key when an outside position is selected."""
    from .plot_layout import ManualLegendLayoutEngine
    engine = figure.get_layout_engine()
    if isinstance(engine, ManualLegendLayoutEngine):
        engine.restore(figure)
    shared = getattr(figure, '_aquaprov_style_outside_legend', None)
    if shared is not None:
        if position in OUTSIDE_POSITIONS:
            return shared
        shared.set_draggable(False)
        shared.remove()
        figure._aquaprov_style_outside_legend = None
    if position not in OUTSIDE_POSITIONS:
        return None
    entries, handlers = {}, {}
    title = ''
    for legend in figure.findobj(Legend):
        entries.update(legend._aquaprov_entries)
        handlers.update(legend.get_legend_handler_map())
        title = title or legend.get_title().get_text()
    if not entries:
        return None
    shared = figure.legend(list(entries.values()), list(entries), title=title or None,
                           loc=OUTSIDE_POSITIONS[position], frameon=False, fontsize=9,
                           handler_map=handlers)
    shared._aquaprov_entries = entries
    figure._aquaprov_style_outside_legend = shared
    return shared


def add_legend_entries(axis, handles):
    """Register semantic keys for artists without a native legend handler."""
    entries = getattr(axis, '_aquaprov_legend_entries', {})
    for handle in handles:
        entries.setdefault(handle.get_label(), handle)
    axis._aquaprov_legend_entries = entries


def box_legend(axis, artists):
    for key, label in (('boxes', 'Interquartile range (25–75%)'),
                       ('medians', 'Median'), ('whiskers', 'Whiskers (within 1.5 IQR)'),
                       ('fliers', 'Outliers')):
        values = artists.get(key, [])
        if values and (key != 'fliers' or any(len(item.get_xdata()) for item in values)):
            values[0].set_label(label)


def violin_legend(axis, artists):
    for key, label in (('bodies', 'Distribution density'), ('cmedians', 'Median'),
                       ('cmins', 'Minimum / maximum'), ('cbars', 'Observed range')):
        value = artists.get(key)
        if value is not None:
            (value[0] if isinstance(value, list) else value).set_label(label)


def scale_legend(axis, artist, label):
    """A representative swatch; the colourbar retains the numeric scale."""
    handle = Patch(facecolor=artist.get_cmap()(.5), label=label)
    handle._aquaprov_scale_source = artist
    add_legend_entries(axis, [handle])


def contour_legend(axis, artist, label='Contour lines'):
    color = artist.get_edgecolor()[0]
    add_legend_entries(axis, [Line2D([], [], color=color, linewidth=artist.get_linewidth()[0], label=label)])


def _axis_entries(axis):
    handles, labels = axis.get_legend_handles_labels()
    entries = dict(zip(labels, handles))
    entries.update(getattr(axis, '_aquaprov_legend_entries', {}))
    return entries


def prepare_figure_legends(figure):
    """Include labelled artists as well as explicitly supplied legend proxies."""
    from ._diagram_colors import _SampleLegendHandler
    from matplotlib.collections import PathCollection
    handler_map = {PathCollection: _SampleLegendHandler()}
    axes = [axis for axis in figure.axes if not hasattr(axis, '_colorbar')]
    legends = list(figure.findobj(Legend))
    shared = getattr(figure, '_aquaprov_outside_legend', None)
    if shared is None and len(figure.legends) == 1:
        shared = figure.legends[0]
    for legend in legends:
        if not hasattr(legend, '_aquaprov_entries'):
            legend._aquaprov_entries = dict(zip(
                (text.get_text() for text in legend.get_texts()), legend.legend_handles))
        # Existing proxies take precedence over raw artists (e.g. hatch keys).
        sources = axes if legend is shared else ([legend.axes] if legend.axes is not None else [])
        added = False
        for axis in sources:
            for label, handle in _axis_entries(axis).items():
                added |= label not in legend._aquaprov_entries
                legend._aquaprov_entries.setdefault(label, handle)
        legend.get_legend_handler_map().update(handler_map)
        if added:
            title = legend.get_title().get_text()
            outside = legend._outside_loc
            legend._init_legend_box(list(legend._aquaprov_entries.values()),
                                   list(legend._aquaprov_entries), markerfirst=True)
            legend.set_loc(legend._loc)
            legend._outside_loc = outside
            legend.set_title(title)
    if shared is not None:
        return
    for axis in axes:
        if axis.get_legend() is not None:
            legend = axis.get_legend()
        else:
            entries = _axis_entries(axis)
            if not entries:
                continue
            legend = axis.legend(list(entries.values()), list(entries), frameon=False,
                                 loc='upper right' if hasattr(axis, 'get_proj') else 'best',
                                 handler_map=handler_map)
            legend._aquaprov_entries = entries
        from .plot_layout import AxesLegendLayout
        if not any(isinstance(item, AxesLegendLayout) for item in axis.artists):
            AxesLegendLayout(axis)


def available_legend_labels(figures):
    """Read the full inventory, including currently hidden entries and keys."""
    labels = {}
    for figure in figures:
        for legend in figure.findobj(Legend):
            entries = getattr(legend, '_aquaprov_entries', None)
            for label in entries if entries is not None else (t.get_text() for t in legend.get_texts()):
                labels.setdefault(label, None)
    return list(labels)


def refresh_scale_keys(figure):
    """Keep scale swatches in step with presentation palette changes."""
    for legend in figure.findobj(Legend):
        entries = legend._aquaprov_entries
        for handle, text in zip(legend.legend_handles, legend.get_texts()):
            original = entries[text.get_text()]
            source = getattr(original, '_aquaprov_scale_source', None)
            if source is not None:
                color = source.get_cmap()(.5)
                original.set_facecolor(color)
                handle.set_facecolor(color)
