"""Presentation-only figure styling; never changes analytical coordinates."""

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path

import matplotlib as mpl
from matplotlib.text import Text
import numpy as np

from .figure_presentation import apply_figure_title, align_figure_colorbars, prepare_figure_title
from .colour_scales import normalize_colourbar_labels, register_colour_scales
from .plot_legends import LEGEND_POSITIONS, OUTSIDE_POSITIONS


@dataclass
class PlotStyle:
    font_family: str = 'Original'
    font_size: float = 10
    title_size: float = 14
    label_size: float = 11
    tick_size: float = 9
    legend_size: float = 9
    font_weight: str = 'normal'
    font_style: str = 'normal'
    text_color: str = '#243447'
    figure_color: str = '#ffffff'
    axes_color: str = '#ffffff'
    grid: str = 'Original'
    grid_color: str = '#cbd5e1'
    grid_width: float = 0.6
    border_width: float = 0.8
    border_color: str = 'Original'
    legend: str = 'Original'
    cmap: str = 'Original'
    normalize_cmap: bool = False
    size_mode: str = 'Original'
    width: float = 9
    height: float = 6
    transparent: bool = False
    tight: bool = True
    title: str = ''
    x_label: str = ''
    y_label: str = ''
    z_label: str = ''
    colorbar_label: str = ''
    x_rotation: str = 'Original'
    y_rotation: str = 'Original'
    title_weight: str = 'Original'
    title_style: str = 'Original'
    title_position: str = 'Original'
    title_visible: bool = True
    reference_note_visible: bool = True
    top_right_spines: bool = True
    colorbar_visible: bool = True
    x_limits: str = ''
    y_limits: str = ''
    z_limits: str = ''
    x_ticks: str = ''
    y_ticks: str = ''
    z_ticks: str = ''
    x_tick_format: str = ''
    y_tick_format: str = ''
    z_tick_format: str = ''
    x_tick_divisor: str = ''
    y_tick_divisor: str = ''
    layout_padding: str = ''
    three_d_bounds: str = ''
    x_label_visible: bool = True
    y_label_visible: bool = True
    z_label_visible: bool = True
    colorbar_label_size: str = ''
    colorbar_tick_size: str = ''
    legend_columns: str = ''
    legend_frame: str = 'Original'
    legend_anchor: str = ''
    legend_hidden_entries: list[str] = field(default_factory=list)

    def validate(self):
        from .observation_options import numbers
        if (not isinstance(self.legend_hidden_entries, list)
                or any(not isinstance(label, str) for label in self.legend_hidden_entries)):
            raise ValueError('Hidden legend entries must be a list of labels.')
        if self.legend_frame not in ('Original','Show','Hide'):
            raise ValueError('Invalid legend frame choice.')
        if self.legend_columns and (not self.legend_columns.isdigit() or not 1 <= int(self.legend_columns) <= 12):
            raise ValueError('Legend columns must be an integer between 1 and 12.')
        if self.legend_anchor:
            numbers(self.legend_anchor,2)
        for key in ('colorbar_label_size','colorbar_tick_size'):
            if getattr(self,key) and not 4 <= numbers(getattr(self,key),1)[0] <= 48:
                raise ValueError('Colourbar font sizes must be between 4 and 48 pt.')
        for name in ('title_visible', 'reference_note_visible', 'top_right_spines', 'colorbar_visible'):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(name + ' must be boolean.')
        for dimension in ('x', 'y', 'z'):
            limits = getattr(self, dimension + '_limits')
            ticks = getattr(self, dimension + '_ticks')
            if limits:
                low, high = numbers(limits, 2)
                if low >= high:
                    raise ValueError('Axis minimum must be less than maximum.')
            if ticks:
                numbers(ticks)
            fmt = getattr(self, dimension + '_tick_format')
            if fmt:
                try:
                    format(1.234, fmt)
                except (ValueError, TypeError) as exc:
                    raise ValueError('Tick format must be a numeric format such as .2f or g.') from exc
        for name in ('x_tick_divisor', 'y_tick_divisor'):
            if getattr(self, name):
                divisor = numbers(getattr(self, name), 1)[0]
                if divisor <= 0:
                    raise ValueError('Tick divisor must be positive.')
        if self.layout_padding and not 0 <= numbers(self.layout_padding, 1)[0] <= 1:
            raise ValueError('Layout padding must be between 0 and 1 inch.')
        if self.three_d_bounds:
            left, bottom, right, top = numbers(self.three_d_bounds, 4)
            if not (0 <= left < right <= 1 and 0 <= bottom < top <= 1):
                raise ValueError('3D plot bounds must be ordered left, bottom, right, top between 0 and 1.')
        register_colour_scales()
        for name in ('font_size', 'title_size', 'label_size', 'tick_size', 'legend_size'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or not 4 <= value <= 48:
                raise ValueError(f'{name} must be between 4 and 48 points.')
        for name in ('grid_width', 'border_width'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or not 0.1 <= value <= 5:
                raise ValueError(f'{name} must be between 0.1 and 5 points.')
        for name in ('width', 'height'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or not 2 <= value <= 24:
                raise ValueError('Figure dimensions must be between 2 and 24 inches.')
        for name in ('text_color', 'figure_color', 'axes_color', 'grid_color'):
            if not mpl.colors.is_color_like(getattr(self, name)):
                raise ValueError(f'Invalid {name}.')
        if self.border_color != 'Original' and not mpl.colors.is_color_like(self.border_color):
            raise ValueError('Invalid border color.')
        if self.grid not in ('Original', 'Show', 'Hide') or self.size_mode not in ('Original', 'Custom'):
            raise ValueError('Invalid grid or size mode.')
        if self.legend not in LEGEND_POSITIONS:
            raise ValueError('Invalid legend position.')
        if self.cmap != 'Original' and self.cmap not in mpl.colormaps:
            raise ValueError('Unknown color map.')
        if not isinstance(self.normalize_cmap, bool):
            raise ValueError('Colour-scale normalization must be boolean.')
        if self.font_weight not in ('normal', 'bold') or self.font_style not in ('normal', 'italic'):
            raise ValueError('Invalid font weight or style.')
        if self.title_weight not in ('Original', 'normal', 'bold') or self.title_style not in ('Original', 'normal', 'italic'):
            raise ValueError('Invalid title weight or style.')
        if self.title_position not in ('Original', 'Left', 'Center', 'Right'):
            raise ValueError('Invalid title position.')
        for name in ('x_rotation', 'y_rotation'):
            if getattr(self, name) not in ('Original', '0', '30', '45', '60', '90'):
                raise ValueError('Invalid tick-label rotation.')
        for name in ('x_label', 'y_label', 'z_label', 'colorbar_label'):
            if not isinstance(getattr(self, name), str):
                raise ValueError('Axis and colorbar labels must be text.')
        if not isinstance(self.font_family, str) or not isinstance(self.title, str):
            raise ValueError('Font and title must be text.')
        if not isinstance(self.transparent, bool) or not isinstance(self.tight, bool):
            raise ValueError('Transparency and tight-crop settings must be boolean.')
        return self

    def save(self, path):
        self.validate()
        Path(path).write_text(json.dumps({'format': 'aquaprov-style', 'version': 1,
                                        'settings': asdict(self)}, indent=2), encoding='utf-8')

    @classmethod
    def load(cls, path):
        payload = json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(payload, dict) or payload.get('format') not in ('aquaprov-style', 'aquastat-style') or payload.get('version') != 1:
            raise ValueError('Not a supported AquaProv style preset.')
        try:
            return cls(**payload['settings']).validate()
        except (TypeError, KeyError) as exc:
            raise ValueError('Invalid style preset fields.') from exc

    def apply(self, figure):
        self.validate()
        from .plot_legends import prepare_figure_legends, prepare_legend_position
        prepare_figure_legends(figure)
        shared_legend = prepare_legend_position(figure, self.legend)
        prepare_figure_title(figure)
        has_three_d = any(hasattr(axis, 'get_proj') for axis in figure.axes)
        if has_three_d:
            if not hasattr(figure, '_aquaprov_3d_original_bounds'):
                figure._aquaprov_3d_original_bounds = {
                    name: getattr(figure.subplotpars, name) for name in ('left', 'bottom', 'right', 'top')}
            if (getattr(figure, '_aquaprov_3d_bounds_override', False)
                    or getattr(figure, '_aquaprov_3d_title_bounds', False)):
                figure.subplots_adjust(**figure._aquaprov_3d_original_bounds)
        if not hasattr(figure, '_aquaprov_original_size'):
            figure._aquaprov_original_size = tuple(figure.get_size_inches())
        figure.set_size_inches((self.width, self.height) if self.size_mode == 'Custom'
                               else figure._aquaprov_original_size, forward=False)
        figure.set_facecolor(self.figure_color)
        from matplotlib.layout_engine import ConstrainedLayoutEngine
        engine = figure.get_layout_engine()
        if isinstance(engine, ConstrainedLayoutEngine):
            if not hasattr(engine, '_aquaprov_padding'):
                engine._aquaprov_padding = {k:engine.get()[k] for k in ('w_pad','h_pad')}
            engine.set(**({'w_pad':float(self.layout_padding),'h_pad':float(self.layout_padding)}
                          if self.layout_padding else engine._aquaprov_padding))
        # Selecting a font family enables typography overrides. Until then,
        # preserve the original sizes and annotation colours.
        for text in figure.findobj(Text):
            if text.get_gid() == 'aquaprov-reference-note':
                text.set_visible(self.reference_note_visible)
                text.set_in_layout(self.reference_note_visible)
            if not hasattr(text, '_aquaprov_original_font'):
                text._aquaprov_original_font = (text.get_fontproperties().copy(), text.get_color())
            if self.font_family == 'Original':
                properties, color = text._aquaprov_original_font
                text.set_fontproperties(properties)
                text.set_color(color)
            else:
                text.set_fontfamily(self.font_family)
                text.set_fontsize(self.font_size)
                text.set_fontweight(self.font_weight)
                text.set_fontstyle(self.font_style)
            if hasattr(text, '_aquaprov_annotation_style'):
                text.update(text._aquaprov_annotation_style)
            if hasattr(text, '_aquaprov_cell_fontsize'):
                text._aquaprov_cell_fontsize = text.get_fontsize()
            if hasattr(text, '_aquaprov_point_fontsize'):
                text._aquaprov_point_fontsize = text.get_fontsize()
            if hasattr(text, '_aquaprov_piper_fontsize'):
                text._aquaprov_piper_fontsize = text.get_fontsize()
            if hasattr(text, '_aquaprov_bounded_fontsize'):
                text._aquaprov_bounded_fontsize = text.get_fontsize()
        for axis in figure.axes:
            is_colorbar = axis.get_label() == '<colorbar>'
            if is_colorbar:
                axis.set_visible(self.colorbar_visible)
            if not is_colorbar:
                from matplotlib.ticker import FixedLocator, FuncFormatter
                from .observation_options import numbers
                for dimension in ('x', 'y', 'z'):
                    component = getattr(axis, dimension + 'axis', None)
                    if component is None:
                        continue
                    if not hasattr(component, '_aquaprov_axis_settings'):
                        component._aquaprov_axis_settings = (
                            getattr(axis, 'get_' + dimension + 'lim')(),
                            component.get_major_locator(), component.get_major_formatter())
                    original_limits, locator, formatter = component._aquaprov_axis_settings
                    limits = getattr(self, dimension + '_limits')
                    ticks = getattr(self, dimension + '_ticks')
                    fmt = getattr(self, dimension + '_tick_format')
                    divisor = float(getattr(self, dimension + '_tick_divisor', '') or 1)
                    component.set_major_locator(FixedLocator(numbers(ticks)) if ticks else locator)
                    component.set_major_formatter(FuncFormatter(lambda value, pos, f=fmt or 'g', d=divisor: format(value / d, f))
                                                  if fmt or divisor != 1 else formatter)
                    if limits or getattr(component, '_aquaprov_limit_override', False):
                        getattr(axis, 'set_' + dimension + 'lim')(numbers(limits, 2) if limits else original_limits)
                    component._aquaprov_limit_override = bool(limits)
                for name in ('top', 'right'):
                    if name in axis.spines:
                        spine = axis.spines[name]
                        if not hasattr(spine, '_aquaprov_visible'):
                            spine._aquaprov_visible = spine.get_visible()
                        spine.set_visible(spine._aquaprov_visible and self.top_right_spines)
            for dimension in ('x', 'y', 'z'):
                component = getattr(axis, dimension + 'axis', None)
                if component is None:
                    continue
                if not hasattr(component, '_aquaprov_label'):
                    component._aquaprov_label = component.label.get_text()
                override = '' if is_colorbar else getattr(self, dimension + '_label')
                if is_colorbar and getattr(axis, '_colorbar', None) is not None:
                    active_dimension = 'y' if axis._colorbar.orientation == 'vertical' else 'x'
                    override = self.colorbar_label if dimension == active_dimension else ''
                component.label.set_text(override or component._aquaprov_label)
                if not is_colorbar:
                    component.label.set_visible(getattr(self,dimension+'_label_visible'))
                rotation = getattr(self, dimension + '_rotation', 'Original')
                for tick in component.get_ticklabels():
                    if not hasattr(tick, '_aquaprov_rotation'):
                        tick._aquaprov_rotation = tick.get_rotation()
                    tick.set_rotation(tick._aquaprov_rotation if rotation == 'Original' else float(rotation))
            axis.set_facecolor(self.axes_color)
            if not hasattr(axis, '_aquaprov_grid'):
                axis._aquaprov_grid = (any(line.get_visible() for line in axis.get_xgridlines()),
                                       any(line.get_visible() for line in axis.get_ygridlines()))
            if not hasattr(axis, '_aquaprov_grid_style'):
                # Retain both the tick defaults (including future ticks after
                # resizing) and existing lines, whose styles may differ.
                axis._aquaprov_grid_style = []
                for component in (axis.xaxis, axis.yaxis):
                    defaults = {key: value for key, value in component._major_tick_kw.items()
                                if key.startswith('grid')}
                    lines = [(tick.gridline, dict(color=tick.gridline.get_color(),
                              linewidth=tick.gridline.get_linewidth(),
                              linestyle=tick.gridline.get_linestyle(),
                              alpha=tick.gridline.get_alpha(), visible=tick.gridline.get_visible()))
                             for tick in component.get_major_ticks()]
                    if lines:
                        for name in ('color', 'linewidth', 'linestyle', 'alpha'):
                            defaults.setdefault('grid_' + name, lines[0][1][name])
                    axis._aquaprov_grid_style.append((defaults, lines))
            if hasattr(axis, 'zaxis'):
                components = (axis.xaxis, axis.yaxis, axis.zaxis)
                if not hasattr(axis, '_aquaprov_3d_grid'):
                    axis._aquaprov_3d_grid = (axis._draw_grid, [dict(part._axinfo['grid']) for part in components])
                visible, original_grid = axis._aquaprov_3d_grid
                # Axes3D.grid ignores styling keywords and forces visibility
                # whenever keywords are supplied; update its grid artists' data.
                axis.grid(visible if self.grid == 'Original' else self.grid == 'Show')
                for component, original in zip(components, original_grid):
                    if self.grid == 'Original':
                        component._axinfo['grid'].update(original)
                    elif self.grid == 'Show':
                        component._axinfo['grid'].update(color=mpl.colors.to_rgba(self.grid_color, .6),
                                                        linewidth=self.grid_width)
                    component.line.set_linewidth(self.border_width)
            elif hasattr(axis, '_aquaprov_custom_grid'):
                custom_grid = axis._aquaprov_custom_grid
                if not hasattr(custom_grid, '_original_show'):
                    custom_grid._original_show = custom_grid.show
                custom_grid.show = custom_grid._original_show if self.grid == 'Original' else self.grid == 'Show'
                axis.grid(False)
            elif self.grid == 'Original':
                for component, (defaults, lines) in zip(
                        (axis.xaxis, axis.yaxis), axis._aquaprov_grid_style):
                    component.set_tick_params(which='major', **defaults)
                    for line, properties in lines:
                        line.set(**properties)
            elif self.grid == 'Show':
                axis.grid(True, color=self.grid_color, linewidth=self.grid_width, alpha=0.6)
            else:
                axis.grid(False)
            for spine in axis.spines.values():
                if not hasattr(spine, '_aquaprov_color'):
                    spine._aquaprov_color = spine.get_edgecolor()
                spine.set_linewidth(self.border_width)
                spine.set_edgecolor(spine._aquaprov_color if self.border_color=='Original' else self.border_color)
            if self.font_family != 'Original':
                axis.title.set_color(self.text_color)
                for name in ('xaxis', 'yaxis', 'zaxis'):
                    component = getattr(axis, name, None)
                    if component is not None:
                        component.label.set_fontsize(self.label_size)
                        component.label.set_color(self.text_color)
                        for text in component.get_ticklabels():
                            text.set_fontsize(self.tick_size)
                            text.set_color(self.text_color)
            legend = axis.get_legend()
            if legend is not None:
                self._position_legend(legend, axis.transAxes, shared_legend)
                if self.font_family != 'Original':
                    for text in legend.get_texts():
                        text.set_fontsize(self.legend_size)
                        text.set_color(self.text_color)
                self._legend_details(legend,axis.transAxes)
                for text in legend.get_texts():
                    text._aquaprov_legend_fontsize = text.get_fontsize()
            # Keep the colorbar tied to the samples' colour mapping.
            artists = [] if axis.get_label() == '<colorbar>' else [*axis.images, *axis.collections]
            if legend is not None:
                # Matplotlib copies scalar-mapped collections into the legend.
                # Recolor those copies along with the plotted samples.
                artists.extend(handle for handle in legend.legend_handles
                               if hasattr(handle, 'get_array'))
            for artist in artists:
                if getattr(artist, '_aquaprov_fixed_cmap', False):
                    continue  # Discrete classes retain their explicitly configured colours.
                if artist.get_array() is not None:
                    if not hasattr(artist, '_aquaprov_cmap'):
                        artist._aquaprov_cmap = artist.get_cmap()
                    artist.set_cmap(artist._aquaprov_cmap if self.cmap == 'Original' else self.cmap)
        for legend in figure.legends:
            self._position_legend(legend, figure.transFigure, shared_legend)
            self._legend_details(legend,figure.transFigure)
            if self.font_family != 'Original':
                for text in legend.get_texts():
                    text.set_fontsize(self.legend_size)
                    text.set_color(self.text_color)
            for text in legend.get_texts():
                text._aquaprov_legend_fontsize = text.get_fontsize()
            for artist in legend.legend_handles:
                if getattr(artist, '_aquaprov_fixed_cmap', False):
                    continue
                if hasattr(artist, 'get_array') and artist.get_array() is not None:
                    if not hasattr(artist, '_aquaprov_cmap'):
                        artist._aquaprov_cmap = artist.get_cmap()
                    artist.set_cmap(artist._aquaprov_cmap if self.cmap == 'Original' else self.cmap)
        from .plot_legends import refresh_scale_keys
        refresh_scale_keys(figure)
        for axis in figure.axes:
            from .plot_layout import TickLabelLayout
            for layout in axis.artists:
                if isinstance(layout, TickLabelLayout):
                    for text in getattr(axis, 'get_' + layout.dimension + 'ticklabels')():
                        text._aquaprov_tick_fontsize = text.get_fontsize()
            if not hasattr(axis, 'get_proj') and len(axis.get_yticks()) >= 20:
                for text in axis.get_yticklabels():
                    text._aquaprov_tick_fontsize = text.get_fontsize()
                if not any(isinstance(artist, TickLabelLayout) and artist.dimension=='y' for artist in axis.artists):
                    TickLabelLayout(axis)
        if getattr(figure, '_aquaprov_3d_legend', False):
            key = figure._aquaprov_outside_legend
            rows = int(np.ceil(len(key.get_texts()) / key._ncols))
            font = self.legend_size if self.font_family != 'Original' else 9
            bottom = (rows * font * 1.6 + 60) / (figure.get_size_inches()[1] * 72)
            # A hidden key must not keep shrinking the 3D plot into the space
            # above it, especially in small saved publication figures.
            figure.subplots_adjust(left=.08, right=.90,
                                   bottom=.12 if not key.get_visible() else max(.20, min(.60, bottom)), top=.88)
        if getattr(figure, '_aquaprov_outside_legend', None) is not None:
            from .plot_layout import prepare_legend_layout, fit_figure_legend
            prepare_legend_layout(figure)
            fit_figure_legend(figure, figure._get_renderer())
        if has_three_d:
            figure._aquaprov_3d_bounds_override = bool(self.three_d_bounds)
            if self.three_d_bounds:
                from .observation_options import numbers
                figure.subplots_adjust(**dict(zip(('left', 'bottom', 'right', 'top'), numbers(self.three_d_bounds, 4))))
        apply_figure_title(figure, self)
        for text in [figure._suptitle, *[t for ax in figure.axes for t in (ax.title, ax._left_title, ax._right_title)]]:
            if text is not None:
                text.set_visible(self.title_visible)
        if has_three_d:
            # Saved compact bounds may reach the top of the page while the
            # title is hidden. Turning it on must reserve space above Axes3D;
            # these axes cannot rely on constrained layout to fit their title.
            figure._aquaprov_3d_title_bounds = False
            heading = figure._aquaprov_heading
            axis = heading.axes
            if self.title_visible and axis is not None and hasattr(axis, 'get_proj'):
                title_height = heading.get_window_extent(figure._get_renderer()).height / figure.dpi
                title_pad = axis.titleOffsetTrans.get_matrix()[1, 2] / figure.dpi
                top = min(figure.subplotpars.top,
                          1 - (title_height + title_pad + 2 / 72) / figure.get_figheight())
                if figure.subplotpars.bottom < top < figure.subplotpars.top:
                    figure.subplots_adjust(top=top)
                    figure._aquaprov_3d_title_bounds = True
        normalize_colourbar_labels(figure, self.normalize_cmap, self.colorbar_label)
        for axis in figure.axes:
            if getattr(axis,'_colorbar',None) is not None:
                if self.colorbar_label_size:
                    axis.xaxis.label.set_fontsize(float(self.colorbar_label_size))
                    axis.yaxis.label.set_fontsize(float(self.colorbar_label_size))
                if self.colorbar_tick_size:
                    axis.tick_params(labelsize=float(self.colorbar_tick_size))
        align_figure_colorbars(figure)
        from .plot_layout import finish_legend_position
        from .plot_legends import connect_legend_dragging
        finish_legend_position(figure, shared_legend)
        connect_legend_dragging(figure)

    def _position_legend(self, legend, transform, shared):
        legend._aquaprov_inside_axis = None
        if not hasattr(legend, '_aquaprov_original'):
            anchor = legend.get_bbox_to_anchor().transformed(transform.inverted())
            legend._aquaprov_original = (legend._loc, anchor.frozen())
            legend._aquaprov_original_outside = legend._outside_loc
        if legend is shared:
            legend.set_bbox_to_anchor(None)
            legend.set_loc(OUTSIDE_POSITIONS[self.legend])
        elif self.legend not in ('Original', 'Hide', *OUTSIDE_POSITIONS):
            legend.set_bbox_to_anchor(None)
            legend.set_loc(self.legend)
            if legend.axes is None:
                axes = [axis for axis in legend.figure.axes if not hasattr(axis, '_colorbar')]
                if len(axes) == 1:
                    legend.set_bbox_to_anchor((0, 0, 1, 1), transform=axes[0].transAxes)
                    legend._aquaprov_inside_axis = axes[0]
                    from .plot_layout import AxesLegendLayout
                    if not any(isinstance(item, AxesLegendLayout) for item in axes[0].artists):
                        AxesLegendLayout(axes[0])
        else:
            location, anchor = legend._aquaprov_original
            legend.set_loc(location)
            legend.set_bbox_to_anchor(anchor, transform=transform)
            legend._outside_loc = getattr(legend, '_aquaprov_original_outside', None)
            if legend._outside_loc is not None:
                legend.set_bbox_to_anchor(None)

    def _legend_details(self, legend, transform):
        if not hasattr(legend,'_aquaprov_details'):
            legend._aquaprov_details = (legend._ncols,legend.get_frame_on(),legend._fontsize)
        columns, frame, original_fontsize = legend._aquaprov_details
        desired = int(self.legend_columns) if self.legend_columns else columns
        fontsize = self.legend_size if self.font_family!='Original' else original_fontsize
        entries = legend._aquaprov_entries
        labels = [label for label in entries if label not in self.legend_hidden_entries]
        if not self.legend_columns and legend is getattr(legend.figure, '_aquaprov_style_outside_legend', None):
            desired = 1
            if self.legend == 'Outside below' and labels:
                width = legend.figure.get_figwidth() * 72
                desired = max(1, min(len(labels), int(width / (40 + max(map(len, labels)) * fontsize * .62))))
        legend.set_visible(self.legend != 'Hide' and bool(labels))
        legend.set_in_layout(legend.get_visible())
        if (legend._ncols != desired or legend._fontsize != fontsize
                or labels != [text.get_text() for text in legend.get_texts()]):
            # Rebuild the packing boxes: set_ncols alone does not repack a live key.
            title = legend.get_title().get_text()
            handles = [entries[label] for label in labels]
            legend.set_ncols(desired)
            legend._fontsize = fontsize
            legend._init_legend_box(handles,labels,markerfirst=True)
            # Repacking creates a new OffsetBox. Reattach its location callback
            # so legend placement remains relative to its axes, including export.
            outside = legend._outside_loc
            legend.set_loc(legend._loc)
            # A numeric Matplotlib location clears the outside flag. Keep the
            # reserved margin when font/column changes rebuild a shared key.
            legend._outside_loc = outside
            legend.set_title(title)
            for text in [legend.get_title(),*legend.get_texts()]:
                text.set_fontsize(fontsize)
                if self.font_family!='Original':
                    text.set_fontfamily(self.font_family)
                    text.set_fontweight(self.font_weight)
                    text.set_fontstyle(self.font_style)
                    text.set_color(self.text_color)
        legend.set_frame_on(frame if self.legend_frame=='Original' else self.legend_frame=='Show')
        if self.legend_anchor:
            from .observation_options import numbers
            legend.set_bbox_to_anchor(numbers(self.legend_anchor,2),transform=transform)

    def export(self, figure, path, dpi):
        # Export dimensions are fixed independently of the resizable Qt canvas.
        self.validate()
        if self.transparent and Path(path).suffix.lower() in ('.jpg', '.jpeg'):
            raise ValueError('JPEG does not support transparency. Choose PNG/PDF/SVG or disable transparency and apply style.')
        size = (self.width, self.height) if self.size_mode == 'Custom' else getattr(figure, '_aquaprov_original_size', figure.get_size_inches())
        if Path(path).suffix.lower() in ('.png', '.jpg', '.jpeg', '.tiff') and size[0] * size[1] * dpi ** 2 > 80_000_000:
            raise ValueError('Raster output exceeds 80 megapixels. Reduce dimensions/DPI or use a vector format.')
        original = figure.get_size_inches().copy()
        try:
            figure.set_size_inches(size, forward=False)
            # Matplotlib's Axes3D tight bounds omit axis labels. Include them
            # explicitly so small figures retain all three labels on export.
            labels = [component.label for axis in figure.axes if hasattr(axis, 'get_proj')
                      for component in (axis.xaxis, axis.yaxis, axis.zaxis)
                      if component.label.get_visible()]
            with mpl.rc_context({'pdf.fonttype': 42, 'svg.fonttype': 'none'}):
                figure.savefig(path, dpi=dpi, transparent=self.transparent,
                               bbox_inches='tight' if self.tight else None,
                               bbox_extra_artists=figure.get_default_bbox_extra_artists() + labels if labels else None)
        finally:
            figure.set_size_inches(original, forward=False)
