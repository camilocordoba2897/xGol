#Manual de usuario en el idioma elegido en el home.
#
#El manual es un solo HTML con las capturas incrustadas
#(static/manual/manual-de-usuario.html, unos 3 MB). En vez de guardar una
#copia por idioma, se traduce al servirlo: cada texto visible es un mensaje
#con contexto "manual" en los mismos .po del sitio, y "python manage.py textos"
#los extrae y compila como cualquier otro.
#
#QUE SE TRADUCE:
#  - Cada frase: el texto entre dos etiquetas de bloque (p, li, h2, div...).
#    Las etiquetas que van dentro de la frase (b, span, a...) quedan en el
#    mensaje y la traduccion las conserva tal cual.
#  - Los atributos que se leen o se oyen: alt, title, aria-label, data-cap
#    (pie de la captura ampliada), data-name/data-sec/data-group (nombre de
#    la pagina en la barra) y la descripcion de la pagina.
#  - Los pocos textos que escribe el script del manual (TEXTOS_SCRIPT).
#Las capturas son imagenes: quedan como se tomaron.
import re
from bisect import bisect_right
from functools import lru_cache

from django.conf import settings
from django.utils import translation

RUTA = settings.BASE_DIR / "static" / "manual" / "manual-de-usuario.html"
CONTEXTO = "manual"

#Etiquetas que van dentro de una frase
EN_LINEA = {"abbr", "b", "br", "code", "em", "i", "kbd", "mark", "q", "s", "small",
            "strong", "sub", "sup", "u"}
#El manual usa span y a tanto dentro de una frase como de caja (indice,
#encabezados, fichas). Van dentro de la frase solo si tienen texto pegado.
DUDOSAS = {"a", "span"}
NO_SE_TRADUCE = {"xGol"}
ATRIBUTOS = ("alt", "title", "aria-label", "data-cap", "data-name", "data-sec", "data-group")
#Textos que arma el script del manual: contador, pantalla completa y captura
TEXTOS_SCRIPT = ("Manual de usuario", "Página ", "Páginas ", " de ", " y ", "Captura ampliada",
                 "Pantalla completa (F)", "Salir de pantalla completa (F)")

#Comentario, bloque que no se toca (script, style, svg), etiqueta o texto
_TROZOS = re.compile(r"<!--.*?-->|<(script|style|svg)\b[^>]*>.*?</\1\s*>|<[^>]*>|[^<]+", re.S | re.I)
_ETIQUETA = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)")
_ATRIBUTO = re.compile(r'(\s(?:%s)=")([^"]*)(")' % "|".join(ATRIBUTOS))
_DESCRIPCION = re.compile(r'(<meta name="description" content=")([^"]*)(")')
_SCRIPT = re.compile(r"(<script\b[^>]*>)(.*?)(</script>)", re.S | re.I)
_LETRA = re.compile(r"[^\W\d_]")
_ESPACIOS = re.compile(r"\s+")
_PRECIO = re.compile(r"\$\d{1,3}(?:\.\d{3})+")
_PORCENTAJE = re.compile(r"\d %")


def _traducible(texto):
    #Con letras, y que no sea la marca ni una direccion del sitio. Los
    #precios y porcentajes tambien: en ingles van $10,000 y 70%.
    plano = re.sub(r"<[^>]*>|&\w+;", "", texto).strip()
    if _PRECIO.search(plano) or _PORCENTAJE.search(plano):
        return True
    return bool(_LETRA.search(plano)) and plano not in NO_SE_TRADUCE and not re.fullmatch(r"\S*[./]\S*", plano)


def _trozos(html):
    #[(inicio, fin, tipo, nombre)] tipo: "texto", "abre", "cierra", "vacio"
    #(svg o <br>: dentro de la frase, sin texto) o "corte" (fin de frase)
    salida = []
    for m in _TROZOS.finditer(html):
        trozo = m.group(0)
        if not trozo.startswith("<"):
            salida.append((m.start(), m.end(), "texto", ""))
            continue
        especial = (m.group(1) or "").lower()
        if especial == "svg":
            salida.append((m.start(), m.end(), "vacio", "svg"))
            continue
        etiqueta = _ETIQUETA.match(trozo)
        nombre = etiqueta.group(2).lower() if etiqueta else ""
        if especial or nombre not in EN_LINEA | DUDOSAS:
            salida.append((m.start(), m.end(), "corte", ""))
        elif nombre == "br":
            salida.append((m.start(), m.end(), "vacio", nombre))
        else:
            salida.append((m.start(), m.end(), "cierra" if etiqueta.group(1) else "abre", nombre))

    def pegado(k):
        return 0 <= k < len(salida) and salida[k][2] == "texto" and html[salida[k][0]:salida[k][1]].strip()

    #De adentro hacia afuera: una caja que contiene otra caja tambien es caja
    for k in reversed(range(len(salida))):
        inicio, fin, tipo, nombre = salida[k]
        if tipo != "abre" or nombre not in DUDOSAS:
            continue
        cierre = _pareja(salida, k, len(salida) - 1)
        caja = cierre < 0 or any(t[2] == "corte" for t in salida[k + 1:cierre])
        if caja or not (pegado(k - 1) or pegado(cierre + 1)):
            salida[k] = (inicio, fin, "corte", "")
            if cierre >= 0:
                salida[cierre] = (salida[cierre][0], salida[cierre][1], "corte", "")
    return salida


def _pareja(trozos, i, j):
    #Indice de la etiqueta que cierra a trozos[i] (o -1 si no cierra antes de j)
    nivel = 0
    for k in range(i, j + 1):
        tipo, nombre = trozos[k][2], trozos[k][3]
        if nombre != trozos[i][3]:
            continue
        if tipo == "abre":
            nivel += 1
        elif tipo == "cierra":
            nivel -= 1
            if nivel == 0:
                return k
    return -1


def _frase(html, trozos):
    #Recorta lo que rodea la frase (espacios, iconos, etiquetas que la
    #envuelven entera o que van vacias) y devuelve (inicio, fin) o None
    i, j = 0, len(trozos) - 1
    while i <= j:
        a, b = trozos[i], trozos[j]
        if a[2] == "texto" and not html[a[0]:a[1]].strip():
            i += 1
        elif b[2] == "texto" and not html[b[0]:b[1]].strip():
            j -= 1
        elif a[2] == "vacio":
            i += 1
        elif b[2] == "vacio":
            j -= 1
        elif a[2] == "abre" and _pareja(trozos, i, j) == i + 1:
            i += 2
        elif b[2] == "cierra" and j > i and trozos[j - 1][2] == "abre" and _pareja(trozos, j - 1, j) == j:
            j -= 2
        elif a[2] == "abre" and _pareja(trozos, i, j) == j:
            i += 1
            j -= 1
        else:
            break
    if i > j:
        return None
    inicio, fin = trozos[i][0], trozos[j][1]
    if trozos[i][2] == "texto":
        inicio += len(html[inicio:fin]) - len(html[inicio:fin].lstrip())
    if trozos[j][2] == "texto":
        fin -= len(html[inicio:fin]) - len(html[inicio:fin].rstrip())
    if not _traducible(html[inicio:fin]):
        return None
    return inicio, fin


def frases(html):
    #[(inicio, fin, texto)] de cada frase visible. El texto va con los
    #espacios juntados: en HTML varios espacios o saltos se ven como uno.
    salida = []
    trozos = _trozos(html)
    tramo = []
    for t in trozos + [(len(html), len(html), "corte", "")]:
        if t[2] != "corte":
            tramo.append(t)
            continue
        if tramo:
            lugar = _frase(html, tramo)
            if lugar:
                salida.append((lugar[0], lugar[1], _ESPACIOS.sub(" ", html[lugar[0]:lugar[1]])))
        tramo = []
    return salida


def _atributos(html):
    #[(inicio, fin, valor)] de los atributos visibles en etiquetas de la pagina
    salida = []
    for m in _TROZOS.finditer(html):
        trozo = m.group(0)
        if not trozo.startswith("<") or m.group(1):
            continue
        for regla in (_ATRIBUTO, _DESCRIPCION):
            for a in regla.finditer(trozo):
                if _traducible(a.group(2)):
                    salida.append((m.start() + a.start(2), m.start() + a.end(2), a.group(2)))
    return salida


def _script_del_manual(html):
    #El script propio del manual (el otro es la libreria que pasa las paginas)
    for m in _SCRIPT.finditer(html):
        if not m.group(2).lstrip().startswith("!function"):
            return m
    return None


def textos(html):
    #[(texto, linea)] para el extractor (xgol/textos.py)
    saltos = [i for i, c in enumerate(html) if c == "\n"]
    salida = [(texto, bisect_right(saltos, inicio) + 1) for inicio, _, texto in frases(html)]
    salida += [(valor, bisect_right(saltos, inicio) + 1) for inicio, _, valor in _atributos(html)]
    script = _script_del_manual(html)
    if script:
        for texto in TEXTOS_SCRIPT:
            lugar = script.group(2).find("'" + texto + "'")
            if lugar >= 0:
                salida.append((texto, bisect_right(saltos, script.start(2) + lugar) + 1))
    return salida


def _reemplazar(html, cambios):
    partes, ultimo = [], 0
    for inicio, fin, nuevo in cambios:
        partes.append(html[ultimo:inicio])
        partes.append(nuevo)
        ultimo = fin
    partes.append(html[ultimo:])
    return "".join(partes)


def traducir(html):
    #El manual en el idioma activo. Primero las frases y despues los
    #atributos: las etiquetas dentro de una frase traducida son las mismas
    #del original, asi que sus atributos se traducen en la segunda pasada.
    def t(texto):
        return translation.pgettext(CONTEXTO, texto)

    html = _reemplazar(html, [(i, f, t(texto)) for i, f, texto in frases(html)])
    html = _reemplazar(html, [(i, f, t(valor)) for i, f, valor in _atributos(html)])
    script = _script_del_manual(html)
    if script:
        codigo = script.group(2)
        for texto in TEXTOS_SCRIPT:
            nuevo = t(texto).replace("\\", "\\\\").replace("'", "\\'")
            codigo = codigo.replace("'" + texto + "'", "'" + nuevo + "'")
        html = html[:script.start(2)] + codigo + html[script.end(2):]
    idioma = translation.get_language() or settings.LANGUAGE_CODE
    region = idioma.split("-")
    lang = region[0] + ("-" + region[1].upper() if len(region) > 1 else "")
    return html.replace('<html lang="es">', f'<html lang="{lang}">', 1)


def original():
    return RUTA.read_text(encoding="utf-8")


@lru_cache(maxsize=8)
def _en_idioma(idioma, marca):
    with translation.override(idioma):
        return traducir(original())


def manual_en(idioma):
    #El español se entrega tal cual; los demas se traducen una vez por
    #proceso y quedan en memoria (marca: cambia si se edita el manual)
    if idioma == settings.LANGUAGE_CODE:
        return original()
    estado = RUTA.stat()
    return _en_idioma(idioma, (estado.st_mtime_ns, estado.st_size))
