import sys
import os
import tempfile
import cv2
import numpy as np
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout,
                             QVBoxLayout, QPushButton, QLabel, QFileDialog,
                             QGraphicsScene, QListWidget, QListWidgetItem,
                             QMessageBox, QSpinBox, QFormLayout, QGroupBox, QGraphicsDropShadowEffect,
                             QCheckBox, QProgressBar, QSplitter, QTabWidget,
                             QRadioButton, QSlider, QButtonGroup, QGridLayout)
from PyQt6.QtGui import QPixmap, QPen, QColor, QImage, QIcon, QPainterPath, QCursor, QPainter
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QPoint
import pyembroidery

from viewer import InteractiveGraphicsView, InteractivePixmapItem, ZoomableView, ThumbnailLabel
from converter import generate_coloring_book, apply_flood_fill, apply_eraser, apply_brush
from stitcher import generate_tatami_from_colored_image, BROTHER_COLORS, get_closest_brother_color

class EmbroideryWorker(QThread):
    """Hilo en segundo plano para procesar la imagen sin congelar la UI"""
    progress = pyqtSignal(int)
    finished_save = pyqtSignal(str)
    finished_preview = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, colored_img, scale, add_outlines, output_path=None, preview_only=False):
        super().__init__()
        self.colored_img = colored_img
        self.scale = scale
        self.add_outlines = add_outlines
        self.output_path = output_path
        self.preview_only = preview_only

    def run(self):
        try:
            pattern = generate_tatami_from_colored_image(
                self.colored_img, self.output_path, scale=self.scale, 
                add_outlines=self.add_outlines, progress_callback=self.progress.emit
            )
            if self.preview_only:
                temp_path = os.path.join(tempfile.gettempdir(), "preview_temp.dst")
                pyembroidery.write_dst(pattern, temp_path)
                self.finished_preview.emit(temp_path)
            else:
                self.finished_save.emit(self.output_path)
        except Exception as e:
            self.error.emit(str(e))

class EmbroideryApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Simulador y Generador de Bordados Brother")
        self.resize(1200, 700)
        self.current_coloring_img = None
        self.used_colors = set()
        self.active_color = None
        self.current_image_path = None
        self.history = []
        self.initUI()

    def initUI(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # Splitter principal para redimensionar paneles dinámicamente
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # --- PANEL IZQUIERDO: Imagen y Controles ---
        left_widget = QWidget()
        left_panel = QVBoxLayout(left_widget)
        left_panel.setContentsMargins(0, 0, 10, 0)
        
        self.btn_load_img = QPushButton("1. Cargar Imagen (PNG/JPG)")
        self.btn_load_img.clicked.connect(self.load_image)
        
        self.lbl_thumbnail = ThumbnailLabel()
        self.lbl_thumbnail.setFixedHeight(120)
        self.lbl_thumbnail.setStyleSheet("border: 2px solid #5e6266; background-color: #1e1f22; margin-top: 10px; border-radius: 4px;")
        self.lbl_thumbnail.color_picked.connect(self.on_thumbnail_color_picked)
        left_panel.addWidget(self.lbl_thumbnail)
        
        # --- Grupo de Herramientas ---
        tools_group = QGroupBox("Herramientas de Dibujo")
        tools_layout = QVBoxLayout()
        
        # Botones Didácticos
        self.btn_bucket = QPushButton("🪣 Relleno")
        self.btn_bucket.setShortcut("F")
        self.btn_bucket.setToolTip("Atajo: F (Fill)")
        self.btn_brush = QPushButton("🖌️ Pincel")
        self.btn_brush.setShortcut("B")
        self.btn_brush.setToolTip("Atajo: B (Brush)")
        self.btn_eraser = QPushButton("🧹 Borrador")
        self.btn_eraser.setShortcut("E")
        self.btn_eraser.setToolTip("Atajo: E (Eraser)")
        self.btn_picker = QPushButton("💧 Pipeta")
        self.btn_picker.setShortcut("I")
        self.btn_picker.setToolTip("Atajo: I (Eyedropper)")
        
        for btn in [self.btn_bucket, self.btn_brush, self.btn_eraser, self.btn_picker]:
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_bucket.setChecked(True)
        
        self.tool_group = QButtonGroup(self)
        self.tool_group.addButton(self.btn_bucket)
        self.tool_group.addButton(self.btn_brush)
        self.tool_group.addButton(self.btn_eraser)
        self.tool_group.addButton(self.btn_picker)
        self.tool_group.buttonClicked.connect(lambda: self.update_cursor())
        
        self.lbl_eraser_size = QLabel("Grosor: 15")
        self.slider_eraser = QSlider(Qt.Orientation.Horizontal)
        self.slider_eraser.setRange(1, 100)
        self.slider_eraser.setValue(15)
        self.slider_eraser.valueChanged.connect(lambda v: self.lbl_eraser_size.setText(f"Grosor: {v}"))
        
        grid_tools = QGridLayout()
        grid_tools.addWidget(self.btn_bucket, 0, 0)
        grid_tools.addWidget(self.btn_brush, 0, 1)
        grid_tools.addWidget(self.btn_eraser, 1, 0)
        grid_tools.addWidget(self.btn_picker, 1, 1)
        tools_layout.addLayout(grid_tools)
        
        tools_layout.addWidget(self.lbl_eraser_size)
        tools_layout.addWidget(self.slider_eraser)
        
        self.btn_undo = QPushButton("Deshacer (Ctrl+Z)")
        self.btn_undo.setShortcut("Ctrl+Z")
        self.btn_undo.setEnabled(False)
        self.btn_undo.clicked.connect(self.undo_action)
        tools_layout.addWidget(self.btn_undo)
        
        self.btn_reset = QPushButton("Limpiar Lienzo")
        self.btn_reset.clicked.connect(self.reset_canvas)
        tools_layout.addWidget(self.btn_reset)
        
        tools_group.setLayout(tools_layout)
        
        # --- Grupo de Configuraciones ---
        config_group = QGroupBox("Opciones de Digitalización")
        config_layout = QFormLayout()
        
        self.spin_scale = QSpinBox()
        self.spin_scale.setRange(1, 50)
        self.spin_scale.setValue(10)
        self.spin_scale.setToolTip("10 unidades = 1mm por píxel (aprox)")
        
        self.chk_outlines = QCheckBox("Generar contornos (Pespunte)")
        self.chk_outlines.setChecked(True)
        
        config_layout.addRow("Escala del Bordado:", self.spin_scale)
        config_layout.addRow("", self.chk_outlines)
        config_group.setLayout(config_layout)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(18)
        
        self.btn_preview = QPushButton("👀 3. Vista Previa (Esquema)")
        self.btn_preview.clicked.connect(self.generate_preview)
        self.btn_preview.setEnabled(False)
        
        self.btn_generate = QPushButton("🚀 4. Generar Bordado (.DST)")
        self.btn_generate.setObjectName("primaryButton")
        self.btn_generate.clicked.connect(self.generate_embroidery)
        self.btn_generate.setEnabled(False) # Se activa al cargar imagen
        
        left_panel.addWidget(self.btn_load_img)
        left_panel.addWidget(tools_group)
        left_panel.addWidget(config_group)
        left_panel.addWidget(self.progress_bar)
        left_panel.addWidget(self.btn_preview)
        left_panel.addWidget(self.btn_generate)
        left_panel.addStretch()
        
        splitter.addWidget(left_widget)

        # --- PANEL CENTRAL: Pestañas de Trabajo ---
        center_widget = QWidget()
        center_panel = QVBoxLayout(center_widget)
        center_panel.setContentsMargins(0, 0, 10, 0)
        
        self.tabs = QTabWidget()
        
        # Pestaña 1: Libro de Colorear
        self.edit_scene = QGraphicsScene()
        self.edit_view = InteractiveGraphicsView(self.edit_scene)
        self.edit_item = InteractivePixmapItem()
        self.edit_scene.addItem(self.edit_item)
        
        self.update_cursor() # Configurar cursor inicial una vez creada la vista
        
        # Añadir sombra profesional al parche para que resalte sobre la cuadrícula
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 200))
        shadow.setOffset(4, 4)
        self.edit_item.setGraphicsEffect(shadow)
        
        self.edit_item.clicked.connect(self.on_image_clicked)
        self.edit_item.dragged.connect(self.on_image_dragged)
        self.edit_item.released.connect(self.refresh_used_colors)
        self.tabs.addTab(self.edit_view, "1. Coloreo Interactivo")
        
        # Pestaña 2: Simulación DST
        self.sim_widget = QWidget()
        sim_layout = QVBoxLayout(self.sim_widget)
        self.btn_load_dst = QPushButton("O Cargar Archivo Existente (.DST/.PES)")
        self.btn_load_dst.clicked.connect(self.load_embroidery_file)
        
        self.scene = QGraphicsScene()
        self.view = ZoomableView(self.scene)
        
        sim_layout.addWidget(self.btn_load_dst)
        sim_layout.addWidget(self.view, 1)
        self.tabs.addTab(self.sim_widget, "2. Simulación (.DST)")
        
        center_panel.addWidget(self.tabs)
        
        splitter.addWidget(center_widget)

        # --- PANEL DERECHO: Lista de Colores ---
        right_widget = QWidget()
        right_panel = QVBoxLayout(right_widget)
        right_panel.setContentsMargins(0, 0, 0, 0)
        
        # --- 1. Paleta Brother ---
        lbl_palette = QLabel("🎨 Paleta Brother")
        lbl_palette.setObjectName("headerLabel")
        right_panel.addWidget(lbl_palette)
        
        self.palette_list = QListWidget()
        self.palette_list.setFixedWidth(240)
        self.palette_list.setIconSize(QSize(24, 24))
        for name, r, g, b in BROTHER_COLORS:
            item = QListWidgetItem(f"{name} ({r},{g},{b})")
            
            # Crear un pequeño cuadrado de color (icono)
            pixmap = QPixmap(24, 24)
            pixmap.fill(QColor(r, g, b))
            item.setIcon(QIcon(pixmap))
            
            item.setData(Qt.ItemDataRole.UserRole, (b, g, r))
            self.palette_list.addItem(item)
            
        self.palette_list.itemSelectionChanged.connect(self.on_palette_selection)
        right_panel.addWidget(self.palette_list, 1)
        
        # --- 2. Hilos Usados ---
        self.lbl_hilos = QLabel("Hilos Usados: 0 / 6")
        self.lbl_hilos.setObjectName("headerLabel")
        right_panel.addWidget(self.lbl_hilos)
        
        self.used_colors_list = QListWidget()
        self.used_colors_list.setFixedWidth(240)
        self.used_colors_list.setIconSize(QSize(24, 24))
        right_panel.addWidget(self.used_colors_list)
        
        splitter.addWidget(right_widget)

        # Proporciones iniciales del Splitter (Izquierda, Centro, Derecha)
        splitter.setSizes([350, 650, 200])
        
        self.apply_modern_theme()

    def apply_modern_theme(self):
        """Aplica una hoja de estilos (QSS) profesional estilo Tema Oscuro / VS Code."""
        dark_theme = """
        QMainWindow, QWidget {
            background-color: #2b2d30;
            color: #cccccc;
            font-family: 'Segoe UI', Helvetica, Arial, sans-serif;
            font-size: 10pt;
        }
        QGraphicsView {
            background-color: #1e1f22;
            border: 1px solid #393b40;
            border-radius: 4px;
        }
        QPushButton {
            background-color: #4c5052;
            border: 1px solid #5e6266;
            border-radius: 4px;
            padding: 8px 16px;
            color: #ffffff;
            font-weight: 500;
        }
        QPushButton:hover {
            background-color: #5a5e62;
            border: 1px solid #6c7074;
        }
        QPushButton:pressed {
            background-color: #3b3e40;
        }
        QPushButton:disabled {
            background-color: #36393b;
            color: #777777;
            border: 1px solid #36393b;
        }
        QPushButton:checked {
            background-color: #2f65ca;
            border: 1px solid #6c7074;
            color: white;
        }
        QPushButton#primaryButton {
            background-color: #3574f0;
            border: 1px solid #2b61cf;
            font-size: 11pt;
            font-weight: bold;
            border-radius: 6px;
            padding: 10px;
        }
        QPushButton#primaryButton:hover {
            background-color: #4682f6;
            border: 1px solid #3574f0;
        }
        QPushButton#primaryButton:pressed {
            background-color: #2b61cf;
        }
        QGroupBox {
            border: 1px solid #393b40;
            border-radius: 4px;
            margin-top: 12px;
            padding-top: 15px;
            padding-bottom: 5px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 5px;
            color: #8fa1b3;
            font-weight: bold;
        }
        QListWidget {
            background-color: #1e1f22;
            border: 1px solid #393b40;
            border-radius: 4px;
            outline: none;
        }
        QListWidget::item {
            padding: 6px;
            border-bottom: 1px solid #2b2d30;
            border-radius: 2px;
            margin: 2px;
        }
        QListWidget::item:selected {
            background-color: #2f65ca;
            color: white;
            border: 1px solid #3574f0;
        }
        QProgressBar {
            border: 1px solid #393b40;
            border-radius: 4px;
            text-align: center;
            background-color: #1e1f22;
            color: #ffffff;
            font-weight: bold;
        }
        QProgressBar::chunk {
            background-color: #3574f0;
            border-radius: 3px;
        }
        QSpinBox {
            background-color: #1e1f22;
            border: 1px solid #393b40;
            color: #cccccc;
            padding: 4px;
            border-radius: 4px;
        }
        QSpinBox::up-button, QSpinBox::down-button {
            background-color: #4c5052;
            border-radius: 2px;
            width: 16px;
        }
        QSpinBox::up-button:hover, QSpinBox::down-button:hover {
            background-color: #5a5e62;
        }
        QCheckBox {
            spacing: 8px;
            color: #cccccc;
        }
        QLabel#headerLabel {
            font-size: 11pt;
            font-weight: bold;
            color: #8fa1b3;
            padding-bottom: 5px;
            border: none;
        }
        QLabel#imageLabel {
            border: none;
            border-radius: 4px;
            background-color: #1e1f22;
            color: #777777;
        }
        QSplitter::handle {
            background-color: #2b2d30;
            width: 4px;
            border-radius: 2px;
        }
        QSplitter::handle:hover {
            background-color: #393b40;
        }
        QTabWidget::pane { border: 1px solid #393b40; border-radius: 4px; }
        QTabBar::tab { background: #1e1f22; color: #8fa1b3; padding: 8px 16px; border: 1px solid #393b40; border-bottom: none; border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 2px;}
        QTabBar::tab:selected { background: #2b2d30; color: #ffffff; border-color: #3574f0; border-bottom: 1px solid #2b2d30;}
        """
        self.setStyleSheet(dark_theme)

    def get_emoji_cursor(self, emoji):
        """Genera un cursor visual usando un emoji para el ratón."""
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        font = painter.font()
        font.setPointSize(16)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, emoji)
        painter.end()
        return QCursor(pixmap, 4, 28)

    def update_cursor(self):
        """Cambia el icono del ratón según la herramienta activa."""
        if self.btn_bucket.isChecked(): cursor = self.get_emoji_cursor("🪣")
        elif self.btn_brush.isChecked(): cursor = self.get_emoji_cursor("🖌️")
        elif self.btn_eraser.isChecked(): cursor = self.get_emoji_cursor("🧹")
        elif self.btn_picker.isChecked(): cursor = self.get_emoji_cursor("💧")
        else: cursor = Qt.CursorShape.ArrowCursor
        
        self.edit_view.viewport().setCursor(cursor)

    def on_palette_selection(self):
        """Actualiza el color activo cuando el usuario hace clic en la lista de paleta."""
        selected = self.palette_list.currentItem()
        if selected:
            self.active_color = selected.data(Qt.ItemDataRole.UserRole)

    def on_thumbnail_color_picked(self, color):
        """Atrapa el color si el usuario usa la pipeta sobre la miniatura original."""
        if self.btn_picker.isChecked():
            self.active_color = color
            self.palette_list.clearSelection()

    def load_image(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Abrir Imagen", "", "Imágenes (*.png *.jpg *.jpeg *.bmp)"
        )
        if file_name:
            try:
                self.current_image_path = file_name
                
                # Cargar imagen real y mostrar miniatura
                img_orig = cv2.imread(file_name, cv2.IMREAD_UNCHANGED)
                pixmap_thumb = QPixmap(file_name)
                self.lbl_thumbnail.set_image(pixmap_thumb, img_orig)
                
                self.current_coloring_img = generate_coloring_book(file_name)
                self.used_colors.clear()
                self.history.clear()
                self.btn_undo.setEnabled(False)
                self.update_image_display()
                self.edit_view.fitInView(self.edit_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
                self.update_color_counter()
                self.tabs.setCurrentIndex(0)  # Cambiar a la pestaña de dibujo
                self.btn_preview.setEnabled(True)
                self.btn_generate.setEnabled(True)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Fallo al cargar imagen:\n{e}")
                self.btn_generate.setEnabled(False)

    def update_image_display(self):
        """Convierte la matriz OpenCV a un QPixmap visible para la GUI."""
        if self.current_coloring_img is None: return
        rgb_image = cv2.cvtColor(self.current_coloring_img, cv2.COLOR_BGRA2RGBA)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        qimg = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGBA8888)
        self.edit_item.setPixmap(QPixmap.fromImage(qimg))
        self.edit_scene.setSceneRect(0, 0, w, h)
        
    def update_color_counter(self):
        """Actualiza el texto y la lista derecha de los hilos que llevas aplicados."""
        self.lbl_hilos.setText(f"Hilos Usados: {len(self.used_colors)} / 6")
        self.used_colors_list.clear()
        for color in self.used_colors:
            b, g, r = color
            item = QListWidgetItem(f"RGB ({r},{g},{b})")
            pixmap = QPixmap(24, 24)
            pixmap.fill(QColor(r, g, b))
            item.setIcon(QIcon(pixmap))
            self.used_colors_list.addItem(item)

    def apply_erase(self, x, y, prev_x=None, prev_y=None):
        """Ejecuta el borrado localmente sin recalcular la lista de colores enteros."""
        radius = self.slider_eraser.value()
        self.current_coloring_img = apply_eraser(self.current_coloring_img, x, y, radius, prev_x, prev_y)
        self.update_image_display()
        
    def apply_paint(self, x, y, prev_x=None, prev_y=None):
        """Aplica un círculo de color usando el Pincel Libre."""
        if not self.active_color: return
        radius = self.slider_eraser.value()
        self.current_coloring_img = apply_brush(self.current_coloring_img, x, y, self.active_color, radius, prev_x, prev_y)
        self.update_image_display()

    def save_to_history(self):
        """Guarda el estado actual de la imagen para poder deshacer cambios."""
        if self.current_coloring_img is not None:
            self.history.append(self.current_coloring_img.copy())
            if len(self.history) > 20: # Limitar a 20 pasos para no llenar la RAM
                self.history.pop(0)
            self.btn_undo.setEnabled(True)
            
    def undo_action(self):
        """Restaura el estado anterior de la imagen."""
        if self.history:
            self.current_coloring_img = self.history.pop()
            if not self.history:
                self.btn_undo.setEnabled(False)
            self.refresh_used_colors()
            self.update_image_display()

    def reset_canvas(self):
        """Reinicia el lienzo a su estado original."""
        if self.current_image_path:
            self.save_to_history()
            self.current_coloring_img = generate_coloring_book(self.current_image_path)
            self.used_colors.clear()
            self.update_color_counter()
            self.update_image_display()

    def on_image_clicked(self, x, y):
        """Evento que dispara el Flood Fill o el Borrador cuando el usuario hace clic en el dibujo."""
        if self.current_coloring_img is None: return
        
        if self.btn_eraser.isChecked():
            self.save_to_history()
            self.apply_erase(x, y)
            return
            
        if self.btn_picker.isChecked():
            b, g, r, a = self.current_coloring_img[y, x]
            # Evitar seleccionar las áreas transparentes
            if a < 128: return
            self.active_color = (int(b), int(g), int(r))
            self.palette_list.clearSelection()
            return
            
        if self.btn_brush.isChecked():
            if not self.active_color:
                QMessageBox.information(self, "Selecciona un Hilo", "Por favor, selecciona un color de la Paleta Brother a la derecha antes de pintar.")
                return
            bgr_color = self.active_color
            if bgr_color not in self.used_colors and len(self.used_colors) >= 6:
                QMessageBox.warning(self, "Límite Técnico Excedido", "Máximo 6 colores permitidos para este modelo de máquina (Brother BP1430L).")
                return
            self.save_to_history()
            self.apply_paint(x, y)
            return
            
        if not self.active_color:
            QMessageBox.information(self, "Selecciona un Hilo", "Por favor, selecciona un color de la Paleta Brother a la derecha antes de pintar.")
            return
            
        b, g, r, a = self.current_coloring_img[y, x]
        # Ignorar áreas transparentes
        if a < 128: return
        # Ignorar clics directos sobre las líneas negras
        if b < 50 and g < 50 and r < 50: return
        
        bgr_color = self.active_color
        
        if bgr_color not in self.used_colors and len(self.used_colors) >= 6:
            QMessageBox.warning(self, "Límite Técnico Excedido", "Máximo 6 colores permitidos para este modelo de máquina (Brother BP1430L).")
            return
            
        self.save_to_history()
        self.current_coloring_img = apply_flood_fill(self.current_coloring_img, x, y, bgr_color)
        self.used_colors.add(bgr_color)
        self.update_image_display()
        self.update_color_counter()

    def on_image_dragged(self, x, y, prev_x, prev_y):
        """Evento para arrastrar continuamente el borrador o pincel."""
        if self.current_coloring_img is None: return
        if self.btn_eraser.isChecked():
            self.apply_erase(x, y, prev_x, prev_y)
        elif self.btn_brush.isChecked():
            self.apply_paint(x, y, prev_x, prev_y)
            
    def refresh_used_colors(self):
        """Revisa la imagen entera al soltar el clic para ver qué colores quedan realmente tras borrar."""
        if self.current_coloring_img is None: return
        pixels = self.current_coloring_img.reshape(-1, 4)
        unique_colors = np.unique(pixels, axis=0)
        self.used_colors.clear()
        for color in unique_colors:
            b, g, r, a = color
            t_color = (int(b), int(g), int(r))
            # Ignoramos el blanco puro, el negro (líneas) y lo transparente
            if a > 128 and t_color != (255, 255, 255) and t_color != (0, 0, 0):
                self.used_colors.add(t_color)
        self.update_color_counter()

    def generate_preview(self):
        if self.current_coloring_img is None: return
        
        if not self.used_colors:
            QMessageBox.warning(self, "Lienzo Vacío", "Por favor, pinta al menos un área con la paleta de colores antes de previsualizar.")
            return
        
        scale = self.spin_scale.value()
        add_outlines = self.chk_outlines.isChecked()
        
        self.btn_preview.setEnabled(False)
        self.btn_generate.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        self.worker = EmbroideryWorker(self.current_coloring_img, scale, add_outlines, preview_only=True)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.finished_preview.connect(self.on_preview_finished)
        self.worker.error.connect(self.on_generation_error)
        self.worker.start()
        
    def on_preview_finished(self, temp_path):
        self.btn_preview.setEnabled(True)
        self.btn_generate.setEnabled(True)
        self.tabs.setCurrentIndex(1)
        self.draw_embroidery(temp_path)

    def generate_embroidery(self):
        if self.current_coloring_img is None:
            return
            
        if not self.used_colors:
            QMessageBox.warning(self, "Lienzo Vacío", "Por favor, pinta al menos un área con la paleta de colores antes de generar el bordado.")
            return
            
        output_path, _ = QFileDialog.getSaveFileName(
            self, "Guardar Bordado", "resultado.dst", "Archivos Tajima DST (*.dst)"
        )
        
        if not output_path:
            return
            
        scale = self.spin_scale.value()
        add_outlines = self.chk_outlines.isChecked()
        
        # Preparar UI para la carga
        self.btn_generate.setEnabled(False)
        self.btn_preview.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        # Iniciar el Worker
        self.worker = EmbroideryWorker(self.current_coloring_img, scale, add_outlines, output_path)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.finished_save.connect(self.on_generation_finished)
        self.worker.error.connect(self.on_generation_error)
        self.worker.start()

    def on_generation_finished(self, output_path):
        self.btn_generate.setEnabled(True)
        self.btn_preview.setEnabled(True)
        self.tabs.setCurrentIndex(1) # Saltar mágicamente a la simulación
        QMessageBox.information(self, "Éxito", f"Bordado generado exitosamente en:\n{output_path}")
        
        # Extraer patrón para dibujarlo
        pattern = pyembroidery.read(output_path)
        self.draw_embroidery_pattern(pattern)
        
    def on_generation_error(self, err):
        self.btn_generate.setEnabled(True)
        self.btn_preview.setEnabled(True)
        QMessageBox.critical(self, "Error", f"Ocurrió un error al generar el bordado:\n{err}")

    def load_embroidery_file(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Abrir Bordado", "", "Archivos de Bordado (*.dst *.pes)"
        )
        if file_name:
            self.draw_embroidery(file_name)

    def draw_embroidery(self, filename):
        try:
            pattern = pyembroidery.read(filename)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo leer el archivo:\n{e}")
            return
        self.draw_embroidery_pattern(pattern)
        
    def draw_embroidery_pattern(self, pattern):
        self.scene.clear()
        self.used_colors_list.clear()

        if not pattern or not pattern.stitches: return

        num_colors_expected = pattern.count_color_changes() + 1
        colors = []
        
        # Intentar extraer hilos (si es nuestro patrón o formato PES)
        for i, thread in enumerate(pattern.threadlist):
            color_val = thread.color if getattr(thread, 'color', None) is not None else 0
            c = QColor((color_val >> 16) & 255, (color_val >> 8) & 255, color_val & 255)
            colors.append(c)
            
            thread_name = getattr(thread, 'description', None) or f"Hilo {i + 1}"
            item = QListWidgetItem(thread_name)
            pixmap = QPixmap(24, 24)
            pixmap.fill(c)
            item.setIcon(QIcon(pixmap))
            self.used_colors_list.addItem(item)
                
        # Si es un archivo .DST raw sin hilos incrustados, generar colores dinámicos
        while len(colors) < num_colors_expected:
            idx = len(colors)
            hue = int((idx * (360 / num_colors_expected)) % 360)
            fallback_color = QColor.fromHsv(hue, 220, 255)
            colors.append(fallback_color)
            
            item = QListWidgetItem(f"Color Genérico {idx + 1}")
            pixmap = QPixmap(24, 24)
            pixmap.fill(fallback_color)
            item.setIcon(QIcon(pixmap))
            self.used_colors_list.addItem(item)

        color_index = 0
        pen = QPen(colors[color_index] if colors else QColor("white"))
        pen.setWidthF(3.0) 
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        current_path = QPainterPath()
        paths_to_draw = []
        is_first_stitch = True

        for x, y, command in pattern.stitches:
            render_x, render_y = float(x), float(-y)
            if command == pyembroidery.STITCH:
                if is_first_stitch:
                    current_path.moveTo(render_x, render_y)
                    is_first_stitch = False
                else:
                    current_path.lineTo(render_x, render_y)
            elif command == pyembroidery.JUMP or command == pyembroidery.TRIM:
                current_path.moveTo(render_x, render_y)
            elif command == pyembroidery.COLOR_CHANGE:
                paths_to_draw.append((current_path, QPen(pen))) # Aislar la memoria gráfica
                color_index = min(color_index + 1, len(colors) - 1)
                pen = QPen(colors[color_index]) # Reiniciar memoria del lápiz
                pen.setWidthF(3.0)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                current_path = QPainterPath()
                current_path.moveTo(render_x, render_y)
                is_first_stitch = True
                
        paths_to_draw.append((current_path, QPen(pen)))
        
        for path, p_pen in paths_to_draw:
            self.scene.addPath(path, p_pen)
        
        self.view.fitInView(self.scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    viewer = EmbroideryApp()
    viewer.show()
    sys.exit(app.exec())