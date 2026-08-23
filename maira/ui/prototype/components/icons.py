"""Thin-line icon painting helpers for the prototype sidebar and controls."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen


def draw_icon(painter: QPainter, name: str, rect: QRectF, color: QColor) -> None:
  painter.save()
  pen = QPen(color)
  pen.setWidthF(1.4)
  pen.setCapStyle(Qt.PenCapStyle.RoundCap)
  pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
  painter.setPen(pen)
  painter.setBrush(Qt.BrushStyle.NoBrush)

  x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
  cx, cy = x + w / 2, y + h / 2
  s = min(w, h) * 0.34

  if name == "home":
    painter.drawLine(QPointF(cx, cy - s), QPointF(cx - s, cy))
    painter.drawLine(QPointF(cx, cy - s), QPointF(cx + s, cy))
    painter.drawRect(QRectF(cx - s * 0.7, cy - s * 0.05, s * 1.4, s * 1.05))
  elif name == "chat":
    painter.drawRoundedRect(QRectF(cx - s, cy - s * 0.75, s * 2, s * 1.35), 3, 3)
    painter.drawLine(QPointF(cx - s * 0.2, cy + s * 0.55), QPointF(cx - s * 0.55, cy + s))
  elif name == "memory":
    painter.drawEllipse(QPointF(cx - s * 0.35, cy), s * 0.55, s * 0.7)
    painter.drawEllipse(QPointF(cx + s * 0.35, cy), s * 0.55, s * 0.7)
  elif name == "tasks":
    box = QRectF(cx - s, cy - s, s * 0.85, s * 0.85)
    painter.drawRoundedRect(box, 2, 2)
    painter.drawLine(QPointF(cx - s * 0.75, cy - s * 0.55), QPointF(cx - s * 0.45, cy - s * 0.25))
    painter.drawLine(QPointF(cx - s * 0.45, cy - s * 0.25), QPointF(cx - s * 0.15, cy - s * 0.75))
    painter.drawLine(QPointF(cx + s * 0.15, cy - s * 0.55), QPointF(cx + s, cy - s * 0.55))
    painter.drawLine(QPointF(cx + s * 0.15, cy), QPointF(cx + s, cy))
    painter.drawLine(QPointF(cx + s * 0.15, cy + s * 0.55), QPointF(cx + s, cy + s * 0.55))
  elif name == "notes":
    painter.drawRoundedRect(QRectF(cx - s * 0.75, cy - s, s * 1.5, s * 2), 3, 3)
    painter.drawLine(QPointF(cx - s * 0.4, cy - s * 0.35), QPointF(cx + s * 0.4, cy - s * 0.35))
    painter.drawLine(QPointF(cx - s * 0.4, cy), QPointF(cx + s * 0.4, cy))
    painter.drawLine(QPointF(cx - s * 0.4, cy + s * 0.35), QPointF(cx + s * 0.15, cy + s * 0.35))
  elif name == "activity":
    pts = [
      QPointF(cx - s, cy + s * 0.2),
      QPointF(cx - s * 0.4, cy + s * 0.2),
      QPointF(cx - s * 0.1, cy - s),
      QPointF(cx + s * 0.35, cy + s * 0.85),
      QPointF(cx + s * 0.55, cy - s * 0.15),
      QPointF(cx + s, cy - s * 0.15),
    ]
    for i in range(len(pts) - 1):
      painter.drawLine(pts[i], pts[i + 1])
  elif name == "automations":
    path_pts = [
      QPointF(cx + s * 0.15, cy - s),
      QPointF(cx - s * 0.35, cy + s * 0.05),
      QPointF(cx + s * 0.05, cy + s * 0.05),
      QPointF(cx - s * 0.15, cy + s),
      QPointF(cx + s * 0.45, cy - s * 0.05),
      QPointF(cx + s * 0.05, cy - s * 0.05),
    ]
    for i in range(len(path_pts) - 1):
      painter.drawLine(path_pts[i], path_pts[i + 1])
  elif name == "settings":
    painter.drawEllipse(QPointF(cx, cy), s * 0.35, s * 0.35)
    for i in range(8):
      import math

      a = i * math.pi / 4
      painter.drawLine(
        QPointF(cx + math.cos(a) * s * 0.55, cy + math.sin(a) * s * 0.55),
        QPointF(cx + math.cos(a) * s * 0.85, cy + math.sin(a) * s * 0.85),
      )
  elif name == "search":
    painter.drawEllipse(QPointF(cx - s * 0.15, cy - s * 0.15), s * 0.55, s * 0.55)
    painter.drawLine(QPointF(cx + s * 0.25, cy + s * 0.25), QPointF(cx + s * 0.75, cy + s * 0.75))
  elif name == "mic":
    painter.drawRoundedRect(QRectF(cx - s * 0.35, cy - s, s * 0.7, s * 1.2), 6, 6)
    painter.drawArc(QRectF(cx - s * 0.7, cy - s * 0.2, s * 1.4, s * 1.1), 0 * 16, -180 * 16)
    painter.drawLine(QPointF(cx, cy + s * 0.9), QPointF(cx, cy + s))
  elif name == "attach":
    painter.drawArc(QRectF(cx - s * 0.2, cy - s, s * 0.9, s * 1.1), 50 * 16, 260 * 16)
    painter.drawLine(QPointF(cx + s * 0.25, cy - s * 0.35), QPointF(cx + s * 0.25, cy + s * 0.45))
  elif name == "send":
    painter.drawLine(QPointF(cx - s * 0.55, cy), QPointF(cx + s * 0.55, cy))
    painter.drawLine(QPointF(cx + s * 0.1, cy - s * 0.45), QPointF(cx + s * 0.55, cy))
    painter.drawLine(QPointF(cx + s * 0.1, cy + s * 0.45), QPointF(cx + s * 0.55, cy))
  elif name == "folder":
    painter.drawRoundedRect(QRectF(cx - s, cy - s * 0.35, s * 2, s * 1.35), 3, 3)
    painter.drawRoundedRect(QRectF(cx - s, cy - s * 0.75, s * 0.9, s * 0.45), 2, 2)
  elif name == "calendar":
    painter.drawRoundedRect(QRectF(cx - s, cy - s * 0.7, s * 2, s * 1.7), 3, 3)
    painter.drawLine(QPointF(cx - s, cy - s * 0.25), QPointF(cx + s, cy - s * 0.25))
    painter.drawLine(QPointF(cx - s * 0.4, cy - s), QPointF(cx - s * 0.4, cy - s * 0.45))
    painter.drawLine(QPointF(cx + s * 0.4, cy - s), QPointF(cx + s * 0.4, cy - s * 0.45))
  elif name == "list":
    for i, oy in enumerate((-0.6, 0.0, 0.6)):
      painter.drawEllipse(QPointF(cx - s * 0.7, cy + s * oy), 1.5, 1.5)
      painter.drawLine(QPointF(cx - s * 0.35, cy + s * oy), QPointF(cx + s * 0.8, cy + s * oy))
  elif name == "close":
    painter.drawLine(QPointF(cx - s * 0.6, cy - s * 0.6), QPointF(cx + s * 0.6, cy + s * 0.6))
    painter.drawLine(QPointF(cx + s * 0.6, cy - s * 0.6), QPointF(cx - s * 0.6, cy + s * 0.6))
  else:
    painter.drawEllipse(QPointF(cx, cy), s * 0.5, s * 0.5)

  painter.restore()
