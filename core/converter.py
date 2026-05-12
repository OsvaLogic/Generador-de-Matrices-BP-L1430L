
import cv2
import numpy as np

def generate_coloring_book(image_path):
    """Convierte la imagen en un lienzo de colorear (líneas negras sobre blanco)."""
    img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"No se pudo cargar la imagen desde: {image_path}")
        
    # --- AUTO REDIMENSIONAR PARA EVITAR CRASH Y LENTITUD ---
    max_dim = 1000
    h, w = img.shape[:2]
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    # Saneamiento de canales
    if len(img.shape) == 3 and img.shape[2] == 4:
        alpha_orig = img[:, :, 3].copy()
        # Pre-mezclar la transparencia con fondo blanco para que no se genere un cuadrado
        alpha_norm = img[:, :, 3] / 255.0
        white_bg = np.ones_like(img[:, :, :3], dtype=np.uint8) * 255
        bgr = (alpha_norm[..., np.newaxis] * img[:, :, :3] + (1 - alpha_norm[..., np.newaxis]) * white_bg).astype(np.uint8)
    elif len(img.shape) == 2:
        bgr = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        alpha_orig = np.ones(bgr.shape[:2], dtype=np.uint8) * 255
    else:
        bgr = img.copy()
        alpha_orig = np.ones(bgr.shape[:2], dtype=np.uint8) * 255
    
    # Convertir a escala de grises
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    
    # Filtro Bilateral: Suaviza la imagen conservando los bordes duros (elimina ruido y sombras)
    blur = cv2.bilateralFilter(gray, 9, 75, 75)
    
    # Umbral adaptativo: Extrae líneas excelentes y robustas sin importar la iluminación
    adaptive = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    
    # Detección de bordes Canny auxiliar y combinación final
    canny = cv2.Canny(blur, 50, 150)
    edges = cv2.bitwise_or(cv2.bitwise_not(adaptive), canny)
    
    # Eliminar el marco cuadrado absoluto
    edges[0:5, :] = 0; edges[-5:, :] = 0
    edges[:, 0:5] = 0; edges[:, -5:] = 0
    
    # Engrosar las líneas negras para delimitar mejor el color
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    edges = cv2.dilate(edges, kernel, iterations=1)
    
    coloring_book_bgr = cv2.cvtColor(cv2.bitwise_not(edges), cv2.COLOR_GRAY2BGR)
    result_bgra = cv2.cvtColor(coloring_book_bgr, cv2.COLOR_BGR2BGRA)
    
    # Hacer que las líneas sean opacas (255) y el cuerpo mantenga la opacidad original de la imagen
    result_bgra[:, :, 3] = np.maximum(alpha_orig, edges)
    
    return result_bgra

def apply_flood_fill(img_bgra, x, y, bgr_color):
    """Rellena un área delimitada con el color seleccionado simulando un balde de pintura."""
    result = img_bgra.copy()
    
    # Asegurar memoria contigua para la función interna de C++
    bgr = np.ascontiguousarray(result[:, :, :3])
    h, w = bgr.shape[:2]
    mask = np.zeros((h + 2, w + 2), np.uint8)
    
    # Convertir el hilo de Brother a tupla de enteros puros
    color = (int(bgr_color[0]), int(bgr_color[1]), int(bgr_color[2]))
    
    # Rellenar explícitamente indicando que modifique la máscara con el valor 255
    flags = 4 | (255 << 8) | cv2.FLOODFILL_FIXED_RANGE
    cv2.floodFill(bgr, mask, (x, y), color, (5, 5, 5), (5, 5, 5), flags)
    
    # Devolver colores y actualizar la opacidad del parche
    result[:, :, :3] = bgr
    fill_area = mask[1:-1, 1:-1] == 255
    result[:, :, 3][fill_area] = 255
    return result

def apply_eraser(img_bgra, x, y, radius=10, prev_x=None, prev_y=None):
    """Borra el color restaurando el papel blanco con interpolación continua."""
    result = img_bgra.copy()
    if prev_x is not None and prev_y is not None:
        cv2.line(result, (prev_x, prev_y), (x, y), (255, 255, 255, 255), thickness=radius*2, lineType=cv2.LINE_AA)
    cv2.circle(result, (x, y), radius, (255, 255, 255, 255), -1, lineType=cv2.LINE_AA)
    return result

def apply_brush(img_bgra, x, y, bgr_color, radius=10, prev_x=None, prev_y=None):
    """Dibuja un trazo de color libremente como un pincel con interpolación continua."""
    result = img_bgra.copy()
    color_bgra = (int(bgr_color[0]), int(bgr_color[1]), int(bgr_color[2]), 255)
    if prev_x is not None and prev_y is not None:
        cv2.line(result, (prev_x, prev_y), (x, y), color_bgra, thickness=radius*2, lineType=cv2.LINE_AA)
    cv2.circle(result, (x, y), radius, color_bgra, -1, lineType=cv2.LINE_AA)
    return result