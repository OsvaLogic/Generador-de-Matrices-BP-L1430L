import numpy as np
import pyembroidery
import math
import cv2
import os
from shapely.geometry import Polygon, LineString
from shapely.affinity import rotate

try:
    from skimage import color
    HAS_SKIMAGE = True
except ImportError:
    HAS_SKIMAGE = False

# ==========================================
# PALETAS DE COLORES
# ==========================================
BROTHER_COLORS = [
    ("Black", 0, 0, 0), ("Blue", 0, 0, 255), ("Brown", 153, 51, 0),
    ("Carmine", 204, 0, 51), ("Cyan", 0, 255, 255), ("Dark Brown", 102, 51, 0),
    ("Dark Fuchsia", 153, 0, 102), ("Dark Gray", 102, 102, 102), ("Dark Green", 0, 102, 0),
    ("Deep Gold", 255, 153, 0), ("Deep Green", 0, 153, 0), ("Deep Rose", 204, 0, 153),
    ("Flesh Pink", 255, 204, 204), ("Gold", 255, 204, 0), ("Gray", 153, 153, 153),
    ("Green", 0, 204, 0), ("Harvest Gold", 255, 153, 51), ("Khaki", 153, 153, 102),
    ("Light Blue", 153, 204, 255), ("Light Brown", 204, 153, 102), ("Light Lilac", 204, 153, 255),
    ("Lilac", 153, 102, 204), ("Magenta", 255, 0, 255), ("Mint Green", 102, 255, 153),
    ("Moss Green", 102, 153, 51), ("Navy", 0, 0, 102), ("Olive Green", 102, 102, 51),
    ("Orange", 255, 102, 0), ("Pink", 255, 102, 204), ("Purple", 102, 0, 153),
    ("Red", 255, 0, 0), ("Reddish Brown", 153, 51, 51), ("Salmon Pink", 255, 102, 102),
    ("Silver", 204, 204, 204), ("Sky Blue", 102, 153, 255), ("Teal Green", 0, 153, 153),
    ("Violet", 153, 0, 255), ("White", 255, 255, 255), ("Yellow", 255, 255, 0),
    ("Yellow Green", 153, 255, 51)
]

MADEIRA_COLORS = [
    ("Mad-Black 1000", 0, 0, 0), ("Mad-White 1001", 255, 255, 255),
    ("Mad-Red 1037", 255, 0, 0), ("Mad-Blue 1134", 0, 0, 255),
    ("Mad-Green 1051", 0, 128, 0), ("Mad-Yellow 1069", 255, 255, 0),
    ("Mad-Orange 1162", 255, 128, 0), ("Mad-Purple 1122", 128, 0, 128),
    ("Mad-Pink 1109", 255, 192, 203), ("Mad-Brown 1145", 139, 69, 19),
    ("Mad-Grey 1041", 128, 128, 128), ("Mad-Navy 1043", 0, 0, 128),
    ("Mad-Gold 1025", 255, 215, 0), ("Mad-Cyan 1094", 0, 255, 255)
]

ISACORD_COLORS = [
    ("Isa-Black 0020", 0, 0, 0), ("Isa-White 0015", 255, 255, 255),
    ("Isa-Red 1902", 255, 0, 0), ("Isa-Blue 3611", 0, 0, 255),
    ("Isa-Green 5610", 0, 128, 0), ("Isa-Yellow 0504", 255, 255, 0),
    ("Isa-Orange 1300", 255, 128, 0), ("Isa-Purple 2900", 128, 0, 128),
    ("Isa-Pink 2520", 255, 192, 203), ("Isa-Brown 0933", 139, 69, 19),
    ("Isa-Grey 0142", 128, 128, 128), ("Isa-Navy 3522", 0, 0, 128),
    ("Isa-Teal 4620", 0, 128, 128), ("Isa-Silver 0112", 192, 192, 192)
]

SULKY_COLORS = [
    ("Sulky-Black 1005", 0, 0, 0), ("Sulky-White 1001", 255, 255, 255),
    ("Sulky-Red 1147", 255, 0, 0), ("Sulky-Blue 1198", 0, 0, 255),
    ("Sulky-Green 1177", 0, 128, 0), ("Sulky-Yellow 1135", 255, 255, 0),
    ("Sulky-Orange 1168", 255, 128, 0), ("Sulky-Purple 1195", 128, 0, 128),
    ("Sulky-Pink 1115", 255, 192, 203), ("Sulky-Brown 1185", 139, 69, 19),
    ("Sulky-Grey 1218", 128, 128, 128), ("Sulky-Navy 1199", 0, 0, 128),
]

_LAB_PALETTES_CACHE = {}

def get_closest_thread_color(r, g, b, palette=None):
    if palette is None: 
        palette = BROTHER_COLORS
        
    closest_color = None
    min_dist = float('inf')
    
    if HAS_SKIMAGE:
        palette_id = id(palette)
        if palette_id not in _LAB_PALETTES_CACHE:
            lab_palette = []
            for c in palette:
                _, cr, cg, cb = c
                rgb_c = np.array([[[cr / 255.0, cg / 255.0, cb / 255.0]]], dtype=np.float32)
                lab_c = color.rgb2lab(rgb_c)
                lab_palette.append((c, lab_c))
            _LAB_PALETTES_CACHE[palette_id] = lab_palette
            
        rgb_target = np.array([[[r / 255.0, g / 255.0, b / 255.0]]], dtype=np.float32)
        lab_target = color.rgb2lab(rgb_target)
        
        for c, lab_c in _LAB_PALETTES_CACHE[palette_id]:
            dist = color.deltaE_ciede2000(lab_target, lab_c)[0][0]
            if dist < min_dist:
                min_dist = dist
                closest_color = c
    else:
        # Se utiliza una aproximación a la distancia perceptual (Fórmula Redmean)
        for c in palette:
            c_name, cr, cg, cb = c
            rmean = (r + cr) / 2.0
            dr = r - cr
            dg = g - cg
            db = b - cb
            
            dist = (2 + rmean / 256.0) * (dr ** 2) + 4.0 * (dg ** 2) + (2 + (255 - rmean) / 256.0) * (db ** 2)
            if dist < min_dist:
                min_dist = dist
                closest_color = c
    return closest_color


def _build_color_mask(bgr, alpha_mask, color, tolerance=18):
    lower = np.clip(color.astype(np.int16) - tolerance, 0, 255).astype(np.uint8)
    upper = np.clip(color.astype(np.int16) + tolerance, 0, 255).astype(np.uint8)
    mask_bgr = cv2.inRange(bgr, lower, upper)
    mask = cv2.bitwise_and(mask_bgr, alpha_mask)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
    mask = cv2.dilate(mask, kernel, iterations=1)
    return mask

# ==========================================
# MOTOR PRINCIPAL DE GENERACIÓN
# ==========================================
def generate_tatami_from_colored_image(colored_img, output_path, scale=10, add_outlines=True, progress_callback=None, palette=None):
    pattern = pyembroidery.EmbPattern()
    
    if palette is None:
        palette = BROTHER_COLORS
    
    row_spacing_units = 3       
    stitch_length_units = 20    
    pull_comp_units = 8
    last_x, last_y = 0, 0
    
    if colored_img.dtype != np.uint8:
        colored_img = colored_img.astype(np.uint8)
    
    if colored_img.shape[2] == 4:
        bgr = colored_img[:, :, :3]
        alpha = colored_img[:, :, 3]
    else:
        bgr = colored_img[:, :, :3]
        alpha = np.full((colored_img.shape[0], colored_img.shape[1]), 255, dtype=np.uint8)
    
    valid_pixels = bgr[alpha > 128]
    if len(valid_pixels) == 0:
        return pattern
        
    unique_colors, counts = np.unique(valid_pixels, axis=0, return_counts=True)
    color_freq = list(zip(unique_colors, counts))
    color_freq.sort(key=lambda x: x[1], reverse=True)
    
    _, alpha_mask = cv2.threshold(alpha, 128, 255, cv2.THRESH_BINARY)
    thread_masks = {}
    working_alpha = alpha_mask.copy()
    
    # Determinar una tolerancia segura para no fusionar colores cercanos
    main_colors = [c[0] for c in color_freq if not np.array_equal(c[0], [255, 255, 255]) and c[1] >= 10]
    safe_tolerance = 30
    if len(main_colors) > 1:
        min_c_dist = float('inf')
        for i in range(len(main_colors)):
            for j in range(i+1, len(main_colors)):
                d = np.max(np.abs(main_colors[i].astype(int) - main_colors[j].astype(int)))
                if d < min_c_dist:
                    min_c_dist = d
        if min_c_dist < 60:
            safe_tolerance = max(2, int(min_c_dist / 2) - 1)

    for color, count in color_freq:
        if np.array_equal(color, [255, 255, 255]) or count < 10:
            continue
        
        c_arr = np.array(color, dtype=np.uint8)
        mask = _build_color_mask(bgr, working_alpha, c_arr, tolerance=safe_tolerance)
        
        area = cv2.countNonZero(mask)
        if area > 15:
            name, br, bg, bb = get_closest_thread_color(color[2], color[1], color[0], palette)
            if name not in thread_masks:
                thread_masks[name] = {"rgb": (br, bg, bb), "mask": mask, "area": area}
            else:
                thread_masks[name]["mask"] = cv2.bitwise_or(thread_masks[name]["mask"], mask)
                thread_masks[name]["area"] += area
            working_alpha = cv2.bitwise_and(working_alpha, cv2.bitwise_not(mask))
            
        if cv2.countNonZero(working_alpha) == 0:
            break
            
    clean_masks = []
    for name, data in thread_masks.items():
        if data["area"] > 50:
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            clean_m = cv2.morphologyEx(data["mask"], cv2.MORPH_CLOSE, kernel, iterations=1)
            clean_masks.append((name, data["rgb"], clean_m, data["area"]))
            
    clean_masks.sort(key=lambda x: x[3], reverse=True)
    ANGLES = [0, 45, 135, 90, 15, 165, 75, 105]
    
    h, w = colored_img.shape[:2]
    diag = int(np.ceil(math.hypot(w, h)))
    pad_x = (diag - w) // 2
    pad_y = (diag - h) // 2
    cx_px, cy_px = diag / 2.0, diag / 2.0
    
    for idx, (name, (br, bg, bb), mask, area) in enumerate(clean_masks):
        if progress_callback:
            progress_callback(int((idx / len(clean_masks)) * 100))
            
        thread = pyembroidery.EmbThread()
        thread.color = (int(br) << 16) | (int(bg) << 8) | int(bb)
        thread.description = name
        pattern.add_thread(thread)
        
        padded = np.zeros((diag, diag), dtype=np.uint8)
        padded[pad_y:pad_y+h, pad_x:pad_x+w] = mask
        
        angle = ANGLES[idx % len(ANGLES)]
        M = cv2.getRotationMatrix2D((cx_px, cy_px), angle, 1.0)
        rotated_mask = cv2.warpAffine(padded, M, (diag, diag), flags=cv2.INTER_NEAREST)
        
        M_inv = cv2.getRotationMatrix2D((cx_px, cy_px), -angle, 1.0)
        
        def inv_transform(rx_scaled, ry_scaled):
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
            y_sequence = all_y[mid_idx::-1] + all_y[mid_idx+1:]
            
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
                    
                # Eliminar micromicropuntadas que ensucian el bordado
                valid_segments = [seg for seg in segments if len(seg) >= 3]
                for seg in valid_segments:
                    x_start_scaled = seg[0] * scale - current_pull_comp
                    x_end_scaled = seg[-1] * scale + current_pull_comp
                    
                    if x_start_scaled >= x_end_scaled:
                        continue
                    
                    if direction == -1:
                        x_start_scaled, x_end_scaled = x_end_scaled, x_start_scaled
                        
                    start_tx, start_ty = inv_transform(x_start_scaled, y_scaled)
                    
                    # Ejecutar el corte (TRIM) en la posición actual ANTES de saltar para evitar hilos sueltos
                    if math.hypot(start_tx - last_x, start_ty - last_y) > 20:
                        pattern.add_stitch_absolute(pyembroidery.TRIM, float(last_x), float(last_y))
                    pattern.add_stitch_absolute(pyembroidery.JUMP, float(start_tx), float(start_ty))
                    
                    curr_x = x_start_scaled
                    step = current_stitch_length if direction == 1 else -current_stitch_length
                    
                    while (curr_x < x_end_scaled if direction == 1 else curr_x > x_end_scaled):
                        tx, ty = inv_transform(curr_x, y_scaled)
                        pattern.add_stitch_absolute(pyembroidery.STITCH, float(tx), float(ty))
                        curr_x += step
                        
                    end_tx, end_ty = inv_transform(x_end_scaled, y_scaled)
                    pattern.add_stitch_absolute(pyembroidery.STITCH, float(end_tx), float(end_ty))
                    last_x, last_y = end_tx, end_ty
                direction *= -1
                
        # --- 3) Pasada final: Contorno (Running Stitch) ---
        if add_outlines:
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            
            if contours:
                ordered_contours = [contours[0]]
                remaining = list(contours[1:])
                curr_pt = contours[0][-1][0] 
                
                while remaining:
                    best_idx = 0
                    min_dist = float('inf')
                    for i, cnt in enumerate(remaining):
                        pt = cnt[0][0]
                        dist = math.hypot(pt[0] - curr_pt[0], pt[1] - curr_pt[1])
                        if dist < min_dist:
                            min_dist = dist
                            best_idx = i
                    next_cnt = remaining.pop(best_idx)
                    ordered_contours.append(next_cnt)
                    curr_pt = next_cnt[-1][0]
                    
                contours = ordered_contours

            for contour in contours:
                if cv2.contourArea(contour) < 20:
                    continue
                    
                start_pt = contour[0][0]
                sx, sy = start_pt[0] * scale, start_pt[1] * scale
                
                # Ejecutar el corte (TRIM) en la posición actual ANTES del contorno
                if math.hypot(sx - last_x, sy - last_y) > 20:
                    pattern.add_stitch_absolute(pyembroidery.TRIM, float(last_x), float(last_y))
                pattern.add_stitch_absolute(pyembroidery.JUMP, float(sx), float(sy))
                
                contour_stitches = [(sx, sy)]
                curr_x, curr_y = sx, sy
                for pt in contour[1:]:
                    nx, ny = pt[0][0] * scale, pt[0][1] * scale
                    if math.hypot(nx - curr_x, ny - curr_y) >= stitch_length_units:
                        contour_stitches.append((nx, ny))
                        curr_x, curr_y = nx, ny
                        
                contour_stitches.append((sx, sy))
                
                # --- [CORRECCIÓN] PESPUNTE DOBLE (Más limpio que el Satín) ---
                for pt in contour_stitches:
                    pattern.add_stitch_absolute(pyembroidery.STITCH, float(pt[0]), float(pt[1]))
                for pt in reversed(contour_stitches):
                    pattern.add_stitch_absolute(pyembroidery.STITCH, float(pt[0]), float(pt[1]))
                        
                last_x, last_y = sx, sy
                
        if idx < len(clean_masks) - 1:
            pattern.add_stitch_absolute(pyembroidery.COLOR_CHANGE, float(last_x), float(last_y))
            
    if progress_callback:
        progress_callback(100)
        
    if output_path:
        pyembroidery.write(pattern, output_path)
        
    return pattern

# ==========================================
# UTILIDADES EXTRA (Encoder y Tatami Base)
# ==========================================
class DSTEncoder:
    @staticmethod
    def encode_stitch(dx_mm, dy_mm, is_jump=False, is_trim=False):
        dx = int(round(dx_mm * 10))
        dy = int(round(dy_mm * 10))
        dx = max(-121, min(121, dx))
        dy = max(-121, min(121, dy))

        b1 = b2 = b3 = 0

        if dx > 0:
            b3 |= 0x04 if dx > 40 else 0; dx -= 81 if dx > 40 else 0
            b2 |= 0x04 if dx > 13 else 0; dx -= 27 if dx > 13 else 0
            b1 |= 0x04 if dx > 4  else 0; dx -= 9  if dx > 4  else 0
            b3 |= 0x01 if dx > 1  else 0; dx -= 3  if dx > 1  else 0
            b2 |= 0x01 if dx > 0  else 0
        elif dx < 0:
            dx = -dx
            b3 |= 0x08 if dx > 40 else 0; dx -= 81 if dx > 40 else 0
            b2 |= 0x08 if dx > 13 else 0; dx -= 27 if dx > 13 else 0
            b1 |= 0x08 if dx > 4  else 0; dx -= 9  if dx > 4  else 0
            b3 |= 0x02 if dx > 1  else 0; dx -= 3  if dx > 1  else 0
            b2 |= 0x02 if dx > 0  else 0

        if dy > 0:
            b3 |= 0x20 if dy > 40 else 0; dy -= 81 if dy > 40 else 0
            b2 |= 0x20 if dy > 13 else 0; dy -= 27 if dy > 13 else 0
            b1 |= 0x20 if dy > 4  else 0; dy -= 9  if dy > 4  else 0
            b3 |= 0x10 if dy > 1  else 0; dy -= 3  if dy > 1  else 0
            b2 |= 0x10 if dy > 0  else 0
        elif dy < 0:
            dy = -dy
            b3 |= 0x40 if dy > 40 else 0; dy -= 81 if dy > 40 else 0
            b2 |= 0x40 if dy > 13 else 0; dy -= 27 if dy > 13 else 0
            b1 |= 0x40 if dy > 4  else 0; dy -= 9  if dy > 4  else 0
            b3 |= 0x80 if dy > 1  else 0; dy -= 3  if dy > 1  else 0
            b2 |= 0x80 if dy > 0  else 0

        if is_jump: b3 |= 0x83 
        elif is_trim: b3 |= 0xC3 
        else: b3 |= 0x03 

        return bytes([b1, b2, b3])

def generate_tatami_fill(polygon: Polygon, angle_deg: float, row_spacing: float = 0.4, stitch_length: float = 4.0):
    rotated_poly = rotate(polygon, -angle_deg, origin='centroid')
    minx, miny, maxx, maxy = rotated_poly.bounds
    
    stitches = []
    y_coords = np.arange(miny, maxy, row_spacing)
    
    direction = 1
    row_index = 0
    
    for y in y_coords:
        scan_line = LineString([(minx - 10, y), (maxx + 10, y)])
        intersection = rotated_poly.intersection(scan_line)
        
        if intersection.is_empty:
            continue
            
        segments = intersection.geoms if hasattr(intersection, 'geoms') else [intersection]
        
        for segment in segments:
            segment_length = segment.length
            offset = (row_index % 4) * (stitch_length / 4.0)
            distances = np.arange(offset, segment_length, stitch_length)
            
            row_points = [segment.interpolate(d) for d in distances]
            if len(segment.boundary.geoms) > 1:
                row_points.append(segment.boundary.geoms[1]) 
            
            if direction == -1:
                row_points.reverse()
                
            stitches.extend([(pt.x, pt.y) for pt in row_points])
            
        direction *= -1
        row_index += 1
        
    final_path = LineString(stitches)
    final_rotated = rotate(final_path, angle_deg, origin='centroid')
    
    return list(final_rotated.coords)