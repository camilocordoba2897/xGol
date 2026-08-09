from usuarios.models import Perfil

def rol_actual(request):
    if request.user.is_authenticated:
        perfil=Perfil.objects.filter(usuario=request.user).first()
        if perfil is not None and perfil.rol is not None:
            return {"rol_actual": perfil.rol.nombre}
    return {"rol_actual": None}