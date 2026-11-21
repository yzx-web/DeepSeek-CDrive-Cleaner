# -*- coding: utf-8 -*-
"""统一的手绘矢量图标库。

不使用 emoji 或外部图片：所有图标由 QPainter 绘制，能随主题着色、任意缩放，
在 125%/150% DPI 下也保持干净。
"""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QLinearGradient, QPainter, QPainterPath, QPen,
                           QRadialGradient)
from PySide6.QtWidgets import QWidget


def _rr(p: QPainter, rect: QRectF, radius: float, fill: Optional[QColor] = None,
        stroke: Optional[QColor] = None, width: float = 1.6) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    if fill is not None:
        p.fillPath(path, fill)
    if stroke is not None:
        p.setPen(QPen(stroke, width))
        p.drawPath(path)
    p.restore()


def _line(p: QPainter, points: list[tuple[float, float]], color: QColor,
          width: float = 1.7, close: bool = False) -> None:
    p.save()
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    path = QPainterPath()
    path.moveTo(QPointF(*points[0]))
    for point in points[1:]:
        path.lineTo(QPointF(*point))
    if close:
        path.closeSubpath()
    p.drawPath(path)
    p.restore()


def _scale_rect(rect: QRectF, box: int = 24) -> tuple[float, float, float]:
    """把 24×24 的设计坐标映射到目标矩形。"""
    s = min(rect.width(), rect.height()) / box
    ox = rect.center().x() - box * s / 2
    oy = rect.center().y() - box * s / 2
    return s, ox, oy


def draw_glyph(p: QPainter, name: str, rect: QRectF, color: QColor,
               width: float = 1.7) -> None:
    """在 rect 中绘制一个 24×24 网格的线性图标。"""
    s, ox, oy = _scale_rect(rect)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.translate(ox, oy)
    p.scale(s, s)

    def L(points: list[tuple[float, float]], w: float = width, close: bool = False) -> None:
        _line(p, points, color, w, close)

    def R(x: float, y: float, w: float, h: float, r: float = 3, fill: Optional[QColor] = None,
          stroke: Optional[QColor] = None, sw: float = width) -> None:
        _rr(p, QRectF(x, y, w, h), r, fill, stroke, sw)

    def circle(x: float, y: float, r: float, fill: Optional[QColor] = None,
               stroke: Optional[QColor] = None, sw: float = width) -> None:
        p.save()
        p.setPen(QPen(stroke, sw) if stroke else Qt.PenStyle.NoPen)
        p.setBrush(fill if fill else Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(x, y), r, r)
        p.restore()

    if name == "dashboard":
        for x, y in [(3.5, 3.5), (13.5, 3.5), (3.5, 13.5), (13.5, 13.5)]:
            R(x, y, 7, 7, 2.2, stroke=color)
    elif name == "clean":
        # 一把轻盈的扫帚 + 星光
        L([(5, 18), (12, 11), (16, 15), (9, 22)], close=True)
        R(10.5, 2.5, 6.2, 4.6, 1.6, fill=QColor(color.red(), color.green(), color.blue(), 34), stroke=color)
        L([(13.6, 7.1), (16.5, 11.5)], 1.3)
        L([(5.1, 18.0), (7.4, 20.3)], 1.1)
        L([(9.2, 14.7), (11.4, 17.0)], 1.1)
    elif name == "search":
        circle(10.2, 10.2, 6.3, stroke=color)
        L([(15, 15), (21, 21)], 1.8)
    elif name == "history":
        circle(12, 12, 8, stroke=color)
        L([(12, 7.5), (12, 12), (15.6, 14.2)], 1.7)
        L([(4.1, 12), (2.1, 9.3), (5.3, 9.0)], 1.3)
    elif name == "settings":
        # 三枚现代滑块，而非上世纪的齿轮
        for y, knob_x in [(6, 15), (12, 8), (18, 17)]:
            L([(3, y), (21, y)], 1.3)
            circle(knob_x, y, 2.5, fill=color)
        # 细描边让旋钮有立体感
    elif name == "folder":
        path = QPainterPath()
        path.moveTo(2.8, 7.2)
        path.lineTo(8.2, 7.2)
        path.lineTo(9.8, 9.0)
        path.lineTo(21.2, 9.0)
        path.lineTo(20.2, 19.6)
        path.lineTo(3.8, 19.6)
        path.closeSubpath()
        p.save()
        p.setPen(QPen(color, width))
        p.setBrush(QColor(color.red(), color.green(), color.blue(), 28))
        p.drawPath(path)
        p.restore()
    elif name == "trash":
        R(5.2, 6.4, 13.6, 14.7, 2.8, stroke=color)
        L([(3.6, 6.4), (20.4, 6.4)], 1.8)
        L([(9.0, 3.2), (15.0, 3.2)], 1.6)
        L([(9.4, 10.0), (9.4, 17.2)], 1.2)
        L([(12.0, 10.0), (12.0, 17.2)], 1.2)
        L([(14.6, 10.0), (14.6, 17.2)], 1.2)
    elif name == "download":
        L([(12, 3.5), (12, 15.2)], 1.8)
        L([(7.4, 10.8), (12, 15.4), (16.6, 10.8)], 1.8)
        L([(4.2, 18.8), (4.2, 20.3), (19.8, 20.3), (19.8, 18.8)], 1.5)
    elif name == "video":
        rr = QRectF(rect.left(), rect.top() + 1, rect.width() - 4, rect.height() - 2)
        p.drawRoundedRect(rr, 3, 3)
        p.drawLine(QPointF(rect.right() - 4, rect.center().y()),
                   QPointF(rect.right(), rect.top() + 3))
        p.drawLine(QPointF(rect.right() - 4, rect.center().y()),
                   QPointF(rect.right(), rect.bottom() - 3))
        p.drawLine(QPointF(rect.right(), rect.top() + 3),
                   QPointF(rect.right(), rect.bottom() - 3))
        p.drawLine(QPointF(rect.left() + 3, rect.center().y()),
                   QPointF(rect.left() + 6, rect.center().y() - 2))
        p.drawLine(QPointF(rect.left() + 3, rect.center().y()),
                   QPointF(rect.left() + 6, rect.center().y() + 2))
        p.drawLine(QPointF(rect.left() + 6, rect.center().y() - 2),
                   QPointF(rect.left() + 6, rect.center().y() + 2))
    elif name == "photo":
        R(3.2, 4.2, 17.6, 15.6, 2.8, stroke=color)
        circle(8.4, 9.6, 2.1, fill=color)
        L([(4.6, 17.7), (10.4, 12.3), (13.2, 15.0), (16.0, 12.6), (19.4, 16.0)], 1.4)
    elif name == "bolt":
        L([(13.2, 2.6), (5.3, 13.4), (11.2, 13.4), (9.8, 21.4), (18.7, 10.2), (12.7, 10.2)], 1.6, close=True)
    elif name == "globe":
        circle(12, 12, 8.6, stroke=color)
        p.save()
        p.setPen(QPen(color, 1.3))
        p.drawEllipse(QPointF(12, 12), 4.2, 8.6)
        p.drawLine(QPointF(3.4, 12), QPointF(20.6, 12))
        p.drawArc(QRectF(5.0, 6.2, 14.0, 11.6), 20 * 16, 140 * 16)
        p.restore()
    elif name == "doc":
        path = QPainterPath()
        path.moveTo(5.2, 2.8)
        path.lineTo(14.0, 2.8)
        path.lineTo(19.2, 8.0)
        path.lineTo(19.2, 21.2)
        path.lineTo(5.2, 21.2)
        path.closeSubpath()
        p.save()
        p.setPen(QPen(color, width))
        p.setBrush(QColor(color.red(), color.green(), color.blue(), 22))
        p.drawPath(path)
        p.restore()
        L([(14.0, 2.9), (14.0, 8.1), (19.1, 8.1)], 1.3)
        for y in (11.6, 14.6, 17.6):
            L([(8.3, y), (16.0, y)], 1.2)
    elif name == "close":
        L([(5, 5), (19, 19)], 1.6)
        L([(19, 5), (5, 19)], 1.6)
    elif name == "minimize":
        L([(5, 12), (19, 12)], 1.6)
    elif name == "maximize":
        R(5.0, 5.0, 14.0, 14.0, 2.0, stroke=color, sw=1.5)
    elif name == "restore":
        R(7.2, 7.2, 12.0, 12.0, 1.8, stroke=color, sw=1.3)
        R(4.0, 4.0, 12.0, 12.0, 1.8, stroke=color, sw=1.3)
    elif name == "chevron":
        L([(8, 5), (15, 12), (8, 19)], 1.7)
    elif name == "chevron_down":
        L([(5, 8), (12, 15), (19, 8)], 1.7)
    elif name == "check":
        L([(4.5, 12.4), (9.6, 17.2), (19.8, 6.4)], 2.2)
    elif name == "sparkles":
        L([(12, 2.5), (13.2, 8.2), (18.8, 9.4), (13.2, 10.6), (12, 16.3), (10.8, 10.6), (5.2, 9.4), (10.8, 8.2)], 1.5, close=True)
        L([(19.0, 15.2), (19.7, 17.2), (21.6, 18.0), (19.7, 18.7), (19.0, 20.7), (18.3, 18.7), (16.4, 18.0), (18.3, 17.2)], 1.2, close=True)
    elif name == "shield":
        L([(12, 2.7), (20, 6.0), (18.8, 14.6), (12, 21.1), (5.2, 14.6), (4, 6.0)], 1.6, close=True)
        L([(8.6, 12.0), (11.1, 14.5), (15.8, 9.6)], 1.6)
    elif name == "power":
        circle(12, 12, 8.0, stroke=color)
        L([(12, 6.9), (12, 12.4)], 1.6)
        L([(8.6, 9.0), (8.6, 9.0)], 0.1)
        p.save()
        p.setPen(QPen(color, 1.5))
        p.drawArc(QRectF(7.0, 7.3, 10.0, 9.6), 20 * 16, 140 * 16)
        p.restore()
    elif name == "info":
        circle(12, 12, 8.7, stroke=color)
        circle(12, 7.5, 1.25, fill=color)
        L([(12, 10.7), (12, 17.0)], 1.5)
    elif name == "external":
        R(4.0, 7.0, 12.4, 12.4, 2.2, stroke=color, sw=1.3)
        L([(11.0, 4.0), (20.0, 4.0), (20.0, 13.0)], 1.4)
        L([(19.6, 4.4), (12.2, 11.8)], 1.4)
    elif name == "clock":
        circle(12, 12, 8.2, stroke=color)
        L([(12, 7.2), (12, 12.2), (15.7, 14.3)], 1.5)
    elif name == "disk":
        p.save()
        p.setPen(QPen(color, width))
        p.setBrush(QColor(color.red(), color.green(), color.blue(), 25))
        p.drawRoundedRect(QRectF(3.0, 4.0, 18.0, 16.0), 4, 4)
        p.drawLine(QPointF(7.0, 8.2), QPointF(17.0, 8.2))
        p.setBrush(color)
        p.drawEllipse(QPointF(16.6, 15.2), 1.2, 1.2)
        p.restore()
    elif name == "warning":
        L([(12, 3.0), (21.3, 20.2), (2.7, 20.2)], 1.5, close=True)
        L([(12, 8.5), (12, 14.2)], 1.6)
        circle(12, 17.4, 0.9, fill=color)
    elif name == "lock":
        R(4.8, 10.0, 14.4, 11.0, 3.0, stroke=color)
        p.save()
        p.setPen(QPen(color, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(QRectF(7.4, 3.8, 9.2, 10.0), 0, 180 * 16)
        p.restore()
        circle(12, 15.0, 1.2, fill=color)
    else:
        circle(12, 12, 4, fill=color)
    p.restore()


class Glyph(QWidget):
    """轻量图标控件，可设置颜色与粗细。"""

    def __init__(self, name: str, color: QColor, size: int = 20, stroke: float = 1.7,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.name = name
        self.color = QColor(color)
        self.stroke = stroke
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def set_color(self, color: QColor) -> None:
        self.color = QColor(color)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        draw_glyph(p, self.name, QRectF(1, 1, self.width() - 2, self.height() - 2),
                   self.color, self.stroke)


class LogoMark(QWidget):
    """紫蓝渐变水晶质感 Logo：一枚悬浮的宝石，而非普通圆形字母。"""

    def __init__(self, size: int = 44, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w = self.width()
        h = self.height()
        # 外发光
        glow = QRadialGradient(w / 2, h / 2 + 4, w * 0.72)
        glow.setColorAt(0.0, QColor(139, 108, 255, 80))
        glow.setColorAt(0.55, QColor(150, 90, 255, 25))
        glow.setColorAt(1.0, QColor(120, 80, 255, 0))
        p.fillRect(self.rect(), glow)
        # 圆角宝石底座
        base = QRectF(3.5, 3.5, w - 7, h - 7)
        path = QPainterPath()
        path.addRoundedRect(base, w * 0.26, h * 0.26)
        grad = QLinearGradient(base.topLeft(), base.bottomRight())
        grad.setColorAt(0.0, QColor("#7976FF"))
        grad.setColorAt(0.34, QColor("#625EF4"))
        grad.setColorAt(0.72, QColor("#A455F8"))
        grad.setColorAt(1.0, QColor("#D06BFF"))
        p.fillPath(path, grad)
        # 顶部玻璃高光
        gloss = QLinearGradient(0, 3, 0, h / 2)
        gloss.setColorAt(0, QColor(255, 255, 255, 108))
        gloss.setColorAt(1, QColor(255, 255, 255, 0))
        p.save()
        p.setClipPath(path)
        p.fillRect(QRectF(3, 3, w - 6, h / 2), gloss)
        # 内层薄雾
        mist = QRadialGradient(w * 0.25, h * 0.85, w * 0.8)
        mist.setColorAt(0, QColor(255, 255, 255, 0))
        mist.setColorAt(1, QColor(40, 18, 120, 60))
        p.fillRect(self.rect(), mist)
        # 中心水晶切面
        cx, cy = w / 2, h / 2 + 0.5
        top = QPointF(cx, 9.5)
        left = QPointF(9.5, cy + 2.0)
        right = QPointF(w - 9.5, cy + 2.0)
        bottom = QPointF(cx, h - 8.5)
        p.setBrush(QColor(255, 255, 255, 176))
        p.setPen(QPen(QColor(255, 255, 255, 210), 1.0))
        p.drawPolygon([top, right, bottom, left])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(220, 235, 255, 55))
        p.drawPolygon([top, left, QPointF(cx, cy + 4), right])
        p.setBrush(QColor(58, 43, 150, 44))
        p.drawPolygon([left, QPointF(cx, cy + 4), bottom])
        p.setBrush(QColor(255, 255, 255, 60))
        p.drawPolygon([QPointF(cx, cy + 4), right, bottom])
        # 两枚高光点
        p.setBrush(QColor(255, 255, 255, 140))
        p.drawEllipse(QPointF(14, 13), 1.6, 1.6)
        p.setBrush(QColor(255, 255, 255, 60))
        p.drawEllipse(QPointF(16.5, 11.2), 0.8, 0.8)
        p.restore()
        # 外框
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 95), 1.0))
        p.drawRoundedRect(base.adjusted(0.5, 0.5, -0.5, -0.5), w * 0.26, h * 0.26)

    @staticmethod
    def make_pixmap(size: int = 256) -> "QPixmap":  # type: ignore[name-defined]
        from PySide6.QtGui import QPixmap
        pix = QPixmap(size, size)
        pix.fill(Qt.GlobalColor.transparent)
        widget = LogoMark(size)
        widget.render(pix)
        return pix
