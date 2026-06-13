import os
import cv2
import traceback  # <-- Importamos la librería para cazar el error
from django.shortcuts import render
from django.http import FileResponse, HttpResponseBadRequest, HttpResponse
from django.conf import settings
from django.core.files.storage import FileSystemStorage

# --- MÓDULOS DE ESCALABILIDAD (Futuro Producción) ---
# from django.contrib.auth.decorators import login_required
# from django_ratelimit.decorators import ratelimit

# Dependencias de digitalización
from .stitcher import generate_tatami_from_colored_image
from .converter import apply_auto_color_kmeans

def index_view(request):
    return render(request, 'index.html')

# @login_required(login_url='/login/') # <--- Quitar el # para proteger la app con Cuentas de Usuario
# @ratelimit(key='ip', rate='5/m', block=True) # <--- Quitar el # para evitar ataques de saturación
def digitize_view(request):
    if request.method == 'POST' and request.FILES.get('image'):
        image_file = request.FILES['image']
        
        # --- 🛡️ SEGURIDAD: 1. Limitar tamaño del archivo (Ejemplo: 5 MB máximo) ---
        max_size = 5 * 1024 * 1024
        if image_file.size > max_size:
            return HttpResponseBadRequest("El archivo es demasiado grande. El máximo permitido es 5 MB.")
            
        # --- 🛡️ SEGURIDAD: 2. Validar extensiones permitidas ---
        ext = os.path.splitext(image_file.name)[1].lower()
        valid_extensions = ['.jpg', '.jpeg', '.png', '.bmp']
        if ext not in valid_extensions:
            return HttpResponseBadRequest("Formato no soportado. Por favor sube una imagen JPG, PNG o BMP.")
            
        stitch_type = request.POST.get('stitch_type', 'tatami')
        density = int(request.POST.get('density', 10))
        
        # Forzar y validar el formato de salida a PES por defecto (Brother / Babylock)
        output_format = request.POST.get('output_format', 'pes').replace('.', '').lower()
        if output_format not in ['pes', 'dst', 'jef', 'exp']:
            output_format = 'pes'
        
        # Guardar imagen temporal
        upload_storage = FileSystemStorage(location=os.path.join(settings.MEDIA_ROOT, 'uploads'))
        filename = upload_storage.save(image_file.name, image_file)
        input_path = upload_storage.path(filename)
        
        # Configurar ruta de salida
        base_name, _ = os.path.splitext(filename)
        output_filename = f"resultado_{base_name}.{output_format}"
        output_path = os.path.join(settings.MEDIA_ROOT, 'outputs', output_filename)
        
        # Prevenir FileNotFoundError si la subcarpeta 'outputs' no existe en 'media'
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        try:
            # Procesamiento de imagen
            # Usar IA de clústeres para digitalizar colores, en lugar de solo dibujar el contorno
            colored_img = apply_auto_color_kmeans(input_path, max_colors=6)
            
            # Generar bordado
            generate_tatami_from_colored_image(
                colored_img=colored_img, 
                output_path=output_path, 
                scale=density, 
                add_outlines=True
            )
            
            # Leer el archivo generado en memoria
            with open(output_path, 'rb') as f:
                file_data = f.read()
                
            # Retornar archivo desde la memoria
            response = HttpResponse(file_data, content_type='application/octet-stream')
            response['Content-Disposition'] = f'attachment; filename="{output_filename}"'
            return response
        except Exception as e:
            # --- CÓDIGO NUEVO PARA CAZAR EL ERROR ---
            print("\n" + "!"*50)
            print("🚨 AQUÍ ESTÁ EL CULPABLE EXACTO:")
            traceback.print_exc()
            print("!"*50 + "\n")
            # ----------------------------------------
            # ----------------------------------------
            return HttpResponseBadRequest(f"Error procesando la imagen: {str(e)}")
        finally:
            # Limpieza garantizada, incluso si hay fallos
            if os.path.exists(input_path): os.remove(input_path)
            if os.path.exists(output_path): os.remove(output_path)

    return HttpResponseBadRequest("Petición inválida o imagen no adjuntada.")