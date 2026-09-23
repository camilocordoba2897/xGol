from django.shortcuts import redirect
from suscripciones.models import Suscripcion
from usuarios.roles import es_administrador

def suscripcion_requerida(vista):
    def revisar(request,*args,**kwargs):

        if not request.user.is_authenticated:
            return redirect("Ingresar")

        #El administrador entra siempre: no compra planes
        if es_administrador(request.user):
            return vista(request,*args,**kwargs)

        suscripcion,creada=Suscripcion.objects.get_or_create(usuario=request.user)

        if suscripcion.activa and not suscripcion.esta_vigente():
            suscripcion.activa=False
            suscripcion.save()

        if not suscripcion.esta_vigente():
            return redirect("Suscripcion")

        return vista(request,*args,**kwargs)

    return revisar