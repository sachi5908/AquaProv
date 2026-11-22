"""Colour-scale menus with swatches and an adjacent live gradient preview.

The model retains Matplotlib identifiers as its text, so existing project files,
presets, scripts and currentText()/setCurrentText() callers remain compatible.
Only the delegate and the closed selector render the human-readable labels.
"""
from functools import lru_cache

import numpy as np
from matplotlib import colormaps
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QListView, QSizePolicy, QStyle, QStyledItemDelegate,
    QStyleOptionComboBox, QStylePainter, QWidget,
)

from ..colour_scales import COLOUR_SCALES, colour_scale_label, register_colour_scales


@lru_cache(maxsize=128)
def gradient_image(name):
    colours = np.ascontiguousarray(colormaps[name](np.linspace(0, 1, 256), bytes=True))
    return QImage(colours.data, 256, 1, 1024, QImage.Format.Format_RGBA8888).copy()


@lru_cache(maxsize=128)
def gradient_icon(name):
    # Render at twice the logical size to keep swatches crisp on HiDPI screens.
    pixmap = QPixmap(80, 28)
    painter = QPainter(pixmap)
    painter.drawImage(pixmap.rect(), gradient_image(name))
    painter.setPen(QColor('#c5cdd5'))
    painter.drawRect(pixmap.rect().adjusted(0, 0, -1, -1))
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


class ColourScaleDelegate(QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.text = colour_scale_label(option.text)

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        return QSize(size.width(), max(30, size.height()))


class ColourScalePreview(QWidget):
    def __init__(self, combo):
        super().__init__()
        self.combo = combo
        self.setMinimumWidth(64)
        self.setFixedHeight(24)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName('Selected colour scale preview')
        combo.currentIndexChanged.connect(self.refresh)
        self.refresh()

    def refresh(self, *_):
        name = self.combo.currentText()
        description = ('Keep the plot\'s original colours' if name == 'Original'
                       else colour_scale_label(name) + ': low values on the left, high values on the right')
        self.setToolTip(description)
        self.setAccessibleDescription(description)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        rectangle = self.rect().adjusted(0, 0, -1, -1)
        name = self.combo.currentText()
        if name in colormaps:
            painter.drawImage(rectangle, gradient_image(name))
        else:
            painter.fillRect(rectangle, QColor('#f5f7fa'))
            painter.setPen(QColor('#526479'))
            painter.drawText(rectangle, Qt.AlignmentFlag.AlignCenter, 'Original')
        painter.setPen(QColor('#c5cdd5'))
        painter.drawRect(rectangle)


class ColourScaleCombo(QComboBox):
    def __init__(self, parent=None, *, original=False, default='viridis', normalization=None):
        super().__init__(parent)
        register_colour_scales()
        self.setAccessibleName('Colour scale')
        self.setIconSize(QSize(40, 14))
        self.setMinimumWidth(130)
        self.setMinimumContentsLength(9)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMaxVisibleItems(8)
        self.setStyleSheet('QComboBox { combobox-popup: 0; }')
        view = QListView(self)
        view.setIconSize(self.iconSize())
        view.setUniformItemSizes(True)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        view.setStyleSheet('QListView { background: white; color: #173858; border: 1px solid #c5cdd5;'
                          ' padding: 3px; outline: 0; }'
                          'QListView::item { padding: 0 4px; border-radius: 3px; }'
                          'QListView::item:selected { background: #e2e9f2; color: #173858; }'
                          'QListView::item:hover { background: #edf2f7; }')
        self.setView(view)
        self.setItemDelegate(ColourScaleDelegate(self))
        self.model().rowsInserted.connect(self._decorate_items)
        self.addItems((['Original'] if original else []) + [name for name, _ in COLOUR_SCALES])
        self.setCurrentText(default)
        self.preview = ColourScalePreview(self)
        self.normalization_check = None
        if normalization is not None:
            self.normalization_check = QCheckBox(normalization.text())
            self.normalization_check.setToolTip(normalization.toolTip())
            self.normalization_check.setChecked(normalization.isChecked())
            # This mirrors one saved plot-style option; only its source emits
            # workspace changes, so toggling it never requests a recalculation.
            self.normalization_check.setProperty('styleControlAlias', True)
            self.normalization_check.toggled.connect(normalization.setChecked)
            normalization.toggled.connect(self.normalization_check.setChecked)

    def _decorate_items(self, parent, first, last):
        for index in range(first, last + 1):
            name = self.itemText(index)
            label = colour_scale_label(name)
            self.setItemData(index, label, Qt.ItemDataRole.AccessibleTextRole)
            self.setItemData(index, label, Qt.ItemDataRole.ToolTipRole)
            if name in colormaps:
                self.setItemIcon(index, gradient_icon(name))

    def showPopup(self):
        width = max(self.fontMetrics().horizontalAdvance(colour_scale_label(self.itemText(i)))
                    for i in range(self.count())) + self.iconSize().width() + 58
        self.view().setMinimumWidth(max(self.width(), width))
        super().showPopup()

    def paintEvent(self, event):
        painter = QStylePainter(self)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        area = self.style().subControlRect(QStyle.ComplexControl.CC_ComboBox, option,
                                          QStyle.SubControl.SC_ComboBoxEditField, self)
        icon_width = self.iconSize().width() + 6 if not option.currentIcon.isNull() else 0
        option.currentText = self.fontMetrics().elidedText(
            colour_scale_label(self.currentText()), Qt.TextElideMode.ElideRight,
            max(0, area.width() - icon_width - 4))
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, option)
        painter.drawControl(QStyle.ControlElement.CE_ComboBoxLabel, option)
