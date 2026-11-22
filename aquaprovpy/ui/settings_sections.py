"""Turn existing settings cards into independently collapsible sections."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QToolButton, QVBoxLayout, QWidget


def make_collapsible(card, *, expanded=False):
    """Keep the card and its fields intact for contextual visibility controls."""
    if hasattr(card, 'section_header'):
        return
    layout = card.layout()
    heading = card.findChild(QLabel, 'cardTitle', Qt.FindChildOption.FindDirectChildrenOnly)
    if heading is None:
        return
    title = heading.text()
    layout.removeWidget(heading)
    heading.hide()
    heading.deleteLater()
    body = QFrame(card)
    body.setObjectName('settingsSectionContent')
    fields = QVBoxLayout(body)
    fields.setContentsMargins(10, 12, 10, 12)
    fields.setSpacing(11)
    visibility = {widget: not widget.isHidden() for widget in
                  card.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly)
                  if widget not in (heading, body)}
    while layout.count():
        item = layout.takeAt(0)
        if item.widget() is not None:
            fields.addWidget(item.widget())
        elif item.layout() is not None:
            fields.addLayout(item.layout())
        else:
            fields.addItem(item)
    for widget, visible in visibility.items():
        widget.setVisible(visible)
    header = QToolButton(card)
    header.setObjectName('settingsSectionHeader')
    header.setText(title.replace('&', '&&'))
    header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    header.setCheckable(True)
    header.setCursor(Qt.CursorShape.PointingHandCursor)
    header.setMinimumHeight(38)
    header.setAccessibleName(title + ' settings')
    header.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

    def toggle(opened):
        body.setVisible(opened)
        header.setArrowType(Qt.ArrowType.DownArrow if opened else Qt.ArrowType.RightArrow)
        header.setToolTip(('Hide ' if opened else 'Show ') + title)
        header.setAccessibleDescription('Expanded' if opened else 'Collapsed')

    header.toggled.connect(toggle)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    layout.addWidget(header)
    layout.addWidget(body)
    card.setObjectName('settingsSection')
    card.section_header = header
    card.section_content = body
    header.setChecked(expanded)
    toggle(expanded)


def organize_settings(content):
    layout = content.layout()
    for index in range(layout.count()):
        card = layout.itemAt(index).widget()
        if isinstance(card, QFrame):
            make_collapsible(card, expanded=index == 0)
