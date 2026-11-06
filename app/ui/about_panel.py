from __future__ import annotations

from pathlib import Path
from platform import python_version

from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR, QSize, Qt
from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from . import icons

_REPOSITORY = "https://github.com/baaaaan1/Playgrounds"


class AboutPanel(QScrollArea):
    """Read-only project information and bundled third-party attribution."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAccessibleName(self.tr("About Playgrounds"))

        content = QWidget()
        content.setObjectName("SettingsEditor")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 12, 0)
        layout.setSpacing(18)

        brand = QLabel()
        brand.setFixedSize(56, 56)
        brand.setPixmap(icons.app_icon().pixmap(QSize(56, 56), self.devicePixelRatioF()))
        brand.setAccessibleName(self.tr("Playgrounds logo"))
        name = QLabel("Playgrounds")
        name.setObjectName("SettingsTitle")
        version = QLabel(self.tr("Version {version} (stable)").format(version=__version__))
        version.setObjectName("SettingsHelp")
        identity = QVBoxLayout()
        identity.setSpacing(2)
        identity.addWidget(name)
        identity.addWidget(version)
        header = QHBoxLayout()
        header.setSpacing(14)
        header.addWidget(brand)
        header.addLayout(identity, 1)
        layout.addLayout(header)

        tagline = QLabel(self.tr("\u201cLooks cool, ships fast, uses less RAM.\u201d \U0001f5ff"))
        tagline.setObjectName("AboutTagline")
        tagline.setTextFormat(Qt.TextFormat.PlainText)
        tagline.setWordWrap(True)
        tagline.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(tagline)

        sections = (
            (self.tr("Your AI workspace"), (
                self.tr("A lightweight desktop AI playground built with Python and PyQt6. "
                        "Use named OpenAI-compatible connections with separate endpoints, models, and settings."),
                self.tr("Stream responses, edit and resend messages, retry failed requests, "
                        "regenerate answers, and copy responses. Search, pin, and archive conversations "
                        "in the main window."),
                self.tr("Review response timing, token usage, and estimated costs when available. "
                        "Cost estimates use the per-model rates you configure; they are not provider invoices."),
                self.tr("<b>Keyboard shortcuts:</b> Ctrl+N for a new chat, Ctrl+F to find text in the chat, "
                        "Ctrl+B to toggle the sidebar, and Ctrl+, to open Settings."),
            )),
            (self.tr("Your data & connections"), (
                self.tr("Conversations and drafts are stored locally as JSON files in "
                        "%APPDATA%\\Playgrounds\\conversations. Preferences are stored using Windows QSettings. "
                        "Conversation files are not encrypted by Playgrounds."),
                self.tr("API keys are stored separately in Windows Credential Manager, "
                        "not in conversation files or application preferences."),
                self.tr("Messages are sent to your configured API endpoint when generating responses. "
                        "Model access, availability, and data handling depend on that provider. "
                        "Automatic update checks can be managed in Settings under Updates."),
            )),
            (self.tr("Project & contributions"), (
                self.tr('<a href="{repository_url}">Source code</a> &nbsp; / &nbsp; '
                        '<a href="{issues_url}">Report an issue</a> &nbsp; / &nbsp; '
                        '<a href="{pulls_url}">Pull requests</a>').format(
                            repository_url=_REPOSITORY,
                            issues_url=f"{_REPOSITORY}/issues",
                            pulls_url=f"{_REPOSITORY}/pulls",
                        ),
                self.tr('Maintained by <a href="{maintainer_url}">baaaaan1</a> '
                        'and <a href="{contributors_url}">contributors</a>. '
                        "Bug reports, code, documentation, and design improvements are welcome. "
                        "For code changes, include regression tests and run pytest and Ruff.").format(
                            maintainer_url="https://github.com/baaaaan1",
                            contributors_url=f"{_REPOSITORY}/graphs/contributors",
                        ),
            )),
            (self.tr("Credits & references"), (
                self.tr('<b>Interface icons:</b> <a href="{icons_url}">'
                        'Material Line Icons (line-md)</a> by Vjacheslav Trushkin. '
                        "MIT license; SVGs are bundled locally with animations frozen for static rendering.").format(
                            icons_url="https://icon-sets.iconify.design/line-md/",
                        ),
                self.tr('<b>Chat action icons:</b> <a href="{symbols_url}">'
                        'Material Symbols</a> by Google. Apache License 2.0; '
                        "SVGs and their license are bundled locally.").format(
                            symbols_url="https://icon-sets.iconify.design/material-symbols/",
                        ),
                self.tr('<b>Application icon:</b> Playgrounds Pixel Mosaic, the project\'s '
                        '<a href="{artwork_url}">bundled SVG artwork</a>.').format(
                            artwork_url=f"{_REPOSITORY}/blob/HEAD/build/icon.svg",
                        ),
                self.tr('<b>Application stack:</b> <a href="{python_url}">Python</a>, '
                        '<a href="{pyqt_url}">PyQt6</a>, and '
                        '<a href="{qt_url}">Qt</a>. '
                        "Runtime: Python {python_version} / PyQt {pyqt_version} / Qt {qt_version}.").format(
                            python_url="https://www.python.org/",
                            pyqt_url="https://www.riverbankcomputing.com/software/pyqt/",
                            qt_url="https://www.qt.io/",
                            python_version=python_version(),
                            pyqt_version=PYQT_VERSION_STR,
                            qt_version=QT_VERSION_STR,
                        ),
                self.tr('<b>Build &amp; quality tools:</b> '
                        '<a href="{pyinstaller_url}">PyInstaller</a>, '
                        '<a href="{pillow_url}">Pillow</a>, '
                        '<a href="{wix_url}">WiX Toolset</a>, '
                        '<a href="{pytest_url}">pytest</a>, and '
                        '<a href="{ruff_url}">Ruff</a>.').format(
                            pyinstaller_url="https://pyinstaller.org/",
                            pillow_url="https://python-pillow.github.io/",
                            wix_url="https://wixtoolset.org/",
                            pytest_url="https://docs.pytest.org/",
                            ruff_url="https://docs.astral.sh/ruff/",
                        ),
            )),
            (self.tr("License"), (
                self.tr('Playgrounds is licensed under '
                        '<a href="{license_url}">GNU GPL version 3 only</a> '
                        "(GPL-3.0-only). The full LICENSE is included with the application. "
                        "Redistribution must comply with GPL v3, including corresponding source requirements.").format(
                            license_url="https://www.gnu.org/licenses/gpl-3.0.html",
                        ),
                self.tr("Third-party assets and tools retain their own licenses. "
                        '<a href="{python_license_url}">Python license</a> / '
                        '<a href="{pyqt_license_url}">PyQt licensing</a> / '
                        '<a href="{qt_license_url}">Qt licensing</a>.').format(
                            python_license_url="https://docs.python.org/3/license.html",
                            pyqt_license_url="https://www.riverbankcomputing.com/software/pyqt/intro",
                            qt_license_url="https://www.qt.io/licensing/",
                        ),
            )),
        )
        for title, paragraphs in sections:
            group = QGroupBox(title)
            body = QVBoxLayout(group)
            body.setSpacing(10)
            for paragraph in paragraphs:
                label = QLabel(paragraph)
                label.setObjectName("SettingsHelp")
                label.setWordWrap(True)
                label.setTextFormat(Qt.TextFormat.RichText)
                label.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextBrowserInteraction
                )
                label.setOpenExternalLinks(True)
                body.addWidget(label)
            layout.addWidget(group)

        self._icon_license = QPlainTextEdit()
        self._symbols_license = QPlainTextEdit()
        resources = Path(__file__).resolve().parents[1] / "resources"
        for title, description, directory, editor in (
            (self.tr("Material Line Icons (MIT)"),
             self.tr("Material Line Icons attribution and full MIT license"), "line-md", self._icon_license),
            (self.tr("Material Symbols (Apache 2.0)"),
             self.tr("Material Symbols attribution and full Apache License 2.0"), "material-symbols", self._symbols_license),
        ):
            license_group = QGroupBox(title)
            license_group.setAccessibleName(description)
            license_group.setCheckable(True)
            license_group.setChecked(False)
            license_layout = QVBoxLayout(license_group)
            editor.setReadOnly(True)
            editor.setAccessibleName(description)
            editor.setFixedHeight(180)
            editor.setPlainText((resources / directory / "LICENSE.txt").read_text(encoding="utf-8"))
            license_layout.addWidget(editor)
            editor.hide()
            license_group.toggled.connect(editor.setVisible)
            layout.addWidget(license_group)
        layout.addStretch(1)
        self.setWidget(content)
