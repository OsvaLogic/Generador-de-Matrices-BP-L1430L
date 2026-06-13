import cv2
import numpy as np

def _load_and_preprocess_image(image_path, max_dim=350):
    """Carga una imagen, previene crash por tamaño, y sanea los canales a BGR y Alpha."""
    with open(image_path, "rb") as f:
        img_array = np.frombuffer(f.read(), dtype=np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_UNCHANGED)
    
    if img is None:
        raise ValueError(f"No se pudo cargar la imagen desde: {image_path}")
        
    h, w = img.shape[:2]
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    has_alpha = len(img.shape) == 3 and img.shape[2] == 4
    if has_alpha:
        alpha_orig = img[:, :, 3].copy()
        alpha_norm = img[:, :, 3] / 255.0
        white_bg = np.ones_like(img[:, :, :3], dtype=np.uint8) * 255
        bgr = (alpha_norm[..., np.newaxis] * img[:, :, :3] + (1 - alpha_norm[..., np.newaxis]) * white_bg).astype(np.uint8)
    elif len(img.shape) == 2:
        bgr = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        alpha_orig = np.ones(bgr.shape[:2], dtype=np.uint8) * 255
    else:
        bgr = img.copy()
        alpha_orig = np.ones(bgr.shape[:2], dtype=np.uint8) * 255
        
    bgr = bgr.astype(np.uint8)
    alpha_orig = alpha_orig.astype(np.uint8)
    
    # [NUEVO]: Agregar un margen de seguridad (padding) para evitar que los bordes del dibujo se corten
    pad = 20
    bgr = cv2.copyMakeBorder(bgr, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=[255, 255, 255])
    alpha_pad_value = 0 if has_alpha else 255
    alpha_orig = cv2.copyMakeBorder(alpha_orig, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=alpha_pad_value)

    return bgr, alpha_orig

def create_text_image(text, font=cv2.FONT_HERSHEY_TRIPLEX, font_scale=3, thickness=5, color_bgr=(0, 0, 0)):
    """Genera una matriz de imagen a partir de texto para el Módulo de Monogramas."""
    (text_width, text_height), baseline = cv2.getTextSize(text, font, font_scale, thickness)
    
    img_h = text_height + baseline + 60
    img_w = text_width + 60
    img_bgra = np.ones((img_h, img_w, 4), dtype=np.uint8) * 255
    
    x, y = 30, text_height + 30
    color_bgra = (color_bgr[0], color_bgr[1], color_bgr[2], 255)
    
    cv2.putText(img_bgra, text, (x, y), font, font_scale, color_bgra, thickness, cv2.LINE_AA)
    
    white_pixels = (img_bgra[:, :, 0] == 255) & (img_bgra[:, :, 1] == 255) & (img_bgra[:, :, 2] == 255)
    img_bgra[white_pixels, 3] = 0
    
    return img_bgra

def generate_coloring_book(image_path):
    """Convierte la imagen en un lienzo de colorear (líneas negras sobre blanco)."""
    bgr, alpha_orig = _load_and_preprocess_image(image_path)
    object_mask = alpha_orig > 0
    
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    blur = cv2.bilateralFilter(gray, 9, 75, 75)
    adaptive = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    
    canny = cv2.Canny(blur, 50, 150)
    edges = cv2.bitwise_or(cv2.bitwise_not(adaptive), canny)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)), iterations=1)
    
    if np.any(alpha_orig == 0):
        object_mask_uint = (object_mask.astype(np.uint8) * 255)
        edges = cv2.bitwise_and(edges, object_mask_uint)
    
    edges[0:5, :] = 0; edges[-5:, :] = 0
    edges[:, 0:5] = 0; edges[:, -5:] = 0
    
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    edges = cv2.dilate(edges, kernel, iterations=1)
    
    coloring_book_bgr = cv2.cvtColor(cv2.bitwise_not(edges), cv2.COLOR_GRAY2BGR)
    coloring_book_bgr[edges == 255] = [1, 1, 1]
    result_bgra = cv2.cvtColor(coloring_book_bgr, cv2.COLOR_BGR2BGRA)
    
    result_alpha = np.where(object_mask, 255, 0).astype(np.uint8)
    result_bgra[:, :, 3] = result_alpha
    
    return result_bgra

def apply_auto_color_kmeans(image_path, max_colors=6):
    """Aplica K-Means para reducir colores y auto-digitalizar la imagen (Auto-Digitizing)."""
    bgr, alpha_orig = _load_and_preprocess_image(image_path)
    object_mask = alpha_orig > 0

    blur_source = cv2.bilateralFilter(bgr, 9, 75, 75)
    blur_float = blur_source.astype(np.float32) / 255.0
    lab_source = cv2.cvtColor(blur_float, cv2.COLOR_BGR2Lab)
    
    pixels_bgr = blur_source.reshape((-1, 3)).astype(np.float32)
    pixels_lab = lab_source.reshape((-1, 3)).astype(np.float32)

    # Detectar posible fondo blanco o transparente para no dejar que domine el K-Means.
    if np.any(alpha_orig == 0):
        bg_mask = alpha_orig.reshape(-1) == 0
    else:
        # Usar el borde para inferir el color de fondo en vez de tratar colores claros del objeto como fondo.
        border_pixels = np.concatenate([
            blur_source[:5, :, :].reshape(-1, 3),
            blur_source[-5:, :, :].reshape(-1, 3),
            blur_source[:, :5, :].reshape(-1, 3),
            blur_source[:, -5:, :].reshape(-1, 3),
        ], axis=0)
        border_float = border_pixels.reshape(-1, 1, 3).astype(np.float32) / 255.0
        border_lab = cv2.cvtColor(border_float, cv2.COLOR_BGR2Lab).reshape(-1, 3)
        bg_center_lab = np.median(border_lab, axis=0)

        border_hsv = cv2.cvtColor(border_pixels.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_BGR2HSV).reshape(-1, 3)
        border_is_light = np.mean(border_hsv[:, 2] > 220) > 0.65
        border_is_low_sat = np.mean(border_hsv[:, 1] < 35) > 0.65

        if border_is_light and border_is_low_sat:
            dist = np.linalg.norm(lab_source - bg_center_lab, axis=2)
            hsv = cv2.cvtColor(blur_source, cv2.COLOR_BGR2HSV)
            low_sat = hsv[:, :, 1] < 35
            bright = hsv[:, :, 2] > 220
            bg_candidate = (dist < 18) & low_sat & bright
            bg_mask = bg_candidate.reshape(-1)
            if np.sum(bg_mask) > bg_mask.size * 0.45:
                # Si el fondo detectado ocupa demasiado y puede ser parte del dibujo,
                # no aplicar máscara de fondo para evitar perder detalles.
                bg_mask = np.zeros_like(bg_mask)
        else:
            bg_mask = np.zeros(pixels_bgr.shape[0], dtype=bool)

    object_pixels_bgr = pixels_bgr[~bg_mask]
    object_pixels_lab = pixels_lab[~bg_mask]
    if object_pixels_bgr.size == 0:
        object_pixels_bgr = pixels_bgr
        object_pixels_lab = pixels_lab
        bg_mask = np.zeros(pixels_bgr.shape[0], dtype=bool)

    unique_pixels_lab = np.unique(object_pixels_lab, axis=0)
    k = min(max_colors, len(unique_pixels_lab))
    if k == 0:
        raise ValueError("No hay suficientes píxeles válidos para aplicar K-Means.")

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
    if k == 1:
        centers_lab = np.float32(unique_pixels_lab[:1])
        labels = np.zeros((object_pixels_lab.shape[0], 1), dtype=np.int32)
    else:
        _, labels, centers_lab = cv2.kmeans(object_pixels_lab, k, None, criteria, 10, cv2.KMEANS_PP_CENTERS)

    quantized_lab = np.full(pixels_lab.shape, [100.0, 0.0, 0.0], dtype=np.float32)
    quantized_lab[~bg_mask] = centers_lab[labels.flatten()]
    quantized_lab = quantized_lab.reshape(bgr.shape)
    
    quantized_bgr_float = cv2.cvtColor(quantized_lab, cv2.COLOR_Lab2BGR)
    quantized_bgr = np.clip(quantized_bgr_float * 255.0, 0, 255).astype(np.uint8)

    gray = cv2.cvtColor(blur_source, cv2.COLOR_BGR2GRAY)
    blur = cv2.bilateralFilter(gray, 9, 75, 75)

    adaptive = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    canny = cv2.Canny(blur, 50, 150)
    edges = cv2.bitwise_or(cv2.bitwise_not(adaptive), canny)
    
    edges[0:5, :] = 0; edges[-5:, :] = 0
    edges[:, 0:5] = 0; edges[:, -5:] = 0
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    edges = cv2.dilate(edges, kernel, iterations=1)

    result_bgra = cv2.cvtColor(quantized_bgr, cv2.COLOR_BGR2BGRA)

    object_mask = alpha_orig > 0
    edge_mask = (edges == 255) & object_mask
    if np.any(edge_mask):
        result_bgra[edge_mask, :3] = [0, 0, 0]

    result_bgra[:, :, 3] = alpha_orig
    final_alpha = alpha_orig.copy()
    if not np.any(alpha_orig == 0) and np.any(bg_mask):
        bg_mask_2d = bg_mask.reshape(bgr.shape[:2])
        final_alpha[bg_mask_2d] = 0
        
    result_bgra[:, :, 3] = final_alpha
    
    return result_bgra

def apply_flood_fill(img_bgra, x, y, bgr_color):
    """Rellena un área delimitada con el color seleccionado simulando un balde de pintura."""
    result = img_bgra.copy()
    bgr = np.ascontiguousarray(result[:, :, :3])
    h, w = bgr.shape[:2]
    mask = np.zeros((h + 2, w + 2), np.uint8)
    
    color = (int(bgr_color[0]), int(bgr_color[1]), int(bgr_color[2]))
    flags = 4 | (255 << 8) | cv2.FLOODFILL_FIXED_RANGE
    cv2.floodFill(bgr, mask, (x, y), color, (5, 5, 5), (5, 5, 5), flags)
    
    result[:, :, :3] = bgr
    fill_area = mask[1:-1, 1:-1] == 255
    result[:, :, 3][fill_area] = 255
    return result

def apply_eraser(img_bgra, x, y, radius=10, prev_x=None, prev_y=None):
    """Borra el color restaurando el papel blanco con interpolación continua."""
    result = img_bgra.copy()
    h, w = result.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    if prev_x is not None and prev_y is not None:
        cv2.line(mask, (prev_x, prev_y), (x, y), 255, thickness=radius * 2, lineType=cv2.LINE_AA)
    cv2.circle(mask, (x, y), radius, 255, -1, lineType=cv2.LINE_AA)

    erase_area = mask == 255
    result[erase_area, :3] = 255
    if result.shape[2] == 4:
        result[erase_area, 3] = 255
    return result

def apply_brush(img_bgra, x, y, bgr_color, radius=10, prev_x=None, prev_y=None):
    """Dibuja un trazo de color libremente como un pincel con interpolación continua."""
    result = img_bgra.copy()
    color_bgra = (int(bgr_color[0]), int(bgr_color[1]), int(bgr_color[2]), 255)
    if prev_x is not None and prev_y is not None:
        cv2.line(result, (prev_x, prev_y), (x, y), color_bgra, thickness=radius * 2, lineType=cv2.LINE_AA)
    cv2.circle(result, (x, y), radius, color_bgra, -1, lineType=cv2.LINE_AA)
    return result