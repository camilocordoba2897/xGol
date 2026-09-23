def acceso(request):
    #es_admin: la cuenta es de administracion (no compra planes ni los ve).
    #tiene_acceso: puede ver el pronostico completo (admin o plan vigente).
    #Perezosos: solo consultan la base en las plantillas que los usan, y una
    #sola vez por pagina aunque la plantilla los pregunte varias veces.
    from usuarios.roles import es_administrador, tiene_acceso
    memo = {}
    def recordar(clave, calculo):
        if clave not in memo:
            memo[clave] = calculo(request.user)
        return memo[clave]
    return {
        "es_admin": lambda: recordar("admin", es_administrador),
        "tiene_acceso": lambda: recordar("acceso", tiene_acceso),
    }


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
