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
        "settings_control_border": "#69758a",
        "settings_success": "#5ad1a3",
        "settings_error": "#ff7f7f",
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
        "settings_control_border": "#7b8494",
        "settings_success": "#18794e",
        "settings_error": "#b42318",
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

QFrame#WindowShell {
    background-color: @bg;
    border: 1px solid @border_strong;
}

QWidget#WindowTitleBar {
    background-color: @bg_alt;
    border-bottom: 1px solid @border;
}

QLabel#WindowTitle {
    color: @text;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.3px;
}

QWidget#WindowTitleBar[active="false"] {
    background-color: @bg;
}

QLabel#WindowTitle[active="false"] {
    color: @text_faint;
}

QWidget#WindowControls {
    background: transparent;
}

QToolButton[windowControl="true"] {
    background: transparent;
    border: none;
    border-radius: 0;
    padding: 0;
}

QToolButton[windowControl="true"]:hover {
    background-color: @surface_hover;
}

QToolButton[windowControl="true"]:pressed {
    background-color: @surface_active;
}

QToolButton[windowControl="true"]:focus {
    border-bottom: 2px solid @accent;
}

QToolButton#WindowClose:hover {
    background-color: #c43d49;
}

QToolButton#WindowClose:pressed {
    background-color: #a22f3a;
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

QFrame#Composer QComboBox {
    background-color: @bg_alt;
    border: 1px solid transparent;
    padding: 4px 26px 4px 8px;
    font-size: 11px;
}

QFrame#Composer QComboBox:hover {
    background-color: @surface_hover;
    border-color: @border_strong;
}

QFrame#Composer QComboBox:focus {
    border-color: @accent;
}

QFrame#Composer QComboBox:disabled {
    color: @text_faint;
}

QFrame#Composer QComboBox QLineEdit {
    background: transparent;
    border: none;
    padding: 0;
    font-size: 11px;
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

QListWidget#ModelList {
    background-color: @surface;
    border: 1px solid @border;
    border-radius: 8px;
    color: @text;
    outline: none;
    padding: 4px;
}

QListWidget#ModelList::item {
    padding: 7px 10px;
    border-radius: 5px;
}

QListWidget#ModelList::item:hover {
    background-color: @surface_hover;
}

QListWidget#ModelList::item:selected {
    background-color: @surface_active;
    color: @accent;
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

/* Settings use larger type and explicit boundaries without changing chat density. */
QDialog#SettingsDialog QWidget {
    font-size: 11pt;
}

QDialog#SettingsDialog QWidget#SettingsEditor {
    background-color: @bg;
}

QDialog#SettingsDialog QLabel#SettingsTitle {
    font-size: 20pt;
    font-weight: 600;
}

QDialog#SettingsDialog QLabel#SettingsHelp {
    color: @text_muted;
    font-size: 10pt;
}

QDialog#SettingsDialog QLabel#SettingsFieldError {
    color: @settings_error;
    font-size: 10pt;
}

QDialog#SettingsDialog QGroupBox {
    color: @text;
    border: none;
    border-top: 1px solid @border_strong;
    margin-top: 12px;
    padding-top: 20px;
    font-size: 12pt;
    font-weight: 600;
}

QDialog#SettingsDialog QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding-right: 10px;
    background-color: @bg;
}

QDialog#SettingsDialog QPushButton {
    min-height: 24px;
    border: 1px solid @settings_control_border;
}

QDialog#SettingsDialog QPushButton#SettingsTab {
    border: 1px solid transparent;
    color: @text_muted;
    padding: 8px 16px;
}

QDialog#SettingsDialog QPushButton#SettingsTab:checked {
    color: @text;
    background-color: @surface_active;
    border-bottom: 3px solid @accent;
    font-weight: 600;
}

QDialog#SettingsDialog QComboBox,
QDialog#SettingsDialog QLineEdit,
QDialog#SettingsDialog QSpinBox,
QDialog#SettingsDialog QDoubleSpinBox,
QDialog#SettingsDialog QPlainTextEdit,
QDialog#SettingsDialog QListWidget#ModelList {
    border: 1px solid @settings_control_border;
}

QDialog#SettingsDialog QComboBox,
QDialog#SettingsDialog QLineEdit,
QDialog#SettingsDialog QSpinBox,
QDialog#SettingsDialog QDoubleSpinBox {
    min-height: 24px;
}

QDialog#SettingsDialog QCheckBox,
QDialog#SettingsDialog QRadioButton {
    color: @text;
    min-height: 32px;
    spacing: 10px;
}

QDialog#SettingsDialog QCheckBox::indicator,
QDialog#SettingsDialog QRadioButton::indicator,
QDialog#SettingsDialog QGroupBox::indicator {
    width: 18px;
    height: 18px;
}

QDialog#SettingsDialog QPushButton:focus,
QDialog#SettingsDialog QComboBox:focus,
QDialog#SettingsDialog QLineEdit:focus,
QDialog#SettingsDialog QSpinBox:focus,
QDialog#SettingsDialog QDoubleSpinBox:focus,
QDialog#SettingsDialog QPlainTextEdit:focus,
QDialog#SettingsDialog QListWidget#ModelList:focus {
    border: 2px solid @accent;
}

QDialog#SettingsDialog QCheckBox:focus,
QDialog#SettingsDialog QRadioButton:focus,
QDialog#SettingsDialog QGroupBox:focus {
    outline: 2px solid @accent;
}

QDialog#SettingsDialog QLabel#SettingsStatus {
    color: @text_muted;
    background-color: @surface;
    border: 1px solid @settings_control_border;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 10pt;
}

QDialog#SettingsDialog QLabel#SettingsStatus[status="error"] {
    color: @settings_error;
    border-color: @settings_error;
}

QDialog#SettingsDialog QLabel#SettingsStatus[status="success"] {
    color: @settings_success;
    border-color: @settings_success;
}

QDialog#SettingsDialog QProgressBar {
    border: none;
    background-color: @surface_active;
    max-height: 4px;
}

QDialog#SettingsDialog QProgressBar::chunk {
    background-color: @accent;
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
