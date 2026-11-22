"""Sample-location workspace behavior and geographic map lifecycle."""
import re
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QMessageBox
from ...ui.loading import plot_loading, run_worker
from ...core.progress import progress_stage


class LocationWorkspaceMixin:
    def _basemap_key(self):
        return self.map_background_combo.currentData() or ('osm' if self.map_background_combo.currentIndex() == 0 else 'plain')

    def _map_controls_changed(self, *_):
        self.map_crs_combo.setEnabled(True)
        utm = self.map_crs_combo.currentData() == 'utm'
        self.map_zone_spin.parentWidget().setVisible(utm)
        self.map_hemisphere_combo.parentWidget().setVisible(utm)


    def _map_background_status(self, message, busy):
        self.map_status.setText(message)
        self.map_retry_button.setEnabled(not busy)
        self.save_button.setEnabled(not busy and self.generated_plot is not None)


    def _retry_map_background(self):
        if self.map_basemap is not None:
            self.map_basemap.refresh(force=True)


    def _populate_map_controls(self, frame):
        columns = list(frame.columns)
        numeric_columns = list(self._numeric_columns)
        # A new worksheet may use a different CRS even when column names agree.
        self.map_crs_combo.setCurrentIndex(0)
        self.map_zone_spin.setValue(0)
        self.map_hemisphere_combo.setCurrentIndex(0)

        for combo, placeholder, values in (
            (self.map_x_combo, "(select X coordinate)", numeric_columns),
            (self.map_y_combo, "(select Y coordinate)", numeric_columns),
            (self.map_value_combo, "(single color)", numeric_columns),
            (self.map_label_combo, "(no point labels)", columns),
        ):
            combo.clear()
            combo.addItem(placeholder)
            combo.addItems([str(column) for column in values])

        def find_coordinate(candidates):
            by_normalized_name = {
                re.sub(r"[^a-z0-9]", "", str(column).lower()): str(column)
                for column in numeric_columns
            }
            for name in candidates:
                if name in by_normalized_name:
                    return by_normalized_name[name]
                if name in ("longitude", "latitude", "easting", "northing"):
                    match = next((column for key, column in by_normalized_name.items() if key.startswith(name)), None)
                    if match:
                        return match
            return ""

        x_column = find_coordinate(("longitude", "lon", "long", "easting", "xcoordinate", "xcoord", "x"))
        y_column = find_coordinate(("latitude", "lat", "northing", "ycoordinate", "ycoord", "y"))
        if x_column:
            self.map_x_combo.setCurrentText(x_column)
        if y_column:
            self.map_y_combo.setCurrentText(y_column)
        if "TDS" in numeric_columns:
            self.map_value_combo.setCurrentText("TDS")
        if len(frame) <= 35 and "Village" in columns:
            self.map_label_combo.setCurrentText("Village")
        elif len(frame) <= 35 and "Sample" in columns:
            self.map_label_combo.setCurrentText("Sample")


    def _make_map_data(self):
        if self.map_data is None:
            raise ValueError("Import a CSV or Excel file first.")
        x_column = self.map_x_combo.currentText()
        y_column = self.map_y_combo.currentText()
        if x_column not in self.map_data or y_column not in self.map_data:
            raise ValueError("Choose numeric X and Y coordinate columns in the Map settings.")
        if x_column == y_column:
            raise ValueError("Choose different columns for the X and Y coordinates.")
        data = self.map_data
        online = self._basemap_key() != 'plain'
        crs, zone, hemisphere = self.map_crs_combo.currentData(), self.map_zone_spin.value(), self.map_hemisphere_combo.currentData()
        def validate_coordinates():
            frame = data[[x_column, y_column]].apply(pd.to_numeric, errors='coerce')
            frame = frame.loc[np.isfinite(frame[x_column]) & np.isfinite(frame[y_column])]
            if frame.empty:
                raise ValueError('The selected coordinate columns do not contain any valid coordinate pairs.')
            # Validate before applying missing-color exclusions.
            if online:
                from ...locations import project_coordinates
                project_coordinates(frame[x_column], frame[y_column], crs, zone, hemisphere)
        with progress_stage(2, 8, 'Checking map coordinates'):
            run_worker(validate_coordinates)
        value_column = self.map_value_combo.currentText()
        if value_column == "(single color)":
            value_column = None
        frame = self._prepare_plot_data(self.map_data,
            [x_column, y_column] + ([value_column] if value_column is not None else []))
        label_column = self.map_label_combo.currentText()
        if label_column == "(no point labels)":
            label_column = None
        return frame, x_column, y_column, value_column, label_column


    @staticmethod
    def _map_bounds(frame, x_column, y_column):
        xmin, xmax = frame[x_column].min(), frame[x_column].max()
        ymin, ymax = frame[y_column].min(), frame[y_column].max()
        xspan, yspan = xmax - xmin, ymax - ymin
        xpad = max(xspan * 0.06, abs(xmin) * 0.0001, 1e-6)
        ypad = max(yspan * 0.06, abs(ymin) * 0.0001, 1e-6)
        if xspan == 0:
            xmin, xmax = xmin - xpad, xmax + xpad
        if yspan == 0:
            ymin, ymax = ymin - ypad, ymax + ypad
        return xmin, xmax, ymin, ymax, xpad, ypad


    def _map_bounds_text(self, frame, x_column, y_column):
        xmin, xmax, ymin, ymax, _, _ = self._map_bounds(frame, x_column, y_column)
        excluded = len(self.map_data) - len(frame) if self.map_data is not None else 0
        return (f"{len(frame):,} locations · {excluded} rows excluded (missing/non-numeric/non-finite coordinates or color) · source bounding box: {x_column} {xmin:g} to {xmax:g}; "
                f"{y_column} {ymin:g} to {ymax:g}")


    def _render_map(self, frame, x_column, y_column, value_column, label_column, target, image_format, dpi):
        options = dict(online=self._basemap_key() != 'plain', provider=self._basemap_key(),
                       crs=self.map_crs_combo.currentData(), zone=self.map_zone_spin.value(),
                       hemisphere=self.map_hemisphere_combo.currentData(), size=self.size_spin.value(),
                       marker=self.marker_combo.currentText(), alpha=self.alpha_spin.value(),
                       color=self.color_button.text(), style=self.plot_style(),
                       boundary=self._active_boundary() if hasattr(self, '_active_boundary') else None)
        if hasattr(self, '_map_layout_options'):
            options.update(self._map_layout_options())
        if hasattr(self, 'point_scale_combo'):
            from ...observation_options import options as point_options
            options['point_settings'] = point_options(self)
        return self._run_plot_job(lambda: self._draw_map(
            frame, x_column, y_column, value_column, label_column, target, image_format, dpi, **options))

    @staticmethod
    def _draw_map(frame, x_column, y_column, value_column, label_column, target, image_format, dpi,
                  *, online, crs, zone, hemisphere, size, marker, alpha, color, style, provider='osm', boundary=None,
                  show_colorbar=True, colorbar_orientation='vertical', show_grid=None, grid_spacing=0.,
                  north_arrow=False, north_reference='true', map_layout=None, point_settings=None, colorbar_options=None):
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle

        figure, axis = plt.subplots(figsize=(9, 6), dpi=dpi, layout='constrained')
        try:
            from ...boundaries import source_crs
            declared = source_crs(crs, zone, hemisphere)
            figure._aquaprov_boundary_crs = 'EPSG:3857' if online else declared
            if online:
                from ...locations import map_limits, project_coordinates
                from ...basemaps import basemap, add_attribution
                plot_x, plot_y, longitude, latitude = project_coordinates(
                    frame[x_column], frame[y_column], crs, zone, hemisphere)
                figure._aquaprov_map_coordinates = (longitude, latitude)
            else:
                plot_x, plot_y = frame[x_column].to_numpy(), frame[y_column].to_numpy()
            from ...observation_options import draw_points, configure_colorbar
            point_settings = dict(point_settings or {})
            if online:
                point_settings['geographic'] = False
            points = draw_points(axis, frame, plot_x, plot_y, frame[value_column] if value_column else None,
                                 settings=point_settings, size=size, marker=marker, alpha=alpha, color=color,
                                 labels=frame[label_column] if label_column else None)
            if value_column and show_colorbar:
                from .cartography import aligned_colorbar
                colorbar = aligned_colorbar(axis, points, value_column, colorbar_orientation, map_layout, colorbar_options)
                configure_colorbar(colorbar, point_settings)

            if online:
                xlim, ylim = map_limits(plot_x, plot_y)
                axis.set_xlim(xlim)
                axis.set_ylim(ylim)
                axis.set_aspect('equal', adjustable='box')
                axis.set_autoscale_on(False)
                axis.set_xlabel('Web Mercator easting (m; EPSG:3857)')
                axis.set_ylabel('Web Mercator northing (m; EPSG:3857)')
                axis.set_title('Sample locations · '+basemap(provider)['name'])
                add_attribution(axis, provider)
                # Wide antimeridian datasets are deliberately not wrapped.
                figure._aquaprov_map_wide = np.ptp(longitude) > 180
            else:
                xmin, xmax, ymin, ymax, xpad, ypad = LocationWorkspaceMixin._map_bounds(frame, x_column, y_column)
                if point_settings.get('bounds', True):
                    axis.add_patch(Rectangle((xmin, ymin), xmax - xmin, ymax - ymin, fill=False,
                                         edgecolor="#147d80", linestyle="--", linewidth=1.4,
                                         label="Coordinate bounds", zorder=2))
                axis.set_xlim(xmin - xpad, xmax + xpad)
                axis.set_ylim(ymin - ypad, ymax + ypad)
                axis.set_xlabel(x_column)
                axis.set_ylabel(y_column)
                axis.set_title("Sample locations · plain coordinates (no basemap)")
                axis.grid(True, color="#dce4ed", linewidth=0.7, alpha=0.8)
                if point_settings.get('bounds', True):
                    axis.legend(loc="upper left" if north_arrow else "best", frameon=True)

            if boundary is not None:
                from ...boundaries import geometry_in_crs, draw_boundary
                geometry = geometry_in_crs(boundary, figure._aquaprov_boundary_crs, declared_local_crs=declared)
                draw_boundary(axis, geometry)
                xmin, ymin, xmax, ymax = geometry.bounds
                lowx, highx = min(axis.get_xlim()[0], xmin), max(axis.get_xlim()[1], xmax)
                lowy, highy = min(axis.get_ylim()[0], ymin), max(axis.get_ylim()[1], ymax)
                axis.set_xlim(lowx, highx)
                axis.set_ylim(lowy, highy)
            from .cartography import decorate_map
            decorate_map(axis, figure._aquaprov_boundary_crs, show_grid=not online if show_grid is None else show_grid,
                         grid_spacing=grid_spacing, north_arrow=north_arrow, north_reference=north_reference,layout=map_layout)
            style.apply(figure)
            if target is not None:
                figure.savefig(target, format=image_format, dpi=dpi, bbox_inches="tight")
            return figure
        except Exception:
            plt.close(figure)
            raise


    @plot_loading
    def generate_map(self):
        self._clear_analysis()
        try:
            image_format = 'png'
            if self.preview_tempdir is not None:
                self.preview_tempdir.cleanup()
            self.preview_tempdir = tempfile.TemporaryDirectory(prefix="aquaprov_map_")
            target = Path(self.preview_tempdir.name) / f"preview.{image_format}"
            self.generated_plot = None
            self.save_button.setEnabled(False)
            self.generate_button.setEnabled(False)
            self.generate_button.setText("Generating map…")
            frame, x_column, y_column, value_column, label_column = self._make_map_data()
            figure = self._render_map(frame, x_column, y_column, value_column, label_column,
                                      None, image_format, 120)
            self._install_figures([figure], ['Sample locations'], map_view=True)
            self.generated_plot = ("map", frame.copy(deep=True), x_column, y_column,
                                   value_column, label_column)
            self.map_details.setText(self._map_bounds_text(frame, x_column, y_column))
            self.map_preview_pixmap = None
            self.save_button.setEnabled(True)
            if self._basemap_key() != 'plain':
                from ...map_tiles import TileBasemap
                self.map_basemap = TileBasemap(figure.axes[0], self.analysis_canvas, self, provider=self._basemap_key())
                self.map_basemap.status_changed.connect(self._map_background_status)
                source = self.map_crs_combo.currentText()
                if self.map_crs_combo.currentData() == 'utm':
                    source += f' · zone {self.map_zone_spin.value()}{self.map_hemisphere_combo.currentData()}'
                details = self.map_details.text() + f' · Source: {source}'
                if figure._aquaprov_map_wide:
                    details += ' · Wide/antimeridian extent: shown unwrapped; zoom into either side for detail.'
                self.map_details.setText(details)
                self.map_basemap.refresh()
            else:
                self.map_status.setText('Plain coordinate view · no geographic background or CRS conversion.')
            self.statusBar().showMessage("Locations plotted. For online maps, wait for the background before saving.")
        except Exception as exc:
            self.plot_loader.hide()
            self._clear_analysis()
            self.generated_plot = None
            self.save_button.setEnabled(False)
            self.statusBar().showMessage("Could not generate the map.")
            self._report_plot_error("Map could not be generated", exc)
        finally:
            self.generate_button.setEnabled(True)
            self._update_generate_button(self.preview_tabs.currentIndex())

