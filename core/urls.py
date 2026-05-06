from django.urls import path
from . import views

urlpatterns = [
    # Ruta principal -> carga index.html
    path('', views.index_view, name='index'),
    # Ruta para procesar formulario y devolver el bordado
    path('digitize/', views.digitize_view, name='digitize'),
]