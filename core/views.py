import os
import cv2
from django.shortcuts import render
from django.http import FileResponse, HttpResponseBadRequest, HttpResponse
from django.conf import settings
from django.core.files.storage import FileSystemStorage

# Dependencias de digitalización
from .stitcher import generate_tatami_from_colored_image
from .converter import generate_coloring_book

def index_view(request):
    return render(request, 'index.html')

def digitize_view(request):
    if request.method == 'POST' and request.FILES.get('image'):
        image_file = request.FILES['image']
        stitch_type = request.POST.get('stitch_type', 'tatami')
        density = int(request.POST.get('density', 10))
        output_format = request.POST.get('output_format', 'dst')
        
        # Guardar imagen temporal
        upload_storage = FileSystemStorage(location=os.path.join(settings.MEDIA_ROOT, 'uploads'))
        filename = upload_storage.save(image_file.name, image_file)
        input_path = upload_storage.path(filename)
        
        # Configurar ruta de salida
        output_filename = f"resultado_{filename.split('.')[0]}.{output_format}"
        output_path = os.path.join(settings.MEDIA_ROOT, 'outputs', output_filename)
        
        try:
            # Procesamiento de imagen
            colored_img = generate_coloring_book(input_path)
            
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
                
            # Limpieza: Eliminar archivos físicos para no llenar el disco del servidor
            if os.path.exists(input_path): os.remove(input_path)
            if os.path.exists(output_path): os.remove(output_path)
            
            # Retornar archivo desde la memoria
            response = HttpResponse(file_data, content_type='application/octet-stream')
            response['Content-Disposition'] = f'attachment; filename="{output_filename}"'
            return response
        except Exception as e:
            return HttpResponseBadRequest(f"Error procesando la imagen: {str(e)}")

    return HttpResponseBadRequest("Petición inválida o imagen no adjuntada.")