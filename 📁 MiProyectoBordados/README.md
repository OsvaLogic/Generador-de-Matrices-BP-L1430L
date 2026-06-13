# 🧵 Brother Bordados Auto-Digitizer

<div align="center">
  <img src="https://img.shields.io/badge/Versi%C3%B3n-1.8-blue?style=for-the-badge" alt="Version 1.8">
  <img src="https://img.shields.io/badge/Status-Activo-success?style=for-the-badge" alt="Status">
  <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Django-092E20?style=for-the-badge&logo=django&logoColor=white" alt="Django">
  <img src="https://img.shields.io/badge/OpenCV-5C3EE8?style=for-the-badge&logo=opencv&logoColor=white" alt="OpenCV">
  <img src="https://img.shields.io/badge/PyQt6-41CD52?style=for-the-badge&logo=qt&logoColor=white" alt="PyQt">
  <br>
  <p><i>Un motor inteligente de auto-digitalización desarrollado por <b>Osva.Logic</b></i></p>
</div>

---

## 📖 Acerca del Proyecto
Motor Full-Stack inteligente que convierte imágenes (PNG/JPG) en archivos de bordado (.DST, .PES). Utiliza OpenCV y pyembroidery para el cálculo de puntadas y color. Incluye una interfaz web hiper-moderna (Django) y una app de escritorio (PyQt6) con lienzo interactivo y simulador. ¡Automatiza y digitaliza tus diseños a otro nivel!

### ✨ Características Principales
- 💻 **Web UI de Alto Nivel:** Diseño *Glassmorphism* oscuro, Drag & Drop nativo y controles precisos.
- 🧮 **Motor Geométrico Inteligente:** Cálculo de rotación, espaciado Tatami, Pull-Compensation (compensación de tire) y underlays automáticos.
- 🎨 **Asignador de Hilos:** Conversión euclidiana del mapa de colores de la imagen original hacia la paleta de hilos estándar Brother.
- 🖥️ **Versión Desktop (Legacy):** Se conserva e incluye en el paquete un software de escritorio 100% funcional creado con PyQt6 para simulaciones avanzadas y coloreado manual de puntadas.

---

## 📂 Estructura del Repositorio

```text
📁 Proyecto/
├── 📁 config_project/    # Configuraciones globales de Django (Settings, URLs)
├── 📁 core/              # Aplicación Web principal
│   ├── converter.py      # Lógica OpenCV (Detección de bordes y coloring)
│   ├── stitcher.py       # Algoritmos pyembroidery (Puntadas y generación DST)
│   └── views.py          # Conexión Backend <-> Frontend
├── 📁 desktop_app/       # Legacy App (Software Desktop PyQt6)
├── 📁 templates/         # Archivos HTML de interfaz visual
└── 📁 static/            # CSS moderno (Glassmorphism & Glow effects) y JS
```

---

## 🚀 Instalación y Uso Rápido

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/OsvaLogic/Generador-de-Matrices-BP-L1430L.git
   cd "Generador-de-Matrices-BP-L1430L/📁 MiProyectoBordados"
   ```

2. **Crear e inicializar el entorno virtual (Recomendado):**
   ```bash
   py -m venv venv  # Usa 'python' si 'py' no está disponible
   
   # En Windows (Git Bash):
   source venv/Scripts/activate
   # En Windows (PowerShell):
   .\venv\Scripts\Activate.ps1
   # En Mac/Linux:
   source venv/bin/activate
   ```

3. **Instalar las dependencias del proyecto:**
   ```bash
   pip install django opencv-python numpy pyembroidery PyQt6 shapely scikit-image torch
   ```

4. **Ejecutar el proyecto (Elige tu versión preferida):**

   **Opción A: Motor Web (Django)**
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   python manage.py runserver
   ```
   *Abre tu navegador en `http://localhost:8000` y ¡disfruta automatizando bordados!*

   **Opción B: Aplicación de Escritorio (PyQt6)**
   ```bash
   python desktop_app/main.py
   ```

---
*Diseñado y desarrollado a otro nivel por Osva.Logic.*
