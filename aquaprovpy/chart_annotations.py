"""Render configured decorations without changing the analysed observations."""
def reference_line(ax, settings, *, direction='horizontal', value=0, limits=None):
    if not settings.get('show', True):
        return None
    kwargs = dict(color=settings.get('color','#888888'), linewidth=settings.get('width',.65),
                  linestyle=settings.get('linestyle','--'), zorder=1)
    kwargs['label'] = settings.get('label') or ('Identity line (y = x)' if direction == 'identity'
                                              else f'{direction.title()} reference ({value:g})')
    if direction == 'identity':
        if settings.get('limits','').strip():
            from .observation_options import numbers
            limits = numbers(settings['limits'],2)
        artist, = ax.plot(limits, limits, **kwargs)
    elif direction == 'vertical':
        if not settings.get('x', True):
            return None
        artist = ax.axvline(value, **kwargs)
    else:
        if not settings.get('y', True):
            return None
        artist = ax.axhline(value, **kwargs)
    artist.set_gid('aquaprov-reference-' + direction)
    return artist


def plot_note(ax, settings, automatic, **values):
    if not settings.get('show', True):
        return None
    text = (settings.get('text') or automatic).replace('\\n', '\n')
    # Literal replacement deliberately avoids evaluation or arbitrary format fields.
    for key,value in values.items():
        text = text.replace('{' + key + '}', format(value, 'g') if isinstance(value, (int,float)) else str(value))
    color, size = settings.get('color','#243447'), settings.get('size',7)
    artist = ax.text(settings.get('x',.03), settings.get('y',.95), text,
        transform=ax.transAxes, ha=settings.get('ha','left'), va=settings.get('va','top'), color=color, fontsize=size)
    artist._aquaprov_annotation_style = dict(color=color, fontsize=size)
    artist.set_gid('aquaprov-plot-note')
    return artist
