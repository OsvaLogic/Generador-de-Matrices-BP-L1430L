
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
    
    # Convertir a escala de grises y suavizar para evitar ruido
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    img_blur = cv2.medianBlur(gray, 3) # Reducido a 3 para no borrar los detalles finos
    
    # Detección de bordes Canny
    edges = cv2.Canny(img_blur, 50, 150)
    
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

def apply_eraser(img_bgra, x, y, radius=10):
    """Borra el color restaurando el papel blanco."""
    result = img_bgra.copy()
    cv2.circle(result, (x, y), radius, (255, 255, 255, 255), -1)
    return result

def apply_brush(img_bgra, x, y, bgr_color, radius=10):
    """Dibuja un trazo de color libremente como un pincel."""
    result = img_bgra.copy()
    color_bgra = (int(bgr_color[0]), int(bgr_color[1]), int(bgr_color[2]), 255)
    cv2.circle(result, (x, y), radius, color_bgra, -1)
    return result