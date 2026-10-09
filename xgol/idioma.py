#Idioma del sitio. La persona lo elige UNA vez con las banderas del home
#(static/js/idioma.js guarda la eleccion en la cookie de idioma de Django) y
#desde ahi todo el sitio sale en ese idioma: paginas, mensajes, errores de
#los formularios, el analizador, los correos y los PDF.
#
#No se usa el LocaleMiddleware de Django porque ese adivina el idioma por el
#navegador: un visitante con el navegador en ingles veria el sitio en ingles
#sin haberlo pedido. Aqui, sin eleccion, siempre es español.
from pathlib import Path

from django.conf import settings
from django.utils import translation
from django.utils.cache import patch_vary_headers

IDIOMAS = [codigo for codigo, _ in settings.LANGUAGES]


def idioma_valido(codigo):
    return codigo if codigo in IDIOMAS else settings.LANGUAGE_CODE


def idioma_de_peticion(request):
    return idioma_valido(request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME, ""))


def idioma_de_usuario(usuario):
    #Para lo que se envia fuera de una visita (la factura por correo cuando
    #Wompi confirma el pago): el ultimo idioma que la persona eligio.
    perfil = getattr(usuario, "perfil", None)
    return idioma_valido(getattr(perfil, "idioma", "") or "")


class IdiomaElegido:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        idioma = idioma_de_peticion(request)
        translation.activate(idioma)
        request.LANGUAGE_CODE = idioma
        self._recordar_en_perfil(request, idioma)
        respuesta = self.get_response(request)
        #La misma direccion devuelve paginas distintas segun la cookie
        patch_vary_headers(respuesta, ("Cookie",))
        respuesta.headers.setdefault("Content-Language", idioma)
        return respuesta

    @staticmethod
    def _recordar_en_perfil(request, idioma):
        #Solo escribe cuando cambia (la sesion recuerda el ultimo guardado)
        usuario = getattr(request, "user", None)
        if not usuario or not usuario.is_authenticated:
            return
        if request.session.get("idioma_guardado") == idioma:
            return
        from usuarios.models import Perfil
        Perfil.objects.filter(usuario=usuario).update(idioma=idioma)
        request.session["idioma_guardado"] = idioma


def _version_textos():
    #Cambia cada vez que se recompilan las traducciones: asi el navegador no
    #se queda con textos viejos del catalogo de JavaScript.
    total = 0
    for mo in Path(settings.BASE_DIR, "locale").glob("*/LC_MESSAGES/*.mo"):
        datos = mo.stat()
        total += int(datos.st_mtime) + datos.st_size
    return str(total)


VERSION_TEXTOS = _version_textos()

#Las banderas del selector del home. Cada idioma lleva la bandera de su
#publico: Colombia (xGol es colombiano), Estados Unidos, Brasil y Alemania.
#El nombre y la region van en su propio idioma, como en cualquier selector.
SELECTOR = [
    {"codigo": "es", "corto": "ES", "nombre": "Español", "region": "Latinoamérica", "bandera": "co"},
    {"codigo": "en", "corto": "EN", "nombre": "English", "region": "United States", "bandera": "us"},
    {"codigo": "pt-br", "corto": "PT", "nombre": "Português", "region": "Brasil", "bandera": "br"},
    {"codigo": "de", "corto": "DE", "nombre": "Deutsch", "region": "Deutschland", "bandera": "de"},
]


def contexto(request):
    actual = translation.get_language()
    elegido = next((i for i in SELECTOR if i["codigo"] == actual), SELECTOR[0])
    return {
        "VERSION_TEXTOS": VERSION_TEXTOS,
        "IDIOMAS_SELECTOR": SELECTOR,
        "IDIOMA_ELEGIDO": elegido,
        "COOKIE_IDIOMA": settings.LANGUAGE_COOKIE_NAME,
    }
