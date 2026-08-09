from django.shortcuts import redirect
from django.contrib import messages

def rol_requerido(nombre_rol):
    def envoltura(vista):
        def revisar(request,*args,**kwargs):

            if not request.user.is_authenticated:
                return redirect("Ingresar")

            if request.user.is_superuser:
                return vista(request,*args,**kwargs)

            perfil=getattr(request.user,"perfil",None)

            if perfil is not None and perfil.rol is not None and perfil.rol.nombre==nombre_rol:
                return vista(request,*args,**kwargs)

            messages.error(request,"No tienes permisos para entrar a esa zona")
            return redirect("Inicio")

        return revisar
    return envoltura

