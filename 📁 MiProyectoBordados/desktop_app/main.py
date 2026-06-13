import sys
import os
import tempfile
import math
import cv2
import numpy as np
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout,
                             QVBoxLayout, QPushButton, QLabel, QFileDialog,
                             QGraphicsScene, QListWidget, QListWidgetItem,
                             QMessageBox, QSpinBox, QFormLayout, QGroupBox, QGraphicsDropShadowEffect,
                             QCheckBox, QProgressBar, QSplitter, QTabWidget,
                             QRadioButton, QSlider, QButtonGroup, QGridLayout, QComboBox,
                             QScrollArea, QInputDialog, QFontDialog, QDialog, QTextEdit, QFontComboBox, 
                             QColorDialog, QDialogButtonBox, QSizePolicy)
from PyQt6.QtGui import QPixmap, QPen, QColor, QImage, QIcon, QPainterPath, QCursor, QPainter, QPdfWriter, QPageSize, QTextDocument, QFont, QFontMetrics
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QPoint, QRectF, QUrl, QByteArray, QBuffer, QIODevice
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
import pyembroidery

# Importar módulos core para que la app de escritorio funcione correctamente
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'core')))

from viewer import InteractiveGraphicsView, InteractivePixmapItem, ZoomableView, ThumbnailLabel
from converter import generate_coloring_book, apply_flood_fill, apply_eraser, apply_brush, apply_auto_color_kmeans, _load_and_preprocess_image, create_text_image
from stitcher import generate_tatami_from_colored_image, BROTHER_COLORS, MADEIRA_COLORS, ISACORD_COLORS, SULKY_COLORS, get_closest_thread_color

class EmbroideryWorker(QThread):
    """Hilo en segundo plano para procesar la imagen sin congelar la UI"""
    progress = pyqtSignal(int)
    finished_save = pyqtSignal(str)
    finished_preview = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, colored_img, scale, add_outlines, output_path=None, preview_only=False, palette=None):
        super().__init__()
        self.colored_img = colored_img
        self.scale = scale
        self.add_outlines = add_outlines
        self.output_path = output_path
        self.preview_only = preview_only
        self.palette = palette if palette else BROTHER_COLORS

    def run(self):
        try:
            pattern = generate_tatami_from_colored_image(
                self.colored_img, self.output_path, scale=self.scale, 
                add_outlines=self.add_outlines, progress_callback=self.progress.emit,
                palette=self.palette
            )
            if self.preview_only:
                # Usar formato PES para la previsualización asegura que PyQt6 lea los colores RGB correctos.
                temp_path = os.path.join(tempfile.gettempdir(), "preview_temp.pes")
                pyembroidery.write(pattern, temp_path)
                self.finished_preview.emit(temp_path)
            else:
                self.finished_save.emit(self.output_path)
        except Exception as e:
            self.error.emit(str(e))

class AdvancedTextDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Módulo Pro de Monogramas y Tipografías")
        self.resize(800, 500)
        self.selected_color = QColor(0, 0, 0)
        self.generated_image = None
        self.initUI()
        
    def initUI(self):
        layout = QHBoxLayout(self)
        
        # Panel de Controles
        control_layout = QVBoxLayout()
        control_layout.setSpacing(15)
        
        # Grupo Texto
        group_text = QGroupBox("Texto a Bordar")
        text_l = QVBoxLayout()
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("Ingresa el texto aquí...")
        self.text_edit.setFixedHeight(80)
        self.text_edit.textChanged.connect(self.update_preview)
        text_l.addWidget(self.text_edit)
        group_text.setLayout(text_l)
        control_layout.addWidget(group_text)
        
        # Grupo Tipografía
        group_font = QGroupBox("Ajustes de Tipografía")
        font_l = QFormLayout()
        
        self.font_combo = QFontComboBox()
        self.font_combo.currentFontChanged.connect(self.update_preview)
        font_l.addRow("Fuente:", self.font_combo)
        
        self.spin_size = QSpinBox()
        self.spin_size.setRange(20, 1000)
        self.spin_size.setValue(150)
        self.spin_size.valueChanged.connect(self.update_preview)
        font_l.addRow("Tamaño:", self.spin_size)
        
        self.spin_rotation = QSpinBox()
        self.spin_rotation.setRange(-360, 360)
        self.spin_rotation.setValue(0)
        self.spin_rotation.valueChanged.connect(self.update_preview)
        font_l.addRow("Rotación:", self.spin_rotation)
        
        style_layout = QHBoxLayout()
        self.chk_bold = QCheckBox("Negrita")
        self.chk_bold.stateChanged.connect(self.update_preview)
        self.chk_italic = QCheckBox("Cursiva")
        self.chk_italic.stateChanged.connect(self.update_preview)
        style_layout.addWidget(self.chk_bold)
        style_layout.addWidget(self.chk_italic)
        font_l.addRow("Estilos:", style_layout)
        
        self.btn_color = QPushButton("Color: Negro")
        self.btn_color.setStyleSheet("background-color: black; color: white;")
        self.btn_color.clicked.connect(self.choose_color)
        font_l.addRow("Color:", self.btn_color)
        
        group_font.setLayout(font_l)
        control_layout.addWidget(group_font)
        
        control_layout.addStretch()
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        control_layout.addWidget(buttons)
        
        # Panel de Vista Previa
        preview_group = QGroupBox("Vista Previa del Lienzo")
        preview_l = QVBoxLayout()
        self.preview_lbl = QLabel()
        self.preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_lbl.setStyleSheet("background-color: #ffffff; border: 1px dashed #3574f0; border-radius: 4px;")
        self.preview_lbl.setMinimumSize(400, 400)
        preview_l.addWidget(self.preview_lbl)
        preview_group.setLayout(preview_l)
        
        layout.addLayout(control_layout, 1)
        layout.addWidget(preview_group, 2)
        self.update_preview()
        
    def choose_color(self):
        color = QColorDialog.getColor(self.selected_color, self, "Elige el color del texto")
        if color.isValid():
            self.selected_color = color
            text_col = 'white' if color.lightness() < 128 else 'black'
            self.btn_color.setStyleSheet(f"background-color: {color.name()}; color: {text_col};")
            self.btn_color.setText(f"Color: {color.name().upper()}")
            self.update_preview()
            
    def get_font(self):
        font = self.font_combo.currentFont()
        font.setPixelSize(self.spin_size.value())
        font.setBold(self.chk_bold.isChecked())
        font.setItalic(self.chk_italic.isChecked())
        return font
        
    def update_preview(self):
        text = self.text_edit.toPlainText()
        if not text.strip():
            self.preview_lbl.setText("Escribe algo para previsualizar...")
            self.generated_image = None
            return
            
        font = self.get_font()
        metrics = QFontMetrics(font)
        
        rect = metrics.boundingRect(0, 0, 4000, 4000, Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignCenter, text)
        pad = 80
        w, h = rect.width() + pad * 2, rect.height() + pad * 2
        
        # Ampliamos el canvas para que al rotar no se corte fácilmente
        diagonal = int(math.hypot(w, h))
        img = QImage(diagonal, diagonal, QImage.Format.Format_ARGB32)
        img.fill(QColor(255, 255, 255, 0))
        
        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Transformación para rotación desde el centro
        painter.translate(diagonal/2, diagonal/2)
        painter.rotate(self.spin_rotation.value())
        painter.translate(-w/2, -h/2)
        
        painter.setFont(font)
        painter.setPen(self.selected_color)
        
        text_rect = QRectF(0, 0, w, h)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, text)
        painter.end()
        
        self.generated_image = img
        pixmap = QPixmap.fromImage(img)
        self.preview_lbl.setPixmap(pixmap.scaled(self.preview_lbl.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

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
        self.redo_history = []
        self.initUI()
        self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)

    def initUI(self):
        # --- BARRA DE ESTADO ---
        self.statusBar = self.statusBar()
        self.statusBar.showMessage("Bienvenido. Carga una imagen para comenzar a digitalizar.")
        self.statusBar.setStyleSheet("background-color: #1e1f22; color: #8fa1b3; border-top: 1px solid #393b40; padding: 4px; font-weight: bold;")

        main_widget = QWidget()
        main_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)

        # Splitter principal para redimensionar paneles dinámicamente
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        main_layout.addWidget(splitter, 1)

        # --- PANEL IZQUIERDO: Imagen y Controles ---
        left_widget = QWidget()
        left_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        left_widget.setMinimumWidth(340)
        left_widget.setMaximumWidth(420)
        left_panel = QVBoxLayout(left_widget)
        left_panel.setContentsMargins(0, 0, 10, 0)
        left_panel.setSpacing(14)
        
        # Título del menú
        app_title = QLabel("Brother Auto-Digitizer")
        app_title.setStyleSheet("font-size: 14pt; font-weight: bold; color: #ffffff; padding: 5px; background: transparent; border: none;")
        app_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_panel.addWidget(app_title)
        
        self.btn_load_img = QPushButton("Cargar Imagen")
        self.btn_load_img.clicked.connect(self.load_image)
        self.btn_load_img.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_load_img.setMinimumHeight(42)

        self.btn_export_img = QPushButton("Guardar Lienzo")
        self.btn_export_img.setToolTip("Guarda la imagen coloreada actual como PNG")
        self.btn_export_img.clicked.connect(self.save_colored_image)
        self.btn_export_img.setEnabled(False)
        self.btn_export_img.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_export_img.setMinimumHeight(42)
        
        img_buttons_layout = QHBoxLayout()
        img_buttons_layout.setSpacing(12)
        img_buttons_layout.addWidget(self.btn_load_img)
        img_buttons_layout.addWidget(self.btn_export_img)

        self.lbl_thumbnail = ThumbnailLabel()
        self.lbl_thumbnail.setFixedHeight(120)
        self.lbl_thumbnail.setStyleSheet("border: 2px solid #5e6266; background-color: #1e1f22; margin-top: 10px; border-radius: 4px;")
        self.lbl_thumbnail.color_picked.connect(self.on_thumbnail_color_picked)
        left_panel.addWidget(self.lbl_thumbnail)
        
        # --- Grupo de Herramientas ---
        tools_group = QGroupBox("Herramientas de Dibujo")
        tools_layout = QVBoxLayout()
        
        # Botones Didácticos
        self.btn_bucket = QPushButton("Relleno")
        self.btn_bucket.setShortcut("F")
        self.btn_bucket.setToolTip("Atajo: F (Fill)")
        self.btn_brush = QPushButton("Pincel")
        self.btn_brush.setShortcut("B")
        self.btn_brush.setToolTip("Atajo: B (Brush)")
        self.btn_eraser = QPushButton("Borrador")
        self.btn_eraser.setShortcut("E")
        self.btn_eraser.setToolTip("Atajo: E (Eraser)")
        self.btn_picker = QPushButton("Pipeta")
        self.btn_picker.setShortcut("I")
        self.btn_picker.setToolTip("Atajo: I (Eyedropper)")
        
        self.btn_line = QPushButton("Línea")
        self.btn_rect = QPushButton("Rectángulo")
        self.btn_circle = QPushButton("Círculo")
        
        for btn in [self.btn_bucket, self.btn_brush, self.btn_eraser, self.btn_picker, self.btn_line, self.btn_rect, self.btn_circle]:
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(42)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_bucket.setChecked(True)
        
        self.tool_group = QButtonGroup(self)
        self.tool_group.addButton(self.btn_bucket)
        self.tool_group.addButton(self.btn_brush)
        self.tool_group.addButton(self.btn_eraser)
        self.tool_group.addButton(self.btn_picker)
        self.tool_group.addButton(self.btn_line)
        self.tool_group.addButton(self.btn_rect)
        self.tool_group.addButton(self.btn_circle)
        self.tool_group.buttonClicked.connect(lambda: self.update_cursor())
        
        self.btn_zoom_in = QPushButton("+ Zoom")
        self.btn_zoom_out = QPushButton("- Zoom")
        self.btn_zoom_fit = QPushButton("Ajustar a Pantalla")
        for btn in [self.btn_zoom_in, self.btn_zoom_out, self.btn_zoom_fit]:
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setMinimumHeight(34)
        
        self.btn_zoom_in.clicked.connect(lambda: self.view.scale(1.15, 1.15))
        self.btn_zoom_out.clicked.connect(lambda: self.view.scale(1.0/1.15, 1.0/1.15))
        self.btn_zoom_fit.clicked.connect(lambda: self.view.fitInView(self.scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio) if self.scene.items() else None)
        
        zoom_layout = QHBoxLayout()
        zoom_layout.addWidget(self.btn_zoom_in)
        zoom_layout.addWidget(self.btn_zoom_out)
        zoom_layout.addWidget(self.btn_zoom_fit)
        zoom_layout.addStretch()

        self.lbl_eraser_size = QLabel("Grosor: 15")
        self.slider_eraser = QSlider(Qt.Orientation.Horizontal)
        self.slider_eraser.setRange(1, 100)
        self.slider_eraser.setValue(15)
        self.slider_eraser.valueChanged.connect(lambda v: self.lbl_eraser_size.setText(f"Grosor: {v}"))
        
        grid_tools = QGridLayout()
        grid_tools.setSpacing(10)
        grid_tools.setColumnStretch(0, 1)
        grid_tools.setColumnStretch(1, 1)
        grid_tools.addWidget(self.btn_bucket, 0, 0)
        grid_tools.addWidget(self.btn_brush, 0, 1)
        grid_tools.addWidget(self.btn_eraser, 1, 0)
        grid_tools.addWidget(self.btn_picker, 1, 1)
        grid_tools.addWidget(self.btn_line, 2, 0)
        grid_tools.addWidget(self.btn_rect, 2, 1)
        grid_tools.addWidget(self.btn_circle, 3, 0)
        tools_layout.addLayout(grid_tools)
        
        tools_layout.addWidget(self.lbl_eraser_size)
        tools_layout.addWidget(self.slider_eraser)
        
        self.btn_undo = QPushButton("Deshacer (Ctrl+Z)")
        self.btn_undo.setShortcut("Ctrl+Z")
        self.btn_undo.setEnabled(False)
        self.btn_undo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_undo.setMinimumHeight(38)
        self.btn_undo.clicked.connect(self.undo_action)
        
        self.btn_redo = QPushButton("Rehacer (Ctrl+Y)")
        self.btn_redo.setShortcut("Ctrl+Y")
        self.btn_redo.setEnabled(False)
        self.btn_redo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_redo.setMinimumHeight(38)
        self.btn_redo.clicked.connect(self.redo_action)
        
        undo_redo_layout = QHBoxLayout()
        undo_redo_layout.addWidget(self.btn_undo)
        undo_redo_layout.addWidget(self.btn_redo)
        tools_layout.addLayout(undo_redo_layout)
        
        self.btn_auto_color = QPushButton("Auto-Digitalizar")
        self.btn_auto_color.setToolTip("IA: Reduce y colorea automáticamente a 6 colores Brother")
        self.btn_auto_color.clicked.connect(self.auto_color_action)
        self.btn_auto_color.setEnabled(False)
        self.btn_auto_color.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_auto_color.setMinimumHeight(42)
        tools_layout.addWidget(self.btn_auto_color)
        
        self.btn_add_text = QPushButton("Módulo Pro de Monogramas")
        self.btn_add_text.setToolTip("Crea textos avanzados con tipografías y efectos listos para bordar")
        self.btn_add_text.clicked.connect(self.add_text_action)
        self.btn_add_text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_add_text.setMinimumHeight(42)
        tools_layout.addWidget(self.btn_add_text)

        self.btn_reset = QPushButton("Limpiar Lienzo")
        self.btn_reset.clicked.connect(self.reset_canvas)
        self.btn_reset.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_reset.setMinimumHeight(42)
        tools_layout.addWidget(self.btn_reset)
        
        tools_group.setLayout(tools_layout)
        
        # --- Grupo de Configuraciones ---
        config_group = QGroupBox("Opciones de Digitalización")
        config_layout = QVBoxLayout()
        
        lbl_bastidor = QLabel("Selecciona tu bastidor:")
        lbl_bastidor.setStyleSheet("font-weight: bold; color: #8fa1b3;")
        
        self.combo_hoop = QComboBox()
        self.combo_hoop.addItems([
            "Libre (Sin Límite)", 
            "Bastidor Pequeño (10x10 cm)", 
            "Bastidor Mediano (13x18 cm)", 
            "Bastidor Grande (16x26 cm)"
        ])
        self.combo_hoop.currentIndexChanged.connect(self.update_hoop_visualizer)
        self.combo_hoop.currentIndexChanged.connect(lambda idx: self.validate_hoop_size())
        
        self.lbl_size_info = QLabel("Tamaño: 0.0 x 0.0 mm")
        self.lbl_size_info.setStyleSheet("color: #8fa1b3; font-weight: bold; margin-top: 5px; margin-bottom: 5px;")
        
        form_scale = QFormLayout()
        self.spin_scale = QSpinBox()
        self.spin_scale.setRange(1, 50)
        self.spin_scale.setValue(10)
        self.spin_scale.setToolTip("10 unidades = 1mm por píxel (aprox)")
        self.spin_scale.valueChanged.connect(self.update_hoop_visualizer)
        self.spin_scale.valueChanged.connect(lambda v: self.update_size_info())
        form_scale.addRow("Escala del Bordado:", self.spin_scale)
        
        self.chk_outlines = QCheckBox("Generar contornos (Pespunte)")
        self.chk_outlines.setChecked(True)
        
        config_layout.addWidget(lbl_bastidor)
        config_layout.addWidget(self.combo_hoop)
        config_layout.addWidget(self.lbl_size_info)
        config_layout.addLayout(form_scale)
        config_layout.addWidget(self.chk_outlines)
        config_group.setLayout(config_layout)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(18)
        
        self.btn_preview = QPushButton("Vista Previa")
        self.btn_preview.clicked.connect(self.generate_preview)
        self.btn_preview.setEnabled(False)
        self.btn_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_preview.setMinimumHeight(42)
        
        self.btn_generate = QPushButton("Generar Bordado")
        self.btn_generate.setObjectName("primaryButton")
        self.btn_generate.clicked.connect(self.generate_embroidery)
        self.btn_generate.setEnabled(False) # Se activa al cargar imagen
        self.btn_generate.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_generate.setMinimumHeight(48)
        
        left_panel.addLayout(img_buttons_layout)
        left_panel.addWidget(tools_group)
        left_panel.addWidget(config_group)
        left_panel.addWidget(self.progress_bar)
        left_panel.addWidget(self.btn_preview)
        left_panel.addWidget(self.btn_generate)
        left_panel.addStretch()
        
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setWidget(left_widget)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        left_scroll.setMinimumWidth(360)
        splitter.addWidget(left_scroll)

        # --- PANEL CENTRAL: Pestañas de Trabajo ---
        center_widget = QWidget()
        center_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        center_panel = QVBoxLayout(center_widget)
        center_panel.setContentsMargins(0, 0, 10, 0)
        
        self.tabs = QTabWidget()
        self.tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Pestaña 1: Libro de Colorear
        self.edit_scene = QGraphicsScene()
        self.edit_view = InteractiveGraphicsView(self.edit_scene)
        self.edit_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # Aceleración por Hardware para la imagen de edición
        self.edit_view.setViewport(QOpenGLWidget())
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
        self.tabs.addTab(self.edit_view, "Coloreo Interactivo")
        
        # Pestaña 2: Simulación DST
        self.sim_widget = QWidget()
        sim_layout = QVBoxLayout(self.sim_widget)
        
        self.btn_load_dst = QPushButton("Cargar Archivo Existente")
        self.btn_load_dst.clicked.connect(self.load_embroidery_file)
        
        self.btn_export_sim = QPushButton("Exportar Simulación a PNG")
        self.btn_export_sim.clicked.connect(self.export_simulation)
        self.btn_export_sim.setEnabled(False)
        
        self.btn_export_pdf = QPushButton("Hoja de Producción (PDF)")
        self.btn_export_pdf.setToolTip("Exporta un PDF con la secuencia de hilos y estadísticas")
        self.btn_export_pdf.clicked.connect(self.export_production_sheet)
        self.btn_export_pdf.setEnabled(False)

        sim_buttons_layout = QHBoxLayout()
        sim_buttons_layout.addWidget(self.btn_load_dst)
        sim_buttons_layout.addWidget(self.btn_export_sim)
        sim_buttons_layout.addWidget(self.btn_export_pdf)

        self.lbl_stats = QLabel("Estadísticas de Bordado: N/A")
        self.lbl_stats.setStyleSheet("background-color: #1e1f22; border: 1px solid #393b40; padding: 10px; border-radius: 4px; font-weight: bold; color: #8fa1b3;")
        
        self.scene = QGraphicsScene()
        self.view = ZoomableView(self.scene)
        self.view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # Aceleración por Hardware para la simulación (Soporta +100k puntadas a 60 FPS)
        self.view.setViewport(QOpenGLWidget())
        
        sim_layout.addLayout(sim_buttons_layout)
        sim_layout.addLayout(zoom_layout)
        sim_layout.addWidget(self.lbl_stats)
        sim_layout.addWidget(self.view, 1)
        self.tabs.addTab(self.sim_widget, "Simulación")
        
        center_panel.addWidget(self.tabs)
        
        splitter.addWidget(center_widget)

        # --- PANEL DERECHO: Lista de Colores ---
        right_widget = QWidget()
        right_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        right_widget.setMinimumWidth(280)
        right_widget.setMaximumWidth(380)
        right_panel = QVBoxLayout(right_widget)
        right_panel.setContentsMargins(0, 0, 0, 0)
        
        # --- 1. Paleta de Hilos ---
        palette_header_layout = QHBoxLayout()
        lbl_palette = QLabel("Paleta:")
        lbl_palette.setObjectName("headerLabel")
        
        self.combo_palette = QComboBox()
        self.combo_palette.addItems(["Brother", "Madeira", "Isacord", "Sulky"])
        self.combo_palette.currentIndexChanged.connect(self.on_palette_changed)
        
        palette_header_layout.addWidget(lbl_palette)
        palette_header_layout.addWidget(self.combo_palette)
        right_panel.addLayout(palette_header_layout)
        
        # Indicador de Color Activo
        self.lbl_active_color_preview = QLabel("Ningún Hilo Seleccionado")
        self.lbl_active_color_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_active_color_preview.setFixedHeight(35)
        right_panel.addWidget(self.lbl_active_color_preview)
        
        self.palette_list = QListWidget()
        self.palette_list.setMinimumWidth(240)
        self.palette_list.setMaximumWidth(360)
        self.palette_list.setIconSize(QSize(24, 24))
        self.current_palette = BROTHER_COLORS
        self.populate_palette_list()
        self.palette_list.itemSelectionChanged.connect(self.on_palette_selection)
        right_panel.addWidget(self.palette_list, 1)
        
        # --- 2. Hilos Usados ---
        self.lbl_hilos = QLabel("Hilos Usados: 0 / 6")
        self.lbl_hilos.setObjectName("headerLabel")
        right_panel.addWidget(self.lbl_hilos)
        
        self.used_colors_list = QListWidget()
        self.used_colors_list.setMinimumWidth(240)
        self.used_colors_list.setMaximumWidth(360)
        self.used_colors_list.setIconSize(QSize(24, 24))
        right_panel.addWidget(self.used_colors_list)
        
        splitter.addWidget(right_widget)
        splitter.setChildrenCollapsible(False)
        splitter.setOpaqueResize(True)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        splitter.setStretchFactor(2, 1)

        # Proporciones iniciales del Splitter (Izquierda, Centro, Derecha)
        splitter.setSizes([360, 960, 320])
        
        self.apply_modern_theme()

    def apply_modern_theme(self):
        """Aplica una hoja de estilos (QSS) profesional estilo Tema Oscuro / Moderno."""
        dark_theme = """
        QMainWindow, QWidget {
            background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1, stop:0 #181b20, stop:1 #24282f);
            color: #e5e7eb;
            font-family: 'Segoe UI', 'Inter', Helvetica, Arial, sans-serif;
            font-size: 10pt;
        }
        QGraphicsView, QScrollArea {
            background-color: #16181d;
            border: 1px solid #32363d;
            border-radius: 12px;
        }
        QPushButton {
            background-color: rgba(59, 78, 121, 0.15);
            border: 1px solid rgba(148, 163, 184, 0.18);
            border-radius: 12px;
            padding: 10px 14px;
            color: #f8fafc;
            font-weight: 600;
            min-height: 36px;
        }
        QPushButton:hover {
            background-color: rgba(59, 78, 121, 0.28);
            border-color: rgba(96, 165, 250, 0.35);
        }
        QPushButton:pressed {
            background-color: rgba(59, 78, 121, 0.4);
        }
        QPushButton:disabled {
            background-color: rgba(71, 85, 105, 0.18);
            color: #94a3b8;
            border: 1px solid rgba(71, 85, 105, 0.4);
        }
        QPushButton:checked {
            background-color: #2563eb;
            border: 1px solid #60a5fa;
            color: #ffffff;
            font-weight: 700;
        }
        QPushButton#primaryButton {
            background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1, stop:0 #3b82f6, stop:1 #2563eb);
            border: none;
            font-size: 11pt;
            font-weight: 700;
            border-radius: 16px;
            padding: 12px 18px;
            color: white;
        }
        QPushButton#primaryButton:hover {
            background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1, stop:0 #60a5fa, stop:1 #3b82f6);
        }
        QPushButton#primaryButton:pressed {
            background: #1d4ed8;
        }
        QGroupBox {
            background-color: rgba(26, 30, 37, 0.95);
            border: 1px solid rgba(96, 165, 250, 0.16);
            border-radius: 16px;
            margin-top: 22px;
            padding-top: 24px;
            padding-bottom: 12px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 4px 12px;
            color: #cbd5e1;
            font-weight: 700;
            background-color: rgba(15, 23, 42, 0.95);
            border-radius: 10px;
            top: -14px;
            left: 12px;
        }
        QListWidget {
            background-color: #161920;
            border: 1px solid rgba(148, 163, 184, 0.18);
            border-radius: 12px;
            outline: none;
        }
        QListWidget::item {
            padding: 8px;
            border-bottom: 1px solid rgba(71, 85, 105, 0.24);
            border-radius: 10px;
            margin: 4px 6px;
        }
        QListWidget::item:selected {
            background-color: rgba(59, 130, 246, 0.22);
            color: #ffffff;
            border: 1px solid rgba(96, 165, 250, 0.48);
        }
        QProgressBar {
            border: 1px solid rgba(148, 163, 184, 0.18);
            border-radius: 10px;
            text-align: center;
            background-color: rgba(15, 23, 42, 0.9);
            color: #e2e8f0;
            font-weight: 600;
            min-height: 24px;
        }
        QProgressBar::chunk {
            background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 #34d399, stop:1 #22c55e);
            border-radius: 8px;
        }
        QDialog {
            background-color: #171b22;
        }
        QTextEdit, QFontComboBox, QComboBox, QSpinBox, QListWidget, QLabel#imageLabel {
            background-color: #121519;
            border: 1px solid rgba(148, 163, 184, 0.16);
            color: #e2e8f0;
            border-radius: 10px;
            padding: 6px;
        }
        QSpinBox {
            padding: 6px 8px;
        }
        QSpinBox::up-button, QSpinBox::down-button {
            background-color: rgba(71, 85, 105, 0.3);
            border-radius: 4px;
            width: 20px;
        }
        QSpinBox::up-button:hover, QSpinBox::down-button:hover {
            background-color: rgba(96, 165, 250, 0.25);
        }
        QCheckBox {
            spacing: 8px;
            color: #cbd5e1;
        }
        QLabel#headerLabel {
            font-size: 11pt;
            font-weight: 700;
            color: #93c5fd;
            padding-bottom: 6px;
            border: none;
        }
        QLabel#imageLabel {
            border: none;
            color: #94a3b8;
        }
        QSplitter::handle {
            background-color: rgba(71, 85, 105, 0.2);
            width: 6px;
            border-radius: 3px;
        }
        QSplitter::handle:hover {
            background-color: rgba(96, 165, 250, 0.35);
        }
        QTabWidget::pane { border: none; background-color: transparent; }
        QTabBar::tab { background: rgba(15, 23, 42, 0.9); color: #94a3b8; padding: 10px 16px; border: 1px solid rgba(71, 85, 105, 0.3); border-bottom: none; border-top-left-radius: 14px; border-top-right-radius: 14px; margin-right: 2px;}
        QTabBar::tab:selected { background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #3b82f6); color: white; border-color: rgba(96, 165, 250, 0.8); }
        QTabBar::tab:hover { color: #ffffff; }
        QToolTip {
            background-color: #111827;
            color: #f8fafc;
            border: 1px solid rgba(148, 163, 184, 0.24);
            border-radius: 8px;
            padding: 6px;
        }
        """
        self.setStyleSheet(dark_theme)

    def resizeEvent(self, event):
        """Ajusta automáticamente las vistas de las escenas al cambiar el tamaño de la ventana."""
        super().resizeEvent(event)
        if self.edit_scene and not self.edit_scene.sceneRect().isNull():
            self.edit_view.fitInView(self.edit_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        if self.scene and self.scene.items():
            self.view.fitInView(self.scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def update_cursor(self):
        """Cambia el icono del ratón según la herramienta activa."""
        if self.btn_bucket.isChecked(): 
            cursor = Qt.CursorShape.CrossCursor
            if hasattr(self, 'statusBar'): self.statusBar.showMessage("Herramienta Activa: Balde de Pintura (Rellena áreas delimitadas con un clic).")
        elif self.btn_brush.isChecked(): 
            cursor = Qt.CursorShape.CrossCursor
            if hasattr(self, 'statusBar'): self.statusBar.showMessage("Herramienta Activa: Pincel (Mantén presionado para dibujar trazos de color libremente).")
        elif self.btn_eraser.isChecked(): 
            cursor = Qt.CursorShape.CrossCursor
            if hasattr(self, 'statusBar'): self.statusBar.showMessage("Herramienta Activa: Borrador (Elimina color y restaura el fondo blanco original).")
        elif self.btn_picker.isChecked(): 
            cursor = Qt.CursorShape.CrossCursor
            if hasattr(self, 'statusBar'): self.statusBar.showMessage("Herramienta Activa: Pipeta (Haz clic en un color del lienzo para seleccionarlo).")
        elif self.btn_line.isChecked() or self.btn_rect.isChecked() or self.btn_circle.isChecked():
            cursor = Qt.CursorShape.CrossCursor
            if hasattr(self, 'statusBar'): self.statusBar.showMessage("Herramienta Activa: Formas (Arrastra para dibujar la forma seleccionada).")
        else: 
            cursor = Qt.CursorShape.ArrowCursor
        
        self.edit_view.viewport().setCursor(cursor)

    def populate_palette_list(self):
        self.palette_list.clear()
        for name, r, g, b in self.current_palette:
            item = QListWidgetItem(f"{name} ({r},{g},{b})")
            pixmap = QPixmap(24, 24)
            pixmap.fill(QColor(r, g, b))
            item.setIcon(QIcon(pixmap))
            item.setData(Qt.ItemDataRole.UserRole, (b, g, r))
            self.palette_list.addItem(item)
            
    def on_palette_changed(self, index):
        if index == 0: self.current_palette = BROTHER_COLORS
        elif index == 1: self.current_palette = MADEIRA_COLORS
        elif index == 2: self.current_palette = ISACORD_COLORS
        elif index == 3: self.current_palette = SULKY_COLORS
        self.populate_palette_list()
        self.active_color = None
        self.lbl_active_color_preview.setText("Ningún Hilo Seleccionado")
        self.lbl_active_color_preview.setStyleSheet("")

    def update_active_color_ui(self, b, g, r):
        """Actualiza el panel visual con el color activo."""
        # Calcular luminancia para decidir si la letra es blanca o negra
        luma = (r * 0.299 + g * 0.587 + b * 0.114)
        text_color = "black" if luma > 186 else "white"
        self.lbl_active_color_preview.setText(f"Color Activo: ({r}, {g}, {b})")
        self.lbl_active_color_preview.setStyleSheet(
            f"background-color: rgb({r}, {g}, {b}); color: {text_color}; "
            f"border: 1px solid #5e6266; border-radius: 4px; font-weight: bold;"
        )

    def on_palette_selection(self):
        """Actualiza el color activo cuando el usuario hace clic en la lista de paleta."""
        selected = self.palette_list.currentItem()
        if selected:
            self.active_color = selected.data(Qt.ItemDataRole.UserRole)
            self.update_active_color_ui(*self.active_color)

    def on_thumbnail_color_picked(self, color):
        """Atrapa el color si el usuario usa la pipeta sobre la miniatura original."""
        if self.btn_picker.isChecked():
            self.active_color = color
            self.palette_list.clearSelection()
            self.update_active_color_ui(*self.active_color)

    def load_image(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Abrir Imagen", "", "Imágenes (*.png *.jpg *.jpeg *.bmp)"
        )
        if file_name:
            try:
                self.current_image_path = file_name
                
                # Guardamos la matriz de colores original en memoria para el autodetector
                self._original_bgr, _ = _load_and_preprocess_image(file_name)
                
                # Cargar imagen real y mostrar miniatura
                with open(file_name, "rb") as f:
                    img_array = np.frombuffer(f.read(), dtype=np.uint8)
                img_orig = cv2.imdecode(img_array, cv2.IMREAD_UNCHANGED)
                pixmap_thumb = QPixmap(file_name)
                self.lbl_thumbnail.set_image(pixmap_thumb, img_orig)
                
                self.current_coloring_img = generate_coloring_book(file_name)
                
                self.used_colors.clear()
                self.history.clear()
                self.redo_history.clear()
                self.btn_undo.setEnabled(False)
                self.btn_redo.setEnabled(False)
                self.btn_auto_color.setEnabled(True)
                
                # --- NUEVO: PREGUNTA PARA AUTO-DIGITALIZAR Y EVITAR CENTRO BLANCO ---
                reply = QMessageBox.question(
                    self, 'Procesamiento de Imagen', 
                    '¿Deseas auto-digitalizar la imagen para mantener los colores originales?\n(Recomendado para evitar que el centro del diseño quede en blanco)',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                    QMessageBox.StandardButton.Yes
                )
                
                if reply == QMessageBox.StandardButton.Yes:
                    self.auto_color_action(prompt=False)
                else:
                    self.update_image_display()
                    self.update_size_info()
                    self.update_color_counter()
                    
                self.edit_view.fitInView(self.edit_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
                self.update_hoop_visualizer()
                self.tabs.setCurrentIndex(0)  # Cambiar a la pestaña de dibujo
                self.btn_preview.setEnabled(True)
                self.btn_generate.setEnabled(True)
                self.btn_export_img.setEnabled(True)
                self.statusBar.showMessage(f"Imagen cargada exitosamente: {os.path.basename(file_name)}. ¡Usa las herramientas para editar!")
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
        
    def save_colored_image(self):
        """Exporta el lienzo coloreado actualmente a un archivo PNG."""
        if self.current_coloring_img is None: return
        file_name, _ = QFileDialog.getSaveFileName(self, "Guardar Lienzo", "lienzo_coloreado.png", "Imágenes PNG (*.png)")
        if file_name:
            _, img_encoded = cv2.imencode(".png", self.current_coloring_img)
            with open(file_name, "wb") as f:
                f.write(img_encoded.tobytes())
            QMessageBox.information(self, "Éxito", "Lienzo guardado exitosamente.")

    def add_text_action(self):
        """Abre el módulo avanzado de Monogramas para ingresar texto con tipografías y lo convierte en un lienzo."""
        dialog = AdvancedTextDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.generated_image:
            img = dialog.generated_image
            
            # Convertir la imagen Qt de forma segura a matriz NumPy (OpenCV)
            ba = QByteArray()
            buffer = QBuffer(ba)
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            img.save(buffer, "PNG")
            
            np_arr = np.frombuffer(ba.data(), dtype=np.uint8)
            text_img_bgra = cv2.imdecode(np_arr, cv2.IMREAD_UNCHANGED)
            
            # Ajustar el fondo para que el motor lo reconozca como lienzo dibujable
            trans_mask = text_img_bgra[:, :, 3] == 0
            text_img_bgra[trans_mask] = [255, 255, 255, 0]

            self.current_image_path = "texto_generado"
            self._original_bgr = text_img_bgra[:, :, :3]
            
            self.save_to_history()
            self.current_coloring_img = text_img_bgra
            
            b, g, r = dialog.selected_color.blue(), dialog.selected_color.green(), dialog.selected_color.red()
            
            self.used_colors.clear()
            self.used_colors.add((b, g, r))
            self.refresh_used_colors()
            self.update_image_display()
            self.update_hoop_visualizer()
            self.update_size_info()
            self.btn_preview.setEnabled(True)
            self.btn_generate.setEnabled(True)
            self.statusBar.showMessage(f"Texto avanzado generado exitosamente. Listo para bordar.")

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
            if len(self.history) > 10: # Limitar a 10 pasos protege fuertemente la RAM (matrices de 1000x1000px pesan mucho)
                self.history.pop(0)
            self.btn_undo.setEnabled(True)
            self.redo_history.clear()
            self.btn_redo.setEnabled(False)
            
    def undo_action(self):
        """Restaura el estado anterior de la imagen."""
        if self.history:
            self.redo_history.append(self.current_coloring_img.copy())
            self.btn_redo.setEnabled(True)
            self.current_coloring_img = self.history.pop()
            if not self.history:
                self.btn_undo.setEnabled(False)
            self.refresh_used_colors()
            self.update_image_display()
            
    def redo_action(self):
        """Rehace el cambio deshecho."""
        if self.redo_history:
            self.history.append(self.current_coloring_img.copy())
            self.btn_undo.setEnabled(True)
            self.current_coloring_img = self.redo_history.pop()
            if not self.redo_history:
                self.btn_redo.setEnabled(False)
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
            self.update_size_info()

    def on_image_clicked(self, x, y):
        """Evento que dispara el Flood Fill o el Borrador cuando el usuario hace clic en el dibujo."""
        if self.current_coloring_img is None: return
        self.shape_start = (x, y)
        
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
            self.update_active_color_ui(*self.active_color)
            return
            
        # --- MAGIA: AUTODETECTAR COLOR SI NO HAS SELECCIONADO NINGUNO ---
        if not self.active_color and hasattr(self, '_original_bgr'):
            try:
                orig_b, orig_g, orig_r = self._original_bgr[y, x]
                # Si la zona que tocaste no es fondo blanco puro, extraemos su color
                if not (orig_b > 240 and orig_g > 240 and orig_r > 240):
                    closest_name, br, bg, bb = get_closest_thread_color(int(orig_r), int(orig_g), int(orig_b), self.current_palette)
                    self.active_color = (bb, bg, br)
                    self.update_active_color_ui(bb, bg, br)
                    self.statusBar.showMessage(f"Hilo autodetectado de la imagen original: {closest_name}")
            except IndexError:
                pass
                
        if self.btn_line.isChecked() or self.btn_rect.isChecked() or self.btn_circle.isChecked():
            if not self.active_color:
                QMessageBox.information(self, "Selecciona un Hilo", "Por favor, selecciona un color de la Paleta Brother a la derecha antes de dibujar.")
                return
            bgr_color = self.active_color
            if bgr_color not in self.used_colors and len(self.used_colors) >= 6:
                QMessageBox.warning(self, "Límite Técnico Excedido", "Máximo 6 colores permitidos para este modelo de máquina.")
                return
            self.save_to_history()
            self.base_coloring_img = self.current_coloring_img.copy()
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
        if b == 1 and g == 1 and r == 1: return
        
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
        elif self.btn_line.isChecked() or self.btn_rect.isChecked() or self.btn_circle.isChecked():
            if not self.active_color: return
            if not hasattr(self, 'shape_start'): self.shape_start = (prev_x, prev_y)
            if not hasattr(self, 'base_coloring_img') or self.base_coloring_img is None:
                self.base_coloring_img = self.current_coloring_img.copy()
                
            preview = self.base_coloring_img.copy()
            color = (self.active_color[0], self.active_color[1], self.active_color[2], 255)
            thickness = self.slider_eraser.value()
            
            if self.btn_line.isChecked():
                cv2.line(preview, self.shape_start, (x, y), color, thickness, cv2.LINE_AA)
            elif self.btn_rect.isChecked():
                if thickness > 20: thickness = cv2.FILLED
                cv2.rectangle(preview, self.shape_start, (x, y), color, thickness, cv2.LINE_AA)
            elif self.btn_circle.isChecked():
                radius = int(math.hypot(x - self.shape_start[0], y - self.shape_start[1]))
                if thickness > 20: thickness = cv2.FILLED
                cv2.circle(preview, self.shape_start, radius, color, thickness, cv2.LINE_AA)
                
            self.current_coloring_img = preview
            self.update_image_display()
            
    def auto_color_action(self, checked=False, prompt=True):
        """Auto-Digitaliza la imagen con K-Means y los colores de Brother."""
        if not self.current_image_path: return
        
        if prompt:
            reply = QMessageBox.question(
                self, 'Auto-Digitalización (IA)', 
                'Esta función usará agrupamiento K-Means para reducir la imagen original a un máximo de 6 colores de la paleta Brother automáticamente.\n\n¿Deseas continuar?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                QMessageBox.StandardButton.Yes
            )
            if reply == QMessageBox.StandardButton.No: return
        
        self.save_to_history()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        
        try:
            img_kmeans = apply_auto_color_kmeans(self.current_image_path, max_colors=6)
            new_img = img_kmeans.copy() # <-- CLAVE: Crear un lienzo limpio para aplicar los colores.
            pixels = img_kmeans.reshape(-1, 4)
            unique_colors = np.unique(pixels, axis=0)
            
            for color in unique_colors:
                b, g, r, a = color
                # Ignorar transparente, bordes negros generados, y blanco puro del fondo
                if a < 128: continue
                if b == 1 and g == 1 and r == 1: continue
                if b > 240 and g > 240 and r > 240: continue
                
                # Encontrar color de la paleta seleccionada más cercano (Usando mejor métrica)
                closest_name, cr, cg, cb = get_closest_thread_color(int(r), int(g), int(b), self.current_palette)
                closest_bgr = (cb, cg, cr)
                
                # Reemplazar grupo de color por el hilo exacto Brother
                if closest_bgr:
                    mask = (img_kmeans[:, :, 0] == b) & (img_kmeans[:, :, 1] == g) & (img_kmeans[:, :, 2] == r) & (img_kmeans[:, :, 3] == a) # <-- La máscara se crea desde el original
                    new_img[mask] = [*closest_bgr, a] # <-- El color se pinta en la copia
                    
            self.current_coloring_img = new_img # <-- Asignar el resultado final ya procesado.
            self.refresh_used_colors()
            self.update_image_display()
            self.update_size_info()
            
        except Exception as e:
            QMessageBox.critical(self, "Error Técnico", f"Ocurrió un error al aplicar K-Means:\n{str(e)}")
            self.undo_action()
        finally:
            QApplication.restoreOverrideCursor()
            
    def auto_fit_to_hoop(self, idx=None):
        """Ajusta automáticamente la escala del diseño para que encaje de forma óptima en el bastidor seleccionado."""
        if idx is None or isinstance(idx, bool):
            idx = self.combo_hoop.currentIndex()
            
        if idx == 0 or self.current_coloring_img is None:
            return
            
        # Definimos los márgenes máximos permitidos (5 mm de seguridad)
        if idx == 1: max_w, max_h = 95, 95     # Bastidor 100x100
        elif idx == 2: max_w, max_h = 125, 175 # Bastidor 130x180
        elif idx == 3: max_w, max_h = 155, 255 # Bastidor 160x260
        else: return
        
        mask = self.current_coloring_img[:, :, 3] > 128
        coords = cv2.findNonZero(mask.astype(np.uint8))
        if coords is not None:
            x, y, w, h = cv2.boundingRect(coords)
            
            scale_normal = min((max_w * 10.0) / w, (max_h * 10.0) / h)
            scale_rotated = min((max_h * 10.0) / w, (max_w * 10.0) / h)
            
            optimal_scale = max(scale_normal, scale_rotated)
            optimal_scale_int = max(1, min(50, int(optimal_scale)))
            
            self.spin_scale.setValue(optimal_scale_int)

    def update_hoop_visualizer(self):
        """Actualiza el cuadro rojo limitante según la escala y el tamaño del bastidor."""
        idx = self.combo_hoop.currentIndex()
        if idx == 0:
            self.edit_view.set_hoop_size(None, None)
            return
            
        # Calculo físico: 1 pixel en la vista = `scale / 10` milímetros.
        scale = self.spin_scale.value() or 1
        pix_per_mm = 10.0 / scale
        
        if idx == 1: w_mm, h_mm = 100, 100
        elif idx == 2: w_mm, h_mm = 130, 180
        elif idx == 3: w_mm, h_mm = 160, 260
        else: return
        
        self.edit_view.set_hoop_size(w_mm * pix_per_mm, h_mm * pix_per_mm)

    def update_size_info(self):
        """Actualiza la etiqueta con las dimensiones físicas reales del bordado."""
        if self.current_coloring_img is None:
            self.lbl_size_info.setText("Tamaño: -- x -- mm")
            return
            
        mask = self.current_coloring_img[:, :, 3] > 128
        coords = cv2.findNonZero(mask.astype(np.uint8))
        if coords is not None:
            x, y, w, h = cv2.boundingRect(coords)
            scale = self.spin_scale.value()
            final_w = w * scale / 10.0
            final_h = h * scale / 10.0
            self.lbl_size_info.setText(f"Tamaño: {final_w:.1f} x {final_h:.1f} mm")
        else:
            self.lbl_size_info.setText("Tamaño: 0.0 x 0.0 mm")
            
    def validate_hoop_size(self):
        """Valida que el bordado final no exceda el tamaño del bastidor físico elegido."""
        idx = self.combo_hoop.currentIndex()
        if idx == 0: return True
        
        if idx == 1: max_w, max_h = 100, 100
        elif idx == 2: max_w, max_h = 130, 180
        elif idx == 3: max_w, max_h = 160, 260
        else: return True
        
        scale = self.spin_scale.value()
        if self.current_coloring_img is None: return True
        
        mask = self.current_coloring_img[:, :, 3] > 128
        coords = cv2.findNonZero(mask.astype(np.uint8))
        if coords is not None:
            x, y, w, h = cv2.boundingRect(coords)
            final_w = w * scale / 10.0
            final_h = h * scale / 10.0
            
            # Verifica que encaje, evaluando rotaciones (horizontal o vertical)
            fits_normal = final_w <= max_w and final_h <= max_h
            fits_rotated = final_w <= max_h and final_h <= max_w
            
            if not (fits_normal or fits_rotated):
                QMessageBox.warning(self, "Tamaño de Bastidor Excedido", 
                    f"El diseño mide {final_w:.1f} x {final_h:.1f} mm y NO entra en el bastidor de {max_w}x{max_h} mm.\n\n"
                    "Solución: Reduce el número en la opción 'Escala del Bordado' para achicar el diseño hasta que encaje."
                )
                return False
        return True

    def refresh_used_colors(self):
        """Revisa la imagen entera al soltar el clic para ver qué colores quedan realmente tras borrar."""
        if hasattr(self, 'base_coloring_img'):
            self.base_coloring_img = None
            
        if self.current_coloring_img is None: return
        pixels = self.current_coloring_img.reshape(-1, 4)
        unique_colors = np.unique(pixels, axis=0)
        self.used_colors.clear()
        for color in unique_colors:
            b, g, r, a = color
            t_color = (int(b), int(g), int(r))
            # Ignoramos el blanco puro, el negro (líneas) y lo transparente
            if a > 128 and t_color != (255, 255, 255) and t_color != (1, 1, 1):
                self.used_colors.add(t_color)
        self.update_color_counter()
        self.update_size_info()

    def generate_preview(self):
        if self.current_coloring_img is None: return
        
        if not self.used_colors:
            QMessageBox.warning(self, "Lienzo Vacío", "Por favor, pinta al menos un área con la paleta de colores antes de previsualizar.")
            return
        
        if not self.validate_hoop_size():
            return
        
        scale = self.spin_scale.value()
        add_outlines = self.chk_outlines.isChecked()
        
        self.btn_preview.setEnabled(False)
        self.btn_generate.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        self.worker = EmbroideryWorker(self.current_coloring_img, scale, add_outlines, preview_only=True, palette=self.current_palette)
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
            
        if not self.validate_hoop_size():
            return
            
        output_path, _ = QFileDialog.getSaveFileName(
            self, "Guardar Bordado", "resultado.pes", "Brother PES (*.pes);;Tajima DST (*.dst);;Janome JEF (*.jef);;Bernina EXP (*.exp)"
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
        self.worker = EmbroideryWorker(self.current_coloring_img, scale, add_outlines, output_path, palette=self.current_palette)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.finished_save.connect(self.on_generation_finished)
        self.worker.error.connect(self.on_generation_error)
        self.worker.start()

    def on_generation_finished(self, output_path):
        self.btn_generate.setEnabled(True)
        self.btn_preview.setEnabled(True)
        self.tabs.setCurrentIndex(1) # Saltar mágicamente a la simulación
        self.statusBar.showMessage("¡Bordado generado y listo para simular!")
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
            item = QListWidgetItem(f"{thread_name}")
            pixmap = QPixmap(24, 24)
            pixmap.fill(c)
            item.setIcon(QIcon(pixmap))
            self.used_colors_list.addItem(item)
            
        # Dibujar las puntadas
        pen = QPen()
        pen.setWidth(2)  # Grosor fijo en pantalla (Nítido y profesional)
        pen.setCosmetic(True)  # Fundamental: Evita que Qt deforme los cruces creando "glitches" o hilos extraños
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        
        path = QPainterPath()
        current_color_idx = 0
        
        if colors:
            pen.setColor(colors[0])
            
        last_x, last_y = 0, 0
        
        for stitch in pattern.stitches:
            x, y, cmd = stitch[0], stitch[1], stitch[2]
            
            if cmd == pyembroidery.COLOR_CHANGE:
                if not path.isEmpty():
                    self.scene.addPath(path, pen)
                path = QPainterPath()
                current_color_idx = (current_color_idx + 1) % len(colors)
                if current_color_idx < len(colors):
                    pen.setColor(colors[current_color_idx])
                path.moveTo(x, y)
                last_x, last_y = x, y
            elif cmd == pyembroidery.JUMP or cmd == pyembroidery.TRIM:
                # Cortar el path anterior aquí evita cruces extraños en la renderización
                if not path.isEmpty():
                    self.scene.addPath(path, pen)
                path = QPainterPath()
                path.moveTo(x, y)
                last_x, last_y = x, y
            elif cmd == pyembroidery.STITCH:
                if path.isEmpty():
                    path.moveTo(last_x, last_y)
                path.lineTo(x, y)
                last_x, last_y = x, y
                
        if not path.isEmpty():
            self.scene.addPath(path, pen)
            
        self.view.fitInView(self.scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.lbl_stats.setText(f"Estadísticas de Bordado: {len(pattern.stitches)} Puntadas | {num_colors_expected} Cambios de Color")
        self.btn_export_sim.setEnabled(True)
        self.btn_export_pdf.setEnabled(True)

    def export_simulation(self):
        if not self.scene.items(): return
        file_name, _ = QFileDialog.getSaveFileName(self, "Exportar Simulación", "simulacion.png", "Imágenes PNG (*.png)")
        if file_name:
            rect = self.scene.itemsBoundingRect()
            rect.adjust(-10, -10, 10, 10)
            img = QImage(int(rect.width()), int(rect.height()), QImage.Format.Format_ARGB32)
            img.fill(Qt.GlobalColor.transparent)
            painter = QPainter(img)
            self.scene.render(painter, target=QRectF(img.rect()), source=rect)
            painter.end()
            img.save(file_name)
            QMessageBox.information(self, "Éxito", "Simulación exportada correctamente.")

    def export_production_sheet(self):
        if not self.scene.items(): return
        file_name, _ = QFileDialog.getSaveFileName(self, "Exportar Hoja de Producción", "hoja_produccion.pdf", "Archivos PDF (*.pdf)")
        if file_name:
            writer = QPdfWriter(file_name)
            writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
            writer.setResolution(300)
            painter = QPainter(writer)
            
            font = QFont("Arial", 16, QFont.Weight.Bold)
            painter.setFont(font)
            painter.drawText(100, 200, "Hoja de Producción de Bordado")
            
            font.setPointSize(12)
            font.setWeight(QFont.Weight.Normal)
            painter.setFont(font)
            painter.drawText(100, 400, self.lbl_stats.text())
            
            y_offset = 600
            painter.drawText(100, y_offset, "Secuencia de Hilos:")
            y_offset += 200
            
            for i in range(self.used_colors_list.count()):
                item = self.used_colors_list.item(i)
                painter.drawText(150, y_offset, f"{i+1}. {item.text()}")
                y_offset += 150
                
            painter.end()
            QMessageBox.information(self, "Éxito", "Hoja de producción PDF generada.")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = EmbroideryApp()
    window.show()
    sys.exit(app.exec())
    