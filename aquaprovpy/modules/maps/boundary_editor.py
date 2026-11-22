"""Manual polygon drawing in a geographic or local coordinate preview."""
import numpy as np
from pyproj.exceptions import ProjError
from shapely.geometry import Polygon
from shapely.ops import unary_union

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.widgets import PolygonSelector

from ...boundaries import make_boundary, geometry_in_crs, draw_boundary, validate_geometry


class BoundaryPicker(QDialog):
    def __init__(self, features, parent=None):
        super().__init__(parent)
        self.features = features
        self.setWindowTitle('Choose study-area polygons')
        self.resize(480, 390)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Select areas to combine into the study boundary.'))
        self.list = QListWidget()
        for feature in features:
            item = QListWidgetItem(feature['name'])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.list.addItem(item)
        layout.addWidget(self.list)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected(self):
        return [f for i,f in enumerate(self.features) if self.list.item(i).checkState() == Qt.CheckState.Checked]

    def accept(self):
        if not self.selected():
            QMessageBox.warning(self, 'Choose an area', 'Select at least one polygon.')
            return
        super().accept()


class BoundaryEditor(QDialog):
    def __init__(self, xy, crs, *, boundary=None, provider='plain', declared_local_crs=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Draw study-area boundary')
        self.resize(1040, 750)
        self.crs, self.boundary = crs, None
        self.parts, self.pending, self.outlines = [], None, []
        self.basemap = None
        layout = QVBoxLayout(self)
        instructions = QLabel('Click vertices around the study area, then click the first point to close. Drag vertices to adjust. '
                              'Use the toolbar to pan/zoom, then turn pan/zoom off to draw. Clear areas to replace an existing boundary.')
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        self.figure = Figure(figsize=(10, 6), layout='constrained')
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.axis = self.figure.add_subplot()
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas, 1)
        points = np.asarray(xy, dtype=float)
        self.axis.scatter(*points.T, c='#007c83', edgecolors='white', linewidths=.5, s=26, zorder=4)
        self.axis.set_aspect('equal', adjustable='box')
        if boundary:
            self.parts = [geometry_in_crs(boundary, crs, declared_local_crs=declared_local_crs)]
        bounds = np.array([p.bounds for p in self.parts]) if self.parts else np.empty((0, 4))
        x = np.r_[points[:, 0], bounds[:, 0], bounds[:, 2]]
        y = np.r_[points[:, 1], bounds[:, 1], bounds[:, 3]]
        pad_x = max(np.ptp(x)*.12, .01 if crs == 'EPSG:4326' else 1)
        pad_y = max(np.ptp(y)*.12, .01 if crs == 'EPSG:4326' else 1)
        self.axis.set(xlim=(x.min()-pad_x, x.max()+pad_x), ylim=(y.min()-pad_y, y.max()+pad_y),
                      xlabel='X' if crs == 'local' else 'Easting (m)' if crs == 'EPSG:3857' else 'Source X',
                      ylabel='Y' if crs == 'local' else 'Northing (m)' if crs == 'EPSG:3857' else 'Source Y')
        self.axis.set_autoscale_on(False)
        self.selector = PolygonSelector(self.axis, self._selected, useblit=False,
                                         props={'color': '#00a6b2', 'linewidth': 2})
        actions = QHBoxLayout()
        for text, callback in [('Add drawn polygon', self.add_polygon), ('Restart polygon', self.restart_polygon), ('Clear areas', self.clear_areas)]:
            button = QPushButton(text)
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)
        self.status = QLabel('Draw a closed polygon, then Apply boundary.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Apply).setText('Apply boundary')
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._refresh_outlines()
        if len(self.parts) == 1 and self.parts[0].geom_type == 'Polygon' and not self.parts[0].interiors:
            vertices = list(self.parts[0].exterior.coords)[:-1]
            self.parts.clear()
            self._refresh_outlines()
            self.selector.verts = vertices
            self.pending = vertices
            self.status.setText('Drag boundary vertices to edit. Clear areas to replace this boundary.')
        if provider != 'plain':
            from ...basemaps import add_attribution
            from ...map_tiles import TileBasemap
            if crs != 'EPSG:3857':
                raise ValueError('Basemap drawing requires geographic display coordinates.')
            add_attribution(self.axis, provider)
            self.basemap = TileBasemap(self.axis, self.canvas, self, provider=provider)
            self.basemap.status_changed.connect(lambda message,busy: self.status.setText(message))
            self.basemap.refresh()

    def _selected(self, vertices):
        self.pending = list(vertices)
        self.status.setText(f'{len(vertices)} vertices. Drag a vertex to adjust, then Apply or Add drawn polygon.')

    def _refresh_outlines(self):
        for patch in self.outlines:
            patch.remove()
        self.outlines = [draw_boundary(self.axis, p) for p in self.parts]
        self.canvas.draw_idle()

    def add_polygon(self):
        if not self.pending:
            self.status.setText('Close the polygon by clicking its first vertex.')
            return False
        try:
            geometry = validate_geometry(Polygon(self.pending))
        except ValueError as exc:
            self.status.setText(str(exc))
            return False
        self.parts.append(geometry)
        self.pending = None
        self.selector.clear()
        self._refresh_outlines()
        self.status.setText(f'{len(self.parts)} area(s). Draw another polygon or Apply boundary.')
        return True

    def restart_polygon(self):
        self.selector.clear()
        self.pending = None
        self.status.setText('Draw a new polygon. Previously added areas are retained.')
        self.canvas.draw_idle()

    def clear_areas(self):
        self.parts.clear()
        self.pending = None
        self.selector.clear()
        self._refresh_outlines()
        self.status.setText('Areas cleared. Draw a new closed polygon.')

    def accept(self):
        if self.pending is not None and not self.add_polygon():
            return
        if not self.parts:
            self.status.setText('Draw and close at least one polygon first.')
            return
        try:
            boundary = make_boundary(unary_union(self.parts), self.crs, provenance={'method': 'manual polygon drawing'})
            if self.crs != 'local':
                boundary = make_boundary(geometry_in_crs(boundary, 'EPSG:4326'), 'EPSG:4326', provenance=boundary['provenance'])
        except (ValueError, ProjError) as exc:
            self.status.setText(str(exc) + ' Clear areas and redraw the boundary within the coordinate limits.')
            return
        self.boundary = boundary
        super().accept()

    def done(self, result):
        self.selector.disconnect_events()
        if self.basemap is not None:
            self.basemap.close()
        super().done(result)
