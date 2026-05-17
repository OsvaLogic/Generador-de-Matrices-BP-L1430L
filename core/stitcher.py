import numpy as np
import pyembroidery
import math
import cv2

# Paleta representativa de hilos estándar Brother (RGB)
BROTHER_COLORS = [
    ("Black", 0, 0, 0),
    ("Blue", 0, 0, 255),
    ("Brown", 153, 51, 0),
    ("Carmine", 204, 0, 51),
    ("Cyan", 0, 255, 255),
    ("Dark Brown", 102, 51, 0),
    ("Dark Fuchsia", 153, 0, 102),
    ("Dark Gray", 102, 102, 102),
    ("Dark Green", 0, 102, 0),
    ("Deep Gold", 255, 153, 0),
    ("Deep Green", 0, 153, 0),
    ("Deep Rose", 204, 0, 153),
    ("Flesh Pink", 255, 204, 204),
    ("Gold", 255, 204, 0),
    ("Gray", 153, 153, 153),
    ("Green", 0, 204, 0),
    ("Harvest Gold", 255, 153, 51),
    ("Khaki", 153, 153, 102),
    ("Light Blue", 153, 204, 255),
    ("Light Brown", 204, 153, 102),
    ("Light Lilac", 204, 153, 255),
    ("Lilac", 153, 102, 204),
    ("Magenta", 255, 0, 255),
    ("Mint Green", 102, 255, 153),
    ("Moss Green", 102, 153, 51),
    ("Navy", 0, 0, 102),
    ("Olive Green", 102, 102, 51),
    ("Orange", 255, 102, 0),
    ("Pink", 255, 102, 204),
    ("Purple", 102, 0, 153),
    ("Red", 255, 0, 0),
    ("Reddish Brown", 153, 51, 51),
    ("Salmon Pink", 255, 102, 102),
    ("Silver", 204, 204, 204),
    ("Sky Blue", 102, 153, 255),
    ("Teal Green", 0, 153, 153),
    ("Violet", 153, 0, 255),
    ("White", 255, 255, 255),
    ("Yellow", 255, 255, 0),
    ("Yellow Green", 153, 255, 51)
]

def get_closest_brother_color(r, g, b):
    """Encuentra el color Brother más cercano usando distancia ponderada (Luma) para mejor percepción visual."""
    # Ponderamos R, G y B según la sensibilidad del ojo humano para evitar emparejamientos extraños.
    return min(BROTHER_COLORS, key=lambda c: (r - c[1])**2 * 0.299 + (g - c[2])**2 * 0.587 + (b - c[3])**2 * 0.114)

def generate_tatami_from_colored_image(colored_img, output_path, scale=10, add_outlines=True, progress_callback=None):
    """Procesa los colores y convierte los píxeles en instrucciones y puntadas de la bordadora."""
    pattern = pyembroidery.EmbPattern()
    
    row_spacing_units = 4       
    stitch_length_units = 20    
    pull_comp_units = 5
    
    last_x, last_y = 0, 0
    
    # 1. Extraer canales BGR y Alpha
    bgr = colored_img[:, :, :3]
    alpha = colored_img[:, :, 3]
    
    # Aislar solo los píxeles que han sido pintados (opacos)
    valid_pixels = bgr[alpha > 128]
    if len(valid_pixels) == 0:
        return pattern
        
    unique_colors = np.unique(valid_pixels, axis=0)
    
    clean_masks = []
    
    for color in unique_colors:
        if np.array_equal(color, [0, 0, 0]): # Ignorar líneas negras de los bordes
            continue
            
        mask_bgr = cv2.inRange(bgr, color, color)
        mask_alpha = (alpha > 128).astype(np.uint8) * 255
        mask = cv2.bitwise_and(mask_bgr, mask_alpha)
        
        area = cv2.countNonZero(mask)
        if area > 0:
            clean_masks.append((color, mask, area))
            
    # 2. Orden de Capas: Ordenar de mayor a menor para evitar deformar la tela
    clean_masks.sort(key=lambda x: x[2], reverse=True)
    
    # Ángulos de rotación intercalados para evitar deformación en la tela (Puckering)
    ANGLES = [0, 45, 135, 90, 15, 165, 75, 105]
    
    # Calcular acolchado (padding) para la rotación basada en la diagonal máxima
    h, w = colored_img.shape[:2]
    diag = int(np.ceil(math.hypot(w, h)))
    pad_x = (diag - w) // 2
    pad_y = (diag - h) // 2
    cx_px, cy_px = diag / 2.0, diag / 2.0
    
    for idx, (color, mask, area) in enumerate(clean_masks):
        if progress_callback:
            progress_callback(int((idx / len(clean_masks)) * 100))
            
        # OpenCV usa BGR, invertimos a RGB para buscar el hilo y para pyembroidery
        name, br, bg, bb = get_closest_brother_color(color[2], color[1], color[0])
        
        thread = pyembroidery.EmbThread()
        thread.color = (int(br) << 16) | (int(bg) << 8) | int(bb)
        thread.description = name
        pattern.add_thread(thread)
        
        # Preparamos máscara enmarcada para la rotación
        padded = np.zeros((diag, diag), dtype=np.uint8)
        padded[pad_y:pad_y+h, pad_x:pad_x+w] = mask
        
        angle = ANGLES[idx % len(ANGLES)]
        M = cv2.getRotationMatrix2D((cx_px, cy_px), angle, 1.0)
        rotated_mask = cv2.warpAffine(padded, M, (diag, diag), flags=cv2.INTER_NEAREST)
        
        M_inv = cv2.getRotationMatrix2D((cx_px, cy_px), -angle, 1.0)
        
        def inv_transform(rx_scaled, ry_scaled):
            """Devuelve las coordenadas al espacio original sin rotar usando la matriz inversa."""
            px, py = rx_scaled / scale, ry_scaled / scale
            nx = M_inv[0, 0] * px + M_inv[0, 1] * py + M_inv[0, 2]
            ny = M_inv[1, 0] * px + M_inv[1, 1] * py + M_inv[1, 2]
            return (nx - pad_x) * scale, (ny - pad_y) * scale
        
        for pass_type in ['underlay', 'main']:
            if pass_type == 'underlay':
                current_spacing = int(row_spacing_units * 5)
                current_pull_comp = -5
                current_stitch_length = stitch_length_units * 1.5
            else:
                current_spacing = row_spacing_units
                current_pull_comp = pull_comp_units
                current_stitch_length = stitch_length_units
                
            direction = 1 
            
            max_y_units = diag * scale
            all_y = list(range(0, int(max_y_units), int(current_spacing)))
            
            if not all_y:
                continue
                
            mid_idx = len(all_y) // 2
            y_sequence_1 = all_y[mid_idx::-1]
            y_sequence_2 = all_y[mid_idx+1:]
            
            y_sequence = y_sequence_1 + y_sequence_2
            
            for y_scaled in y_sequence:
                y_px = int(y_scaled / scale)
                if y_px >= diag:
                    break
                    
                row = rotated_mask[y_px, :]
                indices = np.where(row)[0]
                
                if len(indices) == 0:
                    continue
                
                breaks = np.where(np.diff(indices) != 1)[0] + 1
                segments = np.split(indices, breaks)
                
                if direction == -1:
                    segments = segments[::-1]
                    
                for seg in segments:
                    x_start_scaled = seg[0] * scale - current_pull_comp
                    x_end_scaled = seg[-1] * scale + current_pull_comp
                    
                    if x_start_scaled >= x_end_scaled:
                        continue
                    
                    if direction == -1:
                        x_start_scaled, x_end_scaled = x_end_scaled, x_start_scaled
                        
                    start_tx, start_ty = inv_transform(x_start_scaled, y_scaled)
                    
                    # Optimización de recortes: Solo cortar hilo si el salto es mayor a 2 mm
                    if math.hypot(start_tx - last_x, start_ty - last_y) > 20:
                        pattern.add_stitch_absolute(start_tx, start_ty, pyembroidery.TRIM)
                    pattern.add_stitch_absolute(start_tx, start_ty, pyembroidery.JUMP)
                    
                    curr_x = x_start_scaled
                    step = current_stitch_length if direction == 1 else -current_stitch_length
                    
                    while (curr_x < x_end_scaled if direction == 1 else curr_x > x_end_scaled):
                        tx, ty = inv_transform(curr_x, y_scaled)
                        pattern.add_stitch_absolute(tx, ty, pyembroidery.STITCH)
                        curr_x += step
                        
                    end_tx, end_ty = inv_transform(x_end_scaled, y_scaled)
                    pattern.add_stitch_absolute(end_tx, end_ty, pyembroidery.STITCH)
                    last_x, last_y = end_tx, end_ty
                direction *= -1
                
        # --- 3) Pasada final: Contorno (Running Stitch) ---
        if add_outlines:
            # Extraer todos los contornos externos del parche de color
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            
            for contour in contours:
                # Ignorar contornos diminutos (ruido residual de la imagen)
                if cv2.contourArea(contour) < 20:
                    continue
                    
                start_pt = contour[0][0]
                sx, sy = start_pt[0] * scale, start_pt[1] * scale
                
                if math.hypot(sx - last_x, sy - last_y) > 20:
                    pattern.add_stitch_absolute(sx, sy, pyembroidery.TRIM)
                pattern.add_stitch_absolute(sx, sy, pyembroidery.JUMP)
                
                curr_x, curr_y = sx, sy
                for pt in contour[1:]:
                    nx, ny = pt[0][0] * scale, pt[0][1] * scale
                    # Avanzar por el contorno y dejar una puntada solo si nos alejamos lo suficiente
                    if math.hypot(nx - curr_x, ny - curr_y) >= stitch_length_units:
                        pattern.add_stitch_absolute(nx, ny, pyembroidery.STITCH)
                        curr_x, curr_y = nx, ny
                        
                # Puntada final para cerrar perfectamente el contorno
                pattern.add_stitch_absolute(sx, sy, pyembroidery.STITCH)
                last_x, last_y = sx, sy
                
        # Insertar cambio de color solo si no es la última capa que vamos a bordar
        if idx < len(clean_masks) - 1:
            pattern.add_stitch_absolute(last_x, last_y, pyembroidery.COLOR_CHANGE)
            
    if progress_callback:
        progress_callback(100)
        
    if output_path:
        pyembroidery.write_dst(pattern, output_path)
        
    return pattern