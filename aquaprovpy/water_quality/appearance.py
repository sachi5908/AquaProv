"""Point symbols and independently styled site labels for index figures."""
from textwrap import fill

from matplotlib.colors import is_color_like
from matplotlib.patheffects import withStroke
import numpy as np

from ..plot_layout import point_labels


LABEL_DEFAULTS = dict(content='both',color='#26394d',size=7.,font_family=None,
                      bold=False,italic=False,decimals=2,wrap=22,leaders=True,halo=True)


def label_options(config):
    options = {**LABEL_DEFAULTS, **config.get('point_label_style', {})}
    if options['content'] not in ('both','site','value','class'):
        raise ValueError('Choose site names, index values, both, or site classifications for point labels.')
    if not is_color_like(options['color']):
        raise ValueError('Choose a valid point-label colour.')
    if not isinstance(options['size'], (int,float)) or not np.isfinite(options['size']) or not 4 <= options['size'] <= 32:
        raise ValueError('Point-label size must be between 4 and 32 points.')
    for name,low,high in [('decimals',0,6),('wrap',8,60)]:
        if not isinstance(options[name],int) or not low <= options[name] <= high:
            raise ValueError(f'Point-label {name} must be an integer between {low} and {high}.')
    if options['font_family'] is not None and not isinstance(options['font_family'],str):
        raise ValueError('Choose a point-label font family.')
    return options


def uses_scale_colors(config):
    mode = config.get('point_color_mode','auto')
    if mode not in ('auto','single','scale'):
        raise ValueError('Choose automatic, single-colour or map-scale point colours.')
    return mode == 'scale' or (mode == 'auto' and config.get('view') == 'samples')


def sample_appearance(config, values, cmap, norm):
    """A single-colour overlay must never be remapped by a surface colormap."""
    scaled = uses_scale_colors(config)
    color = config.get('color','#2878a5')
    edge = config.get('sample_edgecolor','#26384a')
    size,alpha,width = config.get('sample_size',38),config.get('sample_alpha',.8),config.get('sample_linewidth',.5)
    if not is_color_like(color) or not is_color_like(edge):
        raise ValueError('Choose valid point fill and outline colours.')
    if not np.isfinite([size,alpha,width]).all() or not (size>0 and 0<=alpha<=1 and 0<=width<=5):
        raise ValueError('Point size must be positive, opacity between 0 and 1, and outline width between 0 and 5.')
    options = dict(s=size,alpha=alpha,marker=config.get('marker','o'),edgecolors=edge,linewidths=width)
    options.update(dict(c=values,cmap=cmap,norm=norm) if scaled else dict(color=color))
    return options


def label_samples(axis, coordinates, data, index, config):
    options = label_options(config)
    labels = []
    for _,row in data.iterrows():
        site = fill(str(row['sample']),width=options['wrap'])
        value = f'{index}: {row[index]:.{options["decimals"]}f}'
        labels.append({'site':site,'value':value,'both':site+'\n'+value,
                       'class':site+'\n'+fill(str(row['classification']),width=options['wrap'])}[options['content']])
    layout = point_labels(axis,coordinates,labels,colors=[options['color']]*len(labels),fontsize=options['size'])
    for text in layout.labels:
        style = dict(color=options['color'],fontsize=options['size'],
                     fontweight='bold' if options['bold'] else 'normal',
                     fontstyle='italic' if options['italic'] else 'normal')
        if options['font_family']:
            style['fontfamily'] = options['font_family']
        # The common figure style preserves these explicit annotation settings.
        text._aquaprov_annotation_style = style
        text.update(style)
        text.set_gid('aquaprov-index-point-label')
        text.set_path_effects([withStroke(linewidth=2,foreground='white')] if options['halo'] else [])
        text.arrow_patch.set_visible(bool(options['leaders']))
    return layout
