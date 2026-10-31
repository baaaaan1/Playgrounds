from __future__ import annotations

import re

from PyQt6.QtWidgets import QApplication

TOKENS: dict[str, dict[str, str]] = {
    "dark": {
        "bg": "#0e1014",
        "bg_alt": "#111419",
        "surface": "#171b22",
        "surface_hover": "#1d232e",
        "surface_active": "#252d3b",
        "border": "#222934",
        "border_strong": "#323c4d",
        "text": "#e7eaf1",
        "text_muted": "#8b94a7",
        "text_faint": "#5b6474",
        "accent": "#7c9cff",
        "accent_hover": "#93adff",
        "accent_text": "#0b1020",
        "user_surface": "#1a2131",
        "assistant_surface": "#141820",
        "code_bg": "#10141c",
        "code_text": "#c8d6ff",
        "danger": "#ff7f7f",
        "success": "#5ad1a3",
    },
    "light": {
        "bg": "#f6f7fa",
        "bg_alt": "#eef0f5",
        "surface": "#ffffff",
        "surface_hover": "#f1f3f8",
        "surface_active": "#e6eaf2",
        "border": "#e2e6ef",
        "border_strong": "#cbd2e0",
        "text": "#1a1f2b",
        "text_muted": "#5f6878",
        "text_faint": "#8b94a5",
        "accent": "#3b5bdb",
        "accent_hover": "#2f4bc4",
        "accent_text": "#ffffff",
        "user_surface": "#eef2fd",
        "assistant_surface": "#ffffff",
        "code_bg": "#f1f3f8",
        "code_text": "#1f2a4a",
        "danger": "#d64545",
        "success": "#1f9d6f",
    },
}

_TOKEN = re.compile(r"@(\w+)")

_QSS = """
* {
    font-family: "Segoe UI Variable Text", "Segoe UI", "Inter", sans-serif;
}

QMainWindow, QDialog, QWidget#Root {
    background-color: @bg;
}

QLabel {
    background: transparent;
    color: @text;
}

QLabel#Wordmark {
    color: @text;
    font-size: 15px;
    font-weight: 600;
    letter-spacing: 0.4px;
}

QLabel#SectionLabel {
    color: @text_faint;
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 1.2px;
    padding: 0 10px;
}

QLabel#TopTitle {
    font-size: 13px;
    font-weight: 600;
}

QLabel#TopMeta {
    color: @text_faint;
    font-size: 10px;
}

QLabel#Hint {
    color: @text_faint;
    font-size: 9px;
}

QLabel#Banner {
    background-color: @surface;
    border: 1px solid @danger;
    border-radius: 8px;
    color: @danger;
    padding: 8px 12px;
    font-size: 10px;
}

QLabel#EmptyTitle {
    font-size: 22px;
    font-weight: 600;
}

QLabel#EmptySubtitle {
    color: @text_muted;
    font-size: 11px;
}

QFrame#Sidebar {
    background-color: @bg_alt;
    border-right: 1px solid @border;
}

QFrame#TopBar {
    background-color: @bg;
    border-bottom: 1px solid @border;
}

QFrame#Composer {
    background-color: @surface;
    border: 1px solid @border;
    border-radius: 14px;
}

QFrame#Composer[busy="true"] {
    border-color: @border_strong;
}

QPlainTextEdit#ComposerInput {
    background: transparent;
    border: none;
    color: @text;
    padding: 10px 12px;
    selection-background-color: @accent;
    selection-color: @accent_text;
}

QPlainTextEdit#Prompt, QPlainTextEdit#SystemPrompt {
    background-color: @surface;
    border: 1px solid @border;
    border-radius: 8px;
    color: @text;
    padding: 7px 9px;
    selection-background-color: @accent;
    selection-color: @accent_text;
}

QPushButton {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    color: @text;
    padding: 6px 10px;
}

QPushButton:hover {
    background-color: @surface_hover;
}

QPushButton:pressed {
    background-color: @surface_active;
}

QPushButton:disabled {
    color: @text_faint;
}

QPushButton#Primary {
    background-color: @accent;
    color: @accent_text;
    font-weight: 600;
    padding: 7px 16px;
}

QPushButton#Primary:hover {
    background-color: @accent_hover;
}

QPushButton#NavButton {
    text-align: left;
    padding: 9px 10px;
    color: @text_muted;
}

QPushButton#NavButton:hover {
    color: @text;
}

QPushButton#Send {
    background-color: @accent;
    border-radius: 9px;
    padding: 3px;
}

QPushButton#Send:hover {
    background-color: @accent_hover;
}

QPushButton#IconButton {
    border-radius: 8px;
    padding: 4px;
}

QPushButton#Stop {
    background-color: @surface_hover;
    border: 1px solid @border_strong;
    border-radius: 9px;
    padding: 3px;
}

QPushButton#Stop:hover {
    background-color: @surface_active;
}

QPushButton#Suggestion {
    background-color: @surface;
    border: 1px solid @border;
    border-radius: 10px;
    color: @text_muted;
    padding: 12px 14px;
    text-align: left;
    font-size: 11px;
}

QPushButton#Suggestion:hover {
    background-color: @surface_hover;
    border-color: @border_strong;
    color: @text;
}

QPushButton#Danger {
    color: @danger;
}

QListWidget#Navigation {
    background: transparent;
    border: none;
    outline: none;
    padding: 4px 2px;
}

QListWidget#Navigation::item {
    border-radius: 8px;
    color: @text_muted;
    margin: 1px 2px;
    padding: 9px 10px;
}

QListWidget#Navigation::item:hover {
    background-color: @surface_hover;
    color: @text;
}

QListWidget#Navigation::item:selected {
    background-color: @surface_active;
    color: @text;
}

QTextBrowser {
    background: transparent;
    border: none;
    selection-background-color: @accent;
    selection-color: @accent_text;
}

QTextBrowser:focus {
    border: none;
}

QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {
    background-color: @surface;
    border: 1px solid @border;
    border-radius: 8px;
    color: @text;
    padding: 6px 9px;
    selection-background-color: @accent;
    selection-color: @accent_text;
}

QComboBox {
    padding-right: 26px;
}

QComboBox:hover, QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover {
    border-color: @border_strong;
}

QComboBox:focus, QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: @accent;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QComboBox QAbstractItemView {
    background-color: @surface;
    border: 1px solid @border;
    color: @text;
    outline: none;
    selection-background-color: @surface_active;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}

QScrollBar::handle:vertical {
    background: @border_strong;
    border-radius: 3px;
    min-height: 32px;
}

QScrollBar::handle:vertical:hover {
    background: @text_faint;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
}

QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px;
}

QScrollBar::handle:horizontal {
    background: @border_strong;
    border-radius: 3px;
    min-width: 32px;
}

QSplitter::handle {
    background: transparent;
}

QMenu {
    background-color: @surface;
    border: 1px solid @border;
    padding: 4px;
}

QMenu::item {
    border-radius: 6px;
    color: @text;
    padding: 7px 18px;
}

QMenu::item:selected {
    background-color: @surface_hover;
}

QMenu::separator {
    background: @border;
    height: 1px;
    margin: 4px 8px;
}

QToolTip {
    background-color: @surface;
    border: 1px solid @border;
    color: @text;
    padding: 4px 7px;
}

QCheckBox {
    color: @text_muted;
    spacing: 8px;
}

QMessageBox {
    background-color: @bg;
}

QScrollArea {
    background: transparent;
    border: none;
}
"""


def tokens_for(name: str) -> dict[str, str]:
    return dict(TOKENS.get(name, TOKENS["dark"]))


def build_qss(tokens: dict[str, str]) -> str:
    return _TOKEN.sub(lambda match: tokens.get(match.group(1), match.group(0)), _QSS)


def apply(app: QApplication, name: str) -> dict[str, str]:
    tokens = tokens_for(name)
    app.setStyleSheet(build_qss(tokens))
    return tokens


def icon_color(tokens: dict[str, str]) -> str:
    return tokens.get("text_muted", "#8b94a7")
