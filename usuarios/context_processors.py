from usuarios.models import Perfil

def rol_actual(request):
    if request.user.is_authenticated:
        perfil=Perfil.objects.filter(usuario=request.user).first()
        if perfil is not None and perfil.rol is not None:
            return {"rol_actual": perfil.rol.nombre}
    return {"rol_actual": None}


def google_disponible(request):
    #El boton de Google solo se pinta si la app de Google esta configurada.
    #Sin esto, si faltara (base nueva, o alguien la borra en el admin de
    #Django), las paginas de Ingresar y Registro daban error 500 y nadie
    #podia entrar al sitio.
    def disponible():
        try:
            from allauth.socialaccount.adapter import get_adapter
            return bool(get_adapter().list_apps(request, provider="google"))
        except Exception:
            return False
    #Perezoso: solo consulta la base en las plantillas que lo usan
    return {"google_disponible": disponible}
