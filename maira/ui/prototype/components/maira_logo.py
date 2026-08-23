"""Maira logo — nested diamond mark with transparent, premium glass treatment."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import (
  QColor,
  QLinearGradient,
  QPainter,
  QPainterPath,
  QPen,
  QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from maira.ui.prototype.theme import tokens as t

_SIZES = {
  "small": 28,
  "medium": 48,
  "large": 96,
  "xlarge": 160,
  "hero": 220,
}


def diamond_path(cx: float, cy: float, half: float) -> QPainterPath:
  """Axis-aligned diamond (square rotated 45°)."""
  path = QPainterPath()
  path.moveTo(cx, cy - half)
  path.lineTo(cx + half, cy)
  path.lineTo(cx, cy + half)
  path.lineTo(cx - half, cy)
  path.closeSubpath()
  return path


class MairaLogo(QWidget):
  """
  Geometric structure:
  - outer diamond frame (transparent stroke)
  - nested inner diamond (softer stroke)
  - left + right core nodes
  Premium look via layered transparency, soft bloom, and optional hover float.
  """

  def __init__(
    self,
    size: str = "medium",
    glowing: bool = False,
    animated: bool = False,
    hovering: bool = False,
    parent=None,
  ) -> None:
    super().__init__(parent)
    self._size_key = size if size in _SIZES else "medium"
    self._px = _SIZES[self._size_key]
    self._glowing = glowing
    self._animated = animated
    self._hovering = hovering
    self._phase = 0.0
    self._intensity = 0.28 if glowing else 0.10
    self._float_y = 0.0
    self._scale = 1.0
    pad = 56 if hovering or size in ("xlarge", "hero") else 28
    self._pad = pad
    self.setFixedSize(int(self._px * 1.4) + pad, int(self._px * 1.4) + pad)
    self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    self._timer: QTimer | None = None
    if animated or hovering:
      self._start_timer()

  def _start_timer(self) -> None:
    if self._timer is None:
      self._timer = QTimer(self)
      self._timer.timeout.connect(self._tick)
    self._timer.start(16)

  def set_size(self, size: str) -> None:
    self._size_key = size if size in _SIZES else "medium"
    self._px = _SIZES[self._size_key]
    pad = 56 if self._hovering or size in ("xlarge", "hero") else 28
    self._pad = pad
    self.setFixedSize(int(self._px * 1.4) + pad, int(self._px * 1.4) + pad)
    self.update()

  def set_glowing(self, glowing: bool) -> None:
    self._glowing = glowing
    self._intensity = 0.42 if glowing else 0.10
    self.update()

  def set_animated(self, animated: bool) -> None:
    self._animated = animated
    if animated or self._hovering:
      self._start_timer()
    elif self._timer is not None and not self._hovering:
      self._timer.stop()

  def set_hovering(self, hovering: bool) -> None:
    self._hovering = hovering
    if hovering:
      self._glowing = True
      self._animated = True
      self._start_timer()
    self.update()

  def set_intensity(self, value: float) -> None:
    self._intensity = max(0.04, min(0.85, value))
    self.update()

  def _tick(self) -> None:
    self._phase = (self._phase + 0.035) % (math.pi * 2)
    breathe = 0.5 + 0.5 * math.sin(self._phase)
    base = 0.38 if self._glowing else 0.12
    self._intensity = base * (0.72 + 0.28 * breathe)

    if self._hovering:
      self._float_y = math.sin(self._phase) * 12.0
      self._scale = 1.0 + 0.035 * math.sin(self._phase * 0.9)
    else:
      self._float_y = 0.0
      self._scale = 1.0
    self.update()

  def paintEvent(self, event) -> None:  # noqa: N802
    del event
    painter = QPainter(self)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    cx = self.width() / 2
    cy = self.height() / 2 + self._float_y
    s = self._px * self._scale
    intensity = self._intensity

    # --- ambient bloom (very soft, translucent) ---
    bloom_r = s * (1.35 if self._hovering else 1.05)
    bloom = QRadialGradient(cx, cy, bloom_r)
    lav = QColor(t.GLOW_LAVENDER)
    lav.setAlphaF(0.10 * intensity if self._hovering else 0.05 * intensity)
    mist = QColor(180, 180, 200)
    mist.setAlphaF(0.06 * intensity)
    clear = QColor(0, 0, 0, 0)
    bloom.setColorAt(0.0, mist)
    bloom.setColorAt(0.45, lav)
    bloom.setColorAt(1.0, clear)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(bloom)
    painter.drawEllipse(QPointF(cx, cy), bloom_r, bloom_r)

    # --- glass plate behind mark (transparent frosted diamond) ---
    glass_outer = diamond_path(cx, cy, s * 0.46)
    glass_fill = QRadialGradient(cx, cy - s * 0.12, s * 0.55)
    top = QColor(255, 255, 255)
    top.setAlphaF(0.045 + 0.03 * intensity)
    mid = QColor(160, 160, 180)
    mid.setAlphaF(0.025)
    glass_fill.setColorAt(0.0, top)
    glass_fill.setColorAt(0.55, mid)
    glass_fill.setColorAt(1.0, clear)
    painter.setBrush(glass_fill)
    painter.drawPath(glass_outer)

    # --- soft drop shadow under mark ---
    shadow = diamond_path(cx, cy + s * 0.03, s * 0.42)
    sh = QColor(0, 0, 0)
    sh.setAlphaF(0.28)
    painter.setBrush(sh)
    painter.drawPath(shadow)

    outer_w = max(1.6, s * 0.038)
    inner_w = max(1.1, s * 0.026)

    # Stroke colors — translucent silver, not solid white
    stroke_outer = QColor(210, 210, 220)
    stroke_outer.setAlphaF(0.42 + 0.28 * intensity)
    stroke_inner = QColor(190, 190, 205)
    stroke_inner.setAlphaF(0.28 + 0.22 * intensity)
    stroke_dim = QColor(170, 170, 185)
    stroke_dim.setAlphaF(0.20 + 0.15 * intensity)

    # --- outer diamond (ghost edge + main edge) ---
    outer = diamond_path(cx, cy, s * 0.42)
    ghost = QPen(QColor(140, 140, 160, int(40 + 50 * intensity)))
    ghost.setWidthF(outer_w + 2.5)
    ghost.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(ghost)
    painter.drawPath(outer)

    pen = QPen(stroke_outer)
    pen.setWidthF(outer_w)
    pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawPath(outer)

    # Highlight edge (top-left sheen) — clipped feel via gradient pen approximation
    sheen = QLinearGradient(cx - s * 0.3, cy - s * 0.35, cx + s * 0.2, cy)
    c0 = QColor(255, 255, 255)
    c0.setAlphaF(0.22 * intensity)
    c1 = QColor(255, 255, 255, 0)
    sheen.setColorAt(0.0, c0)
    sheen.setColorAt(1.0, c1)
    sheen_pen = QPen(QColor(230, 230, 240, int(55 + 40 * intensity)))
    sheen_pen.setWidthF(max(1.0, outer_w * 0.55))
    painter.setPen(sheen_pen)
    painter.drawLine(QPointF(cx, cy - s * 0.42), QPointF(cx - s * 0.42, cy))
    painter.drawLine(QPointF(cx, cy - s * 0.42), QPointF(cx + s * 0.42, cy))

    # --- inner diamond ---
    inner = diamond_path(cx, cy, s * 0.24)
    pen = QPen(stroke_inner)
    pen.setWidthF(inner_w)
    pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
    painter.setPen(pen)
    painter.drawPath(inner)

    # Inner fill — barely there glass
    inner_fill = QColor(200, 200, 215)
    inner_fill.setAlphaF(0.04 + 0.04 * intensity)
    painter.fillPath(inner, inner_fill)

    # --- core nodes (soft translucent gems) ---
    node_r = s * 0.052
    for nx in (cx - s * 0.24, cx + s * 0.24):
      node = diamond_path(nx, cy, node_r)
      node_grad = QRadialGradient(nx, cy - node_r * 0.3, node_r * 1.4)
      hi = QColor(230, 230, 240)
      hi.setAlphaF(0.55 + 0.2 * intensity)
      lo = QColor(150, 150, 170)
      lo.setAlphaF(0.18)
      node_grad.setColorAt(0.0, hi)
      node_grad.setColorAt(1.0, lo)
      painter.setPen(Qt.PenStyle.NoPen)
      painter.setBrush(node_grad)
      painter.drawPath(node)

      rim = QPen(QColor(220, 220, 230, int(70 + 50 * intensity)))
      rim.setWidthF(max(0.8, s * 0.01))
      painter.setBrush(Qt.BrushStyle.NoBrush)
      painter.setPen(rim)
      painter.drawPath(node)

    # Bridge lines — faint, transparent
    bridge = QPen(stroke_dim)
    bridge.setWidthF(max(0.9, s * 0.015))
    bridge.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(bridge)
    painter.drawLine(QPointF(cx - s * 0.175, cy), QPointF(cx - s * 0.07, cy))
    painter.drawLine(QPointF(cx + s * 0.07, cy), QPointF(cx + s * 0.175, cy))

    painter.end()
