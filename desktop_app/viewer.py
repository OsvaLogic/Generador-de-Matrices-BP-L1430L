from PyQt6.QtWidgets import QGraphicsView, QGraphicsPixmapItem, QGraphicsScene, QLabel
from PyQt6.QtGui import QPainter, QColor, QMouseEvent, QPen
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QLineF

class ItemSignals(QObject):
    """Clase auxiliar para manejar señales de forma segura en Qt."""
    clicked = pyqtSignal(int, int)
    dragged = pyqtSignal(int, int, int, int)
    released = pyqtSignal()

class InteractivePixmapItem(QGraphicsPixmapItem):
    def __init__(self, pixmap=None):
        super().__init__()
        self._signals = ItemSignals()
        self._last_pos = None
        if pixmap:
            self.setPixmap(pixmap)
            
    @property
    def clicked(self): return self._signals.clicked
    
    @property
    def dragged(self): return self._signals.dragged
    
    @property
    def released(self): return self._signals.released
        
    def mousePressEvent(self, event):
        pos = event.pos()
        self._last_pos = pos
        self.clicked.emit(int(pos.x()), int(pos.y()))
        
    def mouseMoveEvent(self, event):
        pos = event.pos()
        if self._last_pos:
            self.dragged.emit(int(pos.x()), int(pos.y()), int(self._last_pos.x()), int(self._last_pos.y()))
        self._last_pos = pos
        
    def mouseReleaseEvent(self, event):
        self._last_pos = None
        self.released.emit()

class ThumbnailLabel(QLabel):
    """Miniatura interactiva para extraer colores con la pipeta."""
    color_picked = pyqtSignal(tuple)
    
    def __init__(self):
        super().__init__()
        self._pixmap = None
        self._image_bgr = None
        self.setCursor(Qt.CursorShape.CrossCursor)
        
    def set_image(self, pixmap, image_bgr):
        self._pixmap = pixmap
        self._image_bgr = image_bgr
        self.setPixmap(pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        
    def mousePressEvent(self, event):
        if self._image_bgr is None or not self._pixmap: return
        
        lbl_w, lbl_h = self.width(), self.height()
        pix_w, pix_h = self._pixmap.width(), self._pixmap.height()
        
        scale = min(lbl_w / pix_w, lbl_h / pix_h)
        new_w, new_h = pix_w * scale, pix_h * scale
        offset_x, offset_y = (lbl_w - new_w) / 2, (lbl_h - new_h) / 2
        
        x, y = event.pos().x() - offset_x, event.pos().y() - offset_y
        
        if 0 <= x <= new_w and 0 <= y <= new_h:
            orig_x, orig_y = int(x / scale), int(y / scale)
            if orig_y < self._image_bgr.shape[0] and orig_x < self._image_bgr.shape[1]:
                color = self._image_bgr[orig_y, orig_x]
                if self._image_bgr.shape[2] == 4:
                    if color[3] < 128: return
                    b, g, r = color[:3]
                else:
                    b, g, r = color
                self.color_picked.emit((int(b), int(g), int(r)))

class InteractiveGraphicsView(QGraphicsView):
    """Vista para editar la imagen con soporte de zoom con la rueda."""
    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QColor("#1e1f22"))
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        
    def mousePressEvent(self, event):
        if event.button() in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
            self._is_panning = True
            self._last_mouse_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if getattr(self, '_is_panning', False):
            delta = event.pos() - self._last_mouse_pos
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            self._last_mouse_pos = event.pos()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
            self._is_panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            super().mouseReleaseEvent(event)

    def drawBackground(self, painter, rect):
        """Dibuja una cuadrícula de diseño profesional de fondo."""
        super().drawBackground(painter, rect)
        grid_size = 20
        left = int(rect.left()) - (int(rect.left()) % grid_size)
        top = int(rect.top()) - (int(rect.top()) % grid_size)
        
        lines = []
        for x in range(left, int(rect.right()), grid_size):
            lines.append(QLineF(x, rect.top(), x, rect.bottom()))
        for y in range(top, int(rect.bottom()), grid_size):
            lines.append(QLineF(rect.left(), y, rect.right(), y))
            
        pen = QPen(QColor("#2b2d30"), 1)
        painter.setPen(pen)
        painter.drawLines(lines)
        
    def wheelEvent(self, event):
        zoom_in_factor = 1.15
        zoom_out_factor = 1.0 / zoom_in_factor
        if event.angleDelta().y() > 0:
            zoom_factor = zoom_in_factor
        else:
            zoom_factor = zoom_out_factor
        self.scale(zoom_factor, zoom_factor)


class ZoomableView(QGraphicsView):
    """Vista gráfica personalizada que permite hacer zoom con la rueda del ratón y paneo."""
    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QColor("black"))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)

    def drawBackground(self, painter, rect):
        """Dibuja una cuadrícula de diseño profesional de fondo para la simulación."""
        super().drawBackground(painter, rect)
        grid_size = 20
        left = int(rect.left()) - (int(rect.left()) % grid_size)
        top = int(rect.top()) - (int(rect.top()) % grid_size)
        
        lines = []
        for x in range(left, int(rect.right()), grid_size):
            lines.append(QLineF(x, rect.top(), x, rect.bottom()))
        for y in range(top, int(rect.bottom()), grid_size):
            lines.append(QLineF(rect.left(), y, rect.right(), y))
            
        pen = QPen(QColor("#151515"), 1)  # Gris muy oscuro para que no moleste a los hilos
        painter.setPen(pen)
        painter.drawLines(lines)

    def wheelEvent(self, event):
        zoom_in_factor = 1.15
        zoom_out_factor = 1.0 / zoom_in_factor
        
        if event.angleDelta().y() > 0:
            zoom_factor = zoom_in_factor
        else:
            zoom_factor = zoom_out_factor
            
        self.scale(zoom_factor, zoom_factor)