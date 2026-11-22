"""Project creation form; filesystem work belongs to core.projects."""
from pathlib import Path
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QVBoxLayout)
from ..core.projects import Project
from ..modules.registry import MODULES


class NewProjectDialog(QDialog):
    def __init__(self, parent, module=None):
        super().__init__(parent)
        self.setWindowTitle("Create AquaProv project")
        self.setMinimumWidth(540)
        self.project = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 24)
        title = QLabel("Create a project")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        note = QLabel("Keep your dataset, module settings and exported figures together.")
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        form.setSpacing(14)
        self.name = QLineEdit()
        self.name.setPlaceholderText("e.g. Sukinda groundwater assessment")
        self.location = QLineEdit()
        self.location.setPlaceholderText("Study area / site (optional)")
        self.folder = QLineEdit(str(Path.home() / "Documents" / "AquaProv Projects"))
        directory = QHBoxLayout()
        directory.addWidget(self.folder, 1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.browse)
        directory.addWidget(browse)
        self.module = QComboBox()
        for entry in MODULES:
            self.module.addItem(entry.title, entry.key)
        if module is not None:
            index = self.module.findData(module)
            if index >= 0:
                self.module.setCurrentIndex(index)
        form.addRow("Project name", self.name)
        form.addRow("Study area", self.location)
        form.addRow("Parent folder", directory)
        form.addRow("Start in", self.module)
        layout.addLayout(form)
        self.error = QLabel("A new folder named after your project will be created here.")
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        actions = QHBoxLayout()
        actions.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        create = QPushButton("Create project")
        create.setObjectName("primary")
        create.setDefault(True)
        create.clicked.connect(self.create)
        actions.addWidget(cancel)
        actions.addWidget(create)
        layout.addLayout(actions)

    def browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose parent folder", self.folder.text())
        if folder:
            self.folder.setText(folder)

    def create(self):
        try:
            if not self.folder.text().strip():
                raise ValueError("Choose a parent folder.")
            self.project = Project.create(self.folder.text(), self.name.text(), self.location.text())
            self.project.last_module = self.module.currentData()
            self.project.save()
        except Exception as exc:
            self.error.setStyleSheet("color: #b53c38;")
            self.error.setText("A folder with that name already exists. Choose another project name or parent folder." if isinstance(exc, FileExistsError) else str(exc))
            return
        self.accept()
