"""Shared AquaProv desktop visual styles."""
from pathlib import Path
from .branding import brand_stylesheet
COMBO_ARROW = (Path(__file__).resolve().parents[1] / "assets" / "dropdown.svg").as_posix()
SPIN_UP_ARROW = (Path(COMBO_ARROW).with_name('spin-up.svg')).as_posix()

def apply_workbench_style(self):
    # Keep the inherited control font in points for native Qt font metrics.
    self.setStyleSheet(brand_stylesheet("""
        QWidget { font-family: 'Segoe UI'; font-size: 9pt; color: @ink@; }
        QLabel#activePlotTitle { font-size: 19px; font-weight: 700; color: @ink@; }
        QFrame#plotLibrary { background: white; border: 1px solid @border@; border-radius: 9px; }
        QLabel#libraryHeading { color: @muted@; font-size: 10px; font-weight: 700; }
        QTreeWidget#plotTree { background: white; border: 0; outline: 0; }
        QTreeWidget#plotTree::item { padding: 8px 2px; border: 0; color: @ink@; }
        QTreeWidget#plotTree::item:selected { color: @teal@; background: @selected@; border-radius: 4px; }
        QFrame#quickTypography { background: white; border: 1px solid @border@; border-radius: 7px; }
        QFrame#quickTypography QPushButton { padding: 6px; border: 1px solid @border@; background: @soft@; }
        QFrame#quickTypography QPushButton:checked { color: @teal@; background: @selected@; }
        QMenuBar, QMenu { background: white; color: @ink@; }
        QMenu::item:selected { background: @hover@; }
        QToolBar { background: #ffffff; border-bottom: 1px solid @border@; spacing: 5px; }
        QToolButton { background: transparent; color: @ink@; padding: 5px; border-radius: 5px; }
        QToolButton:hover, QToolButton:checked { background: @hover@; }
        QPushButton:disabled { color: @disabled@; background: @wash@; }
        QComboBox QAbstractItemView { background: #ffffff; color: @ink@; selection-background-color: @selected@; selection-color: @teal@; }
        QCheckBox { spacing: 7px; padding: 4px 0; }
        QTabWidget#controlTabs::pane, QTabWidget#previewTabs::pane { border: 0; }
        QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus { border: 1px solid @teal@; }
        QMainWindow, QWidget#qt_scrollarea_viewport, QWidget#sidebarContent { background: @background@; }
        QLabel#appTitle { color: @ink@; font-size: 27px; font-weight: 750; }
        QLabel#subtitle { color: @muted@; font-size: 12px; }
        QLabel#fileBadge { color: @teal@; background: @selected@; border-radius: 10px; padding: 9px 13px; font-size: 10px; font-weight: 700; }
        QFrame#card, QFrame#publicationCard { background: #ffffff; border: 1px solid @border@; border-radius: 14px; }
        QToolBox#styleSections { background: transparent; border: 0; }
        QToolBox#styleSections::tab { color: @ink@; background: @soft@;
            border: 1px solid @border@; border-radius: 7px;
            padding: 0 10px; font-size: 9pt; font-weight: 600; }
        QToolBox#styleSections::tab:selected { color: @teal@; background: @wash@; border-color: @teal@; }
        QToolBox#styleSections::tab:hover { background: @hover@; border-color: @cyan@; }
        QToolBox#styleSections QWidget#styleSectionContent { background: @soft@; border-radius: 7px; }
        QToolBox#styleSections QScrollArea { background: transparent; border: 0; }
        QFrame#settingsSection { background: transparent; border: 0; }
        QFrame#settingsSectionContent { background: @soft@; border-radius: 7px; }
        QToolButton#settingsSectionHeader { color: @ink@; background: @soft@;
            border: 1px solid @border@; border-radius: 7px; padding: 0 10px;
            font-size: 9pt; font-weight: 600; text-align: left; }
        QToolButton#settingsSectionHeader:checked { color: @teal@; background: @wash@; border-color: @teal@; }
        QToolButton#settingsSectionHeader:hover { background: @hover@; border-color: @cyan@; }
        QToolButton#settingsSectionHeader:focus { border-color: @cyan@; }
        QPushButton#automaticColorButton { color: @teal@; background: @wash@;
            border: 1px solid @border@; border-radius: 5px; padding: 3px 6px; font-size: 8pt; }
        QToolBox#styleSections QDoubleSpinBox::up-button,
        QFrame#settingsSectionContent QDoubleSpinBox::up-button,
        QFrame#settingsSectionContent QSpinBox::up-button,
        QDoubleSpinBox#style_title_size::up-button { subcontrol-origin: border; subcontrol-position: top right;
            width: 20px; border: 0; background: @wash@; border-top-right-radius: 6px; }
        QToolBox#styleSections QDoubleSpinBox::down-button,
        QFrame#settingsSectionContent QDoubleSpinBox::down-button,
        QFrame#settingsSectionContent QSpinBox::down-button,
        QDoubleSpinBox#style_title_size::down-button { subcontrol-origin: border; subcontrol-position: bottom right;
            width: 20px; border: 0; background: @wash@; border-bottom-right-radius: 6px; }
        QToolBox#styleSections QDoubleSpinBox::up-arrow,
        QFrame#settingsSectionContent QDoubleSpinBox::up-arrow,
        QFrame#settingsSectionContent QSpinBox::up-arrow,
        QDoubleSpinBox#style_title_size::up-arrow { image: url("__SPIN_UP__"); width: 8px; height: 8px; }
        QToolBox#styleSections QDoubleSpinBox::down-arrow,
        QFrame#settingsSectionContent QDoubleSpinBox::down-arrow,
        QFrame#settingsSectionContent QSpinBox::down-arrow,
        QDoubleSpinBox#style_title_size::down-arrow { image: url("__COMBO_ARROW__"); width: 8px; height: 8px; }
        QPushButton#styleAction, QPushButton#stylePrimaryAction { font-size: 9pt; font-weight: 600;
            color: @teal@; background: white; border: 1px solid @border@; border-radius: 7px; padding: 9px 7px; }
        QPushButton#styleAction:hover { background: @wash@; border-color: @cyan@; }
        QPushButton#stylePrimaryAction { color: white; background: @teal@; border-color: @teal@; }
        QPushButton#stylePrimaryAction:hover { background: @teal_hover@; border-color: @teal_hover@; }
        QPushButton#styleAction:focus, QPushButton#stylePrimaryAction:focus { border-color: @cyan@; }
        QLabel#cardTitle { color: @ink@; font-size: 14px; font-weight: 700; }
        QLabel#fieldLabel { color: @ink@; font-size: 11px; font-weight: 600; }
        QLabel#muted { color: @muted@; font-size: 11px; }
        QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox, QListWidget { background: @soft@; color: @ink@; border: 1px solid @border@; border-radius: 7px; padding: 8px 9px; min-height: 18px; selection-background-color: @cyan@; }
        QComboBox::drop-down { background: transparent; border: 0; width: 30px; }
        QComboBox::down-arrow { image: url("__COMBO_ARROW__"); width: 10px; height: 10px; }
        QPushButton { border: 0; border-radius: 8px; padding: 9px 12px; font-weight: 650; }
        QPushButton#primaryButton { color: white; background: @teal@; padding: 12px; font-size: 12px; }
        QPushButton#primaryButton:hover { background: @teal_hover@; }
        QPushButton#secondaryButton { color: @teal@; background: @wash@; padding: 11px; text-align: left; }
        QPushButton#secondaryButton:hover { background: @hover@; }
        QPushButton#flatButton { color: @muted@; background: @wash@; }
        QPushButton#flatButton:hover { background: @hover@; }
        QTableView#dataTable { color: @ink@; background: #ffffff; alternate-background-color: @soft@; border: 1px solid @border@; border-radius: 8px; gridline-color: @border@; font-size: 10px; }
        QTableView#dataTable[sidebarTable="true"] { font-size: 9pt; border-radius: 6px;
            alternate-background-color: @wash@; selection-background-color: @selected@; selection-color: @ink@; }
        QTableView#dataTable[sidebarTable="true"] QHeaderView::section { font-size: 9pt;
            background: @wash@; color: @ink@; padding: 5px 7px;
            border: 0; border-right: 1px solid @border@; border-bottom: 1px solid @border@; }
        QTableView[sidebarTable="true"] QTableCornerButton::section { background: @wash@;
            border: 0; border-right: 1px solid @border@; border-bottom: 1px solid @border@; }
        QTableView[sidebarTable="true"] QScrollBar:horizontal { height: 10px; background: @soft@; margin: 2px; }
        QTableView[sidebarTable="true"] QScrollBar::handle:horizontal { background: @border@; border-radius: 3px; min-width: 28px; }
        QTableView[sidebarTable="true"] QScrollBar::add-line:horizontal,
        QTableView[sidebarTable="true"] QScrollBar::sub-line:horizontal { width: 0; }
        QTableView[sidebarTable="true"] QScrollBar::add-page:horizontal,
        QTableView[sidebarTable="true"] QScrollBar::sub-page:horizontal { background: transparent; }
        QTabBar { background: transparent; border: 0; }
        QTabBar::tab { color: @muted@; background: @surface@;
            border: 1px solid @border@; border-radius: 7px;
            min-height: 18px; padding: 7px 12px; margin: 0 6px 4px 0;
            font-size: 9pt; font-weight: 600; }
        QTabBar::tab:last { margin-right: 0; }
        QTabBar::tab:hover:!selected { color: @teal@; background: @wash@; border-color: @cyan@; }
        QTabBar::tab:selected { color: white; background: @teal@; border-color: @teal@; }
        QTabBar::tab:selected:hover { background: @teal_hover@; border-color: @teal_hover@; }
        QTabBar::tab:selected:focus { border-color: @cyan@; }
        QTabBar::tab:disabled { color: @disabled@; background: @soft@; border-color: @border@; }
        QTabBar::scroller { width: 44px; }
        QTabBar QToolButton { color: @teal@; background: @surface@;
            border: 1px solid @border@; border-radius: 5px; width: 20px;
            padding: 0; margin-bottom: 4px; }
        QTabBar QToolButton:hover { background: @hover@; border-color: @cyan@; }
        QTabBar QToolButton:disabled { color: @disabled@; background: @soft@; }
        QHeaderView::section { color: @muted@; background: @background@; border: 0; border-bottom: 1px solid @border@; padding: 8px; font-weight: 700; }
        QLabel#plotPreview { color: @disabled@; background: @soft@; border: 1px dashed @border@; border-radius: 10px; }
        QStatusBar { color: @muted@; background: @wash@; border-top: 1px solid @border@; }
        QSplitter::handle { background: transparent; }
        QScrollBar:vertical { width: 8px; background: transparent; margin: 2px; }
        QScrollBar::handle:vertical { background: @border@; border-radius: 4px; min-height: 30px; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    """).replace("__COMBO_ARROW__", COMBO_ARROW).replace('__SPIN_UP__', SPIN_UP_ARROW))

