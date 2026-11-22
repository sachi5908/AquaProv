"""Direct plot interaction without Matplotlib's navigation toolbar.

Desktop figures zoom and drag as a complete page inside their scroll area.
Explicit axis navigation uses scale coordinates, preserving log/inverted axes.
Views never change the underlying data.
"""
from __future__ import annotations

import numpy as np
from matplotlib.backend_bases import MouseButton


def _scaled(component, values):
    with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
        values = np.ma.asarray(component.get_transform().transform(np.asarray(values, float)))
    return np.asarray(values.filled(np.nan), dtype=float)


def _unscaled(component, values):
    with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
        values = np.ma.asarray(component.get_transform().inverted().transform(np.asarray(values, float)))
    values = np.asarray(values.filled(np.nan), dtype=float)
    if component.get_scale() == 'log' and (values <= 0).any():
        return None
    if component.get_scale() == 'logit' and ((values <= 0) | (values >= 1)).any():
        return None
    return values if np.isfinite(values).all() and values[0] != values[1] else None


class FigureNavigation:
    def __init__(self, canvas, on_view_changed=None):
        self.canvas = canvas
        self.figure = canvas.figure
        self.on_view_changed = on_view_changed
        self.axes = [axis for axis in self.figure.axes if axis.get_navigate() and
                     axis.get_label() != '<colorbar>' and not hasattr(axis, '_colorbar')]
        self._drag = None
        self._decoration_drag = None
        self._page_drag = None
        self.closed = False
        # Keep a separate original view for every per-sample figure. Returning to
        # that figure must not replace its reset position with its zoomed view.
        if not hasattr(self.figure, '_aquaprov_initial_views'):
            self.figure._aquaprov_initial_views = {axis: self._view(axis) for axis in self.axes}
            self._capture_first_camera = True
        else:
            self._capture_first_camera = False
        self.initial_views = self.figure._aquaprov_initial_views
        self.callbacks = [canvas.mpl_connect(name, method) for name, method in (
            ('scroll_event', self._scroll), ('button_press_event', self._press),
            ('motion_notify_event', self._motion), ('button_release_event', self._release),
            ('draw_event', self._first_draw))]

    @staticmethod
    def _view(axis):
        view = {'xlim': axis.get_xlim(), 'ylim': axis.get_ylim()}
        if hasattr(axis, 'get_zlim'):
            view.update(zlim=axis.get_zlim(), elev=axis.elev, azim=axis.azim,
                        roll=axis.roll, focal_length=axis._focal_length)
        return view

    def _first_draw(self, _event):
        if self._capture_first_camera:
            # 3D workspaces apply the selected camera just after installing the
            # canvas. Its first painted camera is the reset position.
            for axis in self.axes:
                if hasattr(axis, 'get_zlim'):
                    self.initial_views[axis].update({key: value for key, value in self._view(axis).items()
                                                    if key in ('elev', 'azim', 'roll', 'focal_length')})
            self._capture_first_camera = False

    def _notify(self):
        if self.on_view_changed:
            self.on_view_changed()

    def _canvas_position(self, event):
        from PySide6.QtCore import QPointF
        ratio = self.canvas.device_pixel_ratio
        return QPointF(event.x / ratio, self.canvas.height() - event.y / ratio)

    def _scroll(self, event):
        viewport = getattr(self.canvas, '_aquaprov_viewport', None)
        if viewport is not None and 'shift' not in str(event.key).lower():
            if not self.closed and self.canvas.widgetlock.available(self):
                self._first_draw(None)
                viewport.zoom_at(float(event.step), self._canvas_position(event))
                self._notify()
            return
        axis = event.inaxes
        if self.closed or axis not in self.axes or not self.canvas.widgetlock.available(self):
            return
        step = float(event.step)
        if not np.isfinite(step) or step == 0:
            return
        self._first_draw(None)
        factor = 1.2 ** -np.clip(step, -10, 10)
        three_d = hasattr(axis, 'get_zlim')
        updates = []
        for name in ('x', 'y', 'z') if three_d else ('x', 'y'):
            component = getattr(axis, name + 'axis')
            limits = _scaled(component, getattr(axis, 'get_' + name + 'lim')())
            if not np.isfinite(limits).all():
                return
            anchor = limits.mean()
            position = getattr(event, name + 'data', None)
            if not three_d and position is not None:
                transformed = _scaled(component, [position])[0]
                if np.isfinite(transformed):
                    anchor = transformed
            result = _unscaled(component, anchor + (limits - anchor) * factor)
            if result is None:
                return
            updates.append((name, result))
        for name, limits in updates:
            getattr(axis, 'set_' + name + 'lim')(limits, auto=False)
        self.canvas.draw_idle()
        self._notify()

    def _press(self, event):
        axis = event.inaxes
        if (self.closed or event.button != MouseButton.LEFT or not self.canvas.widgetlock.available(self)):
            return
        if axis in self.axes and not hasattr(axis, 'get_zlim'):
            for artist in reversed(axis.artists):
                if getattr(artist, '_aquaprov_draggable', False) and artist.contains(event)[0]:
                    self.canvas.widgetlock(self)
                    self._decoration_drag = (artist,event.x,event.y,np.array(artist.position),axis.bbox.frozen())
                    return
        # Leave draggable legends under Matplotlib's own event handlers.
        # Legends can sit outside their axes, where event.inaxes is None.
        legends = [*self.figure.legends, *(item.get_legend() for item in self.figure.axes)]
        if any(legend is not None and legend.get_visible() and legend.contains(event)[0] for legend in legends):
            # Axes3D receives the press before navigation; cancel its camera
            # gesture when the user picked a legend over the 3D axes.
            if axis in self.axes and hasattr(axis, 'get_zlim'):
                axis.button_pressed = None
            return
        viewport = getattr(self.canvas, '_aquaprov_viewport', None)
        three_d = axis in self.axes and hasattr(axis, 'get_zlim')
        if viewport is not None and not three_d and 'shift' not in str(event.key).lower():
            self.canvas.widgetlock(self)
            self._page_drag = viewport
            viewport.begin_drag(self._canvas_position(event))
            return
        if axis not in self.axes or three_d:
            return
        self.canvas.widgetlock(self)
        self._drag = (axis, event.x, event.y, axis.bbox.frozen(),
                      _scaled(axis.xaxis, axis.get_xlim()), _scaled(axis.yaxis, axis.get_ylim()))

    def _motion(self, event):
        if not self.closed and self._page_drag is not None and event.x is not None and event.y is not None:
            self._page_drag.drag_to(self._canvas_position(event))
            return
        if not self.closed and self._decoration_drag is not None and event.x is not None and event.y is not None:
            artist,x,y,position,bounds = self._decoration_drag
            artist.move_to(position+[(event.x-x)/bounds.width,(event.y-y)/bounds.height])
            self.canvas.draw_idle()
            return
        if self.closed or self._drag is None or event.x is None or event.y is None:
            return
        axis, x, y, bounds, xlim, ylim = self._drag
        if bounds.width <= 0 or bounds.height <= 0:
            return
        limits = []
        for component, original, movement in ((axis.xaxis, xlim, (event.x - x) / bounds.width),
                                                (axis.yaxis, ylim, (event.y - y) / bounds.height)):
            value = _unscaled(component, original - movement * (original[1] - original[0]))
            if value is None:
                return
            limits.append(value)
        axis.set_xlim(limits[0], auto=False)
        axis.set_ylim(limits[1], auto=False)
        self.canvas.draw_idle()

    def _release(self, _event):
        if self.closed:
            return
        if self._page_drag is not None:
            self._page_drag.end_drag()
            self._page_drag = None
        if self._decoration_drag is not None:
            self.figure._aquaprov_layout_moved = True
        self._drag = None
        self._decoration_drag = None
        if self.canvas.widgetlock.isowner(self):
            self.canvas.widgetlock.release(self)
        self._notify()

    def reset(self):
        if self.closed:
            return
        self._first_draw(None)
        self._release(None)
        for axis, view in self.initial_views.items():
            axis.set_xlim(view['xlim'], auto=False)
            axis.set_ylim(view['ylim'], auto=False)
            if 'zlim' in view:
                axis.set_zlim(view['zlim'], auto=False)
                axis.view_init(elev=view['elev'], azim=view['azim'], roll=view['roll'])
                if np.isinf(view['focal_length']):
                    axis.set_proj_type('ortho')
                else:
                    axis.set_proj_type('persp', focal_length=view['focal_length'])
        viewport = getattr(self.canvas, '_aquaprov_viewport', None)
        if viewport is not None:
            viewport.reset()
        self.canvas.draw_idle()
        self._notify()

    def disconnect(self):
        if self.closed:
            return
        if self._page_drag is not None:
            self._page_drag.end_drag()
            self._page_drag = None
        self._drag = None
        self._decoration_drag = None
        if self.canvas.widgetlock.isowner(self):
            self.canvas.widgetlock.release(self)
        for callback in self.callbacks:
            self.canvas.mpl_disconnect(callback)
        self.callbacks.clear()
        self.closed = True
