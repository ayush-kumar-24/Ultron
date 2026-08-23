"""Prototype stylesheet built from design tokens."""

from __future__ import annotations

from maira.ui.prototype.theme import tokens as t


def build_stylesheet() -> str:
  return f"""
* {{
  font-family: {t.FONT_FAMILY};
  outline: none;
}}

QMainWindow, QWidget#ProtoRoot {{
  background-color: {t.BG_PRIMARY};
  color: {t.TEXT_PRIMARY};
}}

QWidget#Workspace {{
  background-color: {t.BG_PRIMARY};
}}

QWidget#Sidebar {{
  background-color: {t.BG_SECONDARY};
  border-right: 1px solid {t.BORDER};
}}

QLabel#BrandWordmark {{
  color: {t.TEXT_PRIMARY};
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 2.5px;
}}

QLabel#PageTitle {{
  color: {t.TEXT_HEADING};
  font-size: 22px;
  font-weight: 500;
  letter-spacing: -0.3px;
}}

QLabel#PageSubtitle {{
  color: {t.TEXT_SECONDARY};
  font-size: 14px;
  font-weight: 400;
}}

QLabel#Greeting {{
  color: {t.TEXT_HEADING};
  font-size: 28px;
  font-weight: 500;
  letter-spacing: -0.5px;
}}

QLabel#GreetingSub {{
  color: {t.TEXT_SECONDARY};
  font-size: 15px;
  font-weight: 400;
}}

QLabel#SectionLabel {{
  color: {t.TEXT_MUTED};
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 1.2px;
  text-transform: uppercase;
}}

QLabel#Muted {{
  color: {t.TEXT_MUTED};
  font-size: 13px;
}}

QLabel#Secondary {{
  color: {t.TEXT_SECONDARY};
  font-size: 13px;
}}

QLabel#EmptyTitle {{
  color: {t.TEXT_SECONDARY};
  font-size: 16px;
  font-weight: 500;
}}

QLabel#EmptyBody {{
  color: {t.TEXT_MUTED};
  font-size: 13px;
}}

QLineEdit, QTextEdit, QPlainTextEdit {{
  background-color: {t.BG_INPUT};
  border: 1px solid {t.BORDER};
  border-radius: {t.RADIUS_MD}px;
  color: {t.TEXT_PRIMARY};
  padding: 10px 14px;
  selection-background-color: rgba(255,255,255,0.12);
  selection-color: {t.TEXT_PRIMARY};
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
  border: 1px solid {t.BORDER_FOCUS};
}}

QLineEdit::placeholder, QTextEdit::placeholder, QPlainTextEdit::placeholder {{
  color: {t.TEXT_MUTED};
}}

QPushButton#PrimaryButton {{
  background-color: {t.CTA_FILL};
  color: {t.BG_PRIMARY};
  border: none;
  border-radius: {t.RADIUS_MD}px;
  padding: 10px 22px;
  font-size: 13px;
  font-weight: 600;
}}

QPushButton#PrimaryButton:hover {{
  background-color: {t.CTA_FILL_HOVER};
}}

QPushButton#PrimaryButton:pressed {{
  background-color: {t.ACCENT_SOFT};
}}

QPushButton#GhostButton {{
  background-color: transparent;
  color: {t.TEXT_SECONDARY};
  border: 1px solid {t.BORDER};
  border-radius: {t.RADIUS_MD}px;
  padding: 8px 16px;
  font-size: 13px;
}}

QPushButton#GhostButton:hover {{
  border: 1px solid {t.BORDER_HOVER};
  color: {t.TEXT_PRIMARY};
  background-color: {t.BG_HOVER};
}}

QPushButton#QuickAction {{
  background-color: transparent;
  color: {t.TEXT_SECONDARY};
  border: 1px solid {t.BORDER};
  border-radius: {t.RADIUS_PILL}px;
  padding: 8px 16px;
  font-size: 12px;
}}

QPushButton#QuickAction:hover {{
  border: 1px solid {t.BORDER_HOVER};
  color: {t.TEXT_PRIMARY};
  background-color: rgba(255,255,255,0.03);
}}

QPushButton#IconChip {{
  background-color: transparent;
  border: none;
  border-radius: 8px;
  color: {t.TEXT_SECONDARY};
  padding: 6px;
}}

QPushButton#IconChip:hover {{
  background-color: rgba(255,255,255,0.06);
  color: {t.TEXT_PRIMARY};
}}

QScrollArea {{
  background: transparent;
  border: none;
}}

QScrollBar:vertical {{
  background: transparent;
  width: 8px;
  margin: 0;
}}

QScrollBar::handle:vertical {{
  background: rgba(255,255,255,0.10);
  border-radius: 4px;
  min-height: 24px;
}}

QScrollBar::handle:vertical:hover {{
  background: rgba(255,255,255,0.18);
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
  height: 0;
  background: none;
}}

QScrollBar:horizontal {{
  height: 0;
}}

QComboBox {{
  background-color: {t.BG_ELEVATED};
  border: 1px solid {t.BORDER};
  border-radius: {t.RADIUS_SM}px;
  color: {t.TEXT_PRIMARY};
  padding: 8px 12px;
  min-height: 20px;
}}

QComboBox:hover {{
  border: 1px solid {t.BORDER_HOVER};
}}

QComboBox::drop-down {{
  border: none;
  width: 24px;
}}

QComboBox QAbstractItemView {{
  background-color: {t.BG_ELEVATED};
  border: 1px solid {t.BORDER_HOVER};
  selection-background-color: rgba(255,255,255,0.08);
  color: {t.TEXT_PRIMARY};
  outline: none;
}}

QSlider::groove:horizontal {{
  height: 3px;
  background: rgba(255,255,255,0.10);
  border-radius: 2px;
}}

QSlider::handle:horizontal {{
  background: {t.TEXT_PRIMARY};
  width: 14px;
  height: 14px;
  margin: -6px 0;
  border-radius: 7px;
}}

QSlider::sub-page:horizontal {{
  background: rgba(255,255,255,0.35);
  border-radius: 2px;
}}

QCheckBox, QRadioButton {{
  color: {t.TEXT_SECONDARY};
  spacing: 10px;
}}

QCheckBox::indicator, QRadioButton::indicator {{
  width: 16px;
  height: 16px;
  border: 1px solid {t.BORDER_HOVER};
  background: {t.BG_SURFACE};
}}

QCheckBox::indicator {{
  border-radius: 4px;
}}

QRadioButton::indicator {{
  border-radius: 9px;
}}

QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
  background: {t.TEXT_PRIMARY};
  border-color: {t.TEXT_PRIMARY};
}}

QListWidget {{
  background: transparent;
  border: none;
  outline: none;
  color: {t.TEXT_SECONDARY};
}}

QListWidget::item {{
  padding: 10px 12px;
  border-radius: {t.RADIUS_SM}px;
}}

QListWidget::item:selected {{
  background: rgba(255,255,255,0.06);
  color: {t.TEXT_PRIMARY};
}}

QListWidget::item:hover {{
  background: rgba(255,255,255,0.04);
}}

QFrame#Card {{
  background-color: {t.BG_SURFACE};
  border: 1px solid {t.BORDER};
  border-radius: {t.RADIUS_MD}px;
}}

QFrame#ElevatedCard {{
  background-color: {t.BG_ELEVATED};
  border: 1px solid {t.BORDER};
  border-radius: {t.RADIUS_MD}px;
}}

QFrame#Divider {{
  background-color: {t.BORDER};
  max-height: 1px;
  border: none;
}}

QToolTip {{
  background-color: {t.BG_ELEVATED};
  color: {t.TEXT_PRIMARY};
  border: 1px solid {t.BORDER_HOVER};
  padding: 6px 10px;
  border-radius: 6px;
}}

QWidget#OverlayScrim {{
  background-color: rgba(0, 0, 0, 0.62);
}}

QFrame#OverlayPanel {{
  background-color: {t.BG_ELEVATED};
  border: 1px solid {t.BORDER_ACTIVE};
  border-radius: {t.RADIUS_LG}px;
}}

QLabel#Toast {{
  background-color: {t.BG_ELEVATED};
  color: {t.TEXT_PRIMARY};
  border: 1px solid {t.BORDER_HOVER};
  border-radius: {t.RADIUS_MD}px;
  padding: 12px 18px;
}}

QLabel#ErrorBanner {{
  background-color: rgba(248, 113, 113, 0.08);
  color: #FCA5A5;
  border: 1px solid rgba(248, 113, 113, 0.22);
  border-radius: {t.RADIUS_MD}px;
  padding: 14px 16px;
}}

QLabel#Tag {{
  background-color: rgba(255,255,255,0.05);
  color: {t.TEXT_SECONDARY};
  border: 1px solid {t.BORDER};
  border-radius: 6px;
  padding: 2px 8px;
  font-size: 11px;
}}
"""
