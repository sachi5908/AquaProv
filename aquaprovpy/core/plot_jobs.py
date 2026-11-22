"""Figure preparation without reading or creating Qt widgets."""
import importlib
import re
from contextlib import contextmanager, ExitStack

from .diagram_layout import prepare_diagram_layout
from ..figure_presentation import prepare_figure_title
from .progress import progress_stage, report_progress


@contextmanager
def _suppress_notifications(registry):
    """Suppress delivery while preserving registrations made by a worker.

    CallbackRegistry.blocked() swaps out its callback dictionary. A legend
    created or repacked there loses its new handlers when the old dictionary
    is restored, leaving the registry's reverse index stale too.
    """
    original = registry.__dict__.get('process')
    registry.process = lambda *args, **kwargs: None
    try:
        yield
    finally:
        if original is None:
            del registry.process
        else:
            registry.process = original


@contextmanager
def detached_figure(figure):
    """Give a worker an Agg canvas; replay GUI draw notifications after joining.

    Matplotlib shares its callback registry between canvases. Blocking it is
    essential: a draw callback can own Qt controls even with an Agg canvas attached.
    """
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    canvas, stale_callback = figure.canvas, figure.stale_callback
    with ExitStack() as stack:
        stack.enter_context(_suppress_notifications(figure._canvas_callbacks))
        for axis in figure.axes:
            stack.enter_context(_suppress_notifications(axis.callbacks))
        figure.stale_callback = None
        try:
            yield FigureCanvasAgg(figure)
        finally:
            figure.set_canvas(canvas)
            figure.stale_callback = stale_callback


def render_diagram(module_name, frame, unit, target, image_format, dpi, style, title, *, save=True):
    import matplotlib.pyplot as plt
    module = importlib.import_module(f'aquaprovpy.{module_name}')
    per_sample = module_name in ('stiff', 'chernoff')
    if per_sample:
        samples = frame['Sample'].astype(str)
        if samples.duplicated().any() or any(re.search(r'[<>:"/\\|?*]', name) or not name.strip() for name in samples):
            raise ValueError('Per-sample diagrams require unique sample names without file-path characters.')
    before = set(plt.get_fignums())
    try:
        with progress_stage(0, 65, 'Calculating diagram'):
            with plt.rc_context({'savefig.dpi': dpi, 'figure.max_open_warning': 0}):
                # Live figures need only the final styled render below.
                module.plot(frame, unit=unit, figname=None,
                            figformat=image_format)
        figures = [plt.figure(n) for n in sorted(set(plt.get_fignums()) - before)]
        if len(figures) != (len(frame) if per_sample else 1):
            raise RuntimeError('The legacy diagram did not produce all expected figures. Check the input data.')
        labels = frame['Sample'].astype(str).tolist() if per_sample else [title]
        outputs = [target.parent / f'{target.stem}_{sample}.{image_format}' for sample in labels] if per_sample else [target]
        for index, (figure, label, output) in enumerate(zip(figures, labels, outputs), 1):
            prepare_diagram_layout(figure, module_name)
            prepare_figure_title(figure, title, sample=label if per_sample else None)
            style.apply(figure)
            if save:
                figure.savefig(output, dpi=dpi, bbox_inches='tight')
            report_progress(65 + 35 * index / len(figures), f'Prepared figure {index} of {len(figures)}')
        return figures, labels, outputs
    except BaseException:
        for number in set(plt.get_fignums()) - before:
            plt.close(number)
        raise
