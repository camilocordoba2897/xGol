from django.shortcuts import redirect
from suscripciones.models import Suscripcion

def suscripcion_requerida(vista):
    def revisar(request,*args,**kwargs):

        if not request.user.is_authenticated:
            return redirect("Ingresar")

        perfil=getattr(request.user,"perfil",None)
        es_admin=request.user.is_superuser or (perfil is not None and perfil.rol is not None and perfil.rol.nombre=="administrador")
        if es_admin:
            return vista(request,*args,**kwargs)

        suscripcion,creada=Suscripcion.objects.get_or_create(usuario=request.user)

        if suscripcion.activa and not suscripcion.esta_vigente():
            suscripcion.activa=False
            suscripcion.save()

        if not suscripcion.esta_vigente():
            return redirect("Suscripcion")

        return vista(request,*args,**kwargs)

    return revisar