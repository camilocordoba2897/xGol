"""
URL configuration for xgol project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django.templatetags.static import static as ruta_estatica
from usuarios.views import PedirEnlaceContrasena, RestablecerContrasena

urlpatterns = [
    path('admin/', admin.site.urls),
    #Los navegadores piden /favicon.ico por su cuenta aunque la pagina declare
    #otro icono: sin esto cada visita dejaba un 404 en el registro.
    path('favicon.ico', RedirectView.as_view(url=ruta_estatica('img/favicon.ico'), permanent=True)),
    #Esta ruta va ANTES del include: sustituye la vista de Django por la
    #misma con nuestro formulario, para que el cambio de contraseña por
    #correo exija las mismas reglas que el registro. El name se conserva
    #para que el enlace del correo y los {% url %} sigan funcionando.
    path('cuenta/reset/<uidb64>/<token>/', RestablecerContrasena.as_view(),
         name='password_reset_confirm'),
    #Con tope de solicitudes: ver PedirEnlaceContrasena
    path('cuenta/password_reset/', PedirEnlaceContrasena.as_view(),
         name='password_reset'),
    path('cuenta/', include("django.contrib.auth.urls")),
    path('social/', include("allauth.urls")),
    path('', include("inicio.urls")),
    path('', include('usuarios.urls')),
    path('', include("analizador.urls")),
    path('', include("suscripciones.urls")),
    path('', include("pagos.urls")),
]
