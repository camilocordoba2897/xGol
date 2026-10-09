#Textos traducibles del proyecto: los saca del codigo, mantiene al dia los
#archivos de traduccion (locale/<idioma>/LC_MESSAGES/*.po) y los compila
#(.mo), que es lo que Django lee.
#
#Hace lo mismo que "makemessages" y "compilemessages" de Django, pero en
#Python puro: esos dos comandos necesitan el programa gettext instalado, y
#en Windows no viene. Se usa con:
#
#    python manage.py textos            extrae, actualiza los .po y compila
#    python manage.py textos --revisar  solo revisa (no escribe nada)
#
#DE DONDE SALEN LOS TEXTOS (el texto original siempre en español):
#  - Plantillas:  {% translate "..." %} y {% blocktranslate %}. Se leen con
#    el mismo convertidor que usa Django (templatize), asi que el texto que
#    se guarda es exactamente el que Django busca al pintar la pagina.
#  - Python:      gettext("..."), gettext_lazy, ngettext, pgettext...
#  - JavaScript:  gettext('...'), ngettext(...), pgettext(...) en static/js
#    y en los <script> de las plantillas. El texto tiene que ir escrito tal
#    cual dentro de la llamada (sin sumar pedazos), o no se puede extraer.
#  - Manual:      las frases de static/manual/manual-de-usuario.html, con
#    contexto "manual" (ver inicio/manual.py).
import ast
import re
import struct
from pathlib import Path

from django.conf import settings
from django.utils.translation.template import templatize

RAIZ = Path(settings.BASE_DIR)
APPS = ["inicio", "usuarios", "analizador", "suscripciones", "pagos", "xgol"]
CARPETAS_PLANTILLAS = [RAIZ / "templates"] + [RAIZ / app / "templates" for app in APPS]
CARPETA_JS = RAIZ / "static" / "js"
CARPETA_LOCALE = RAIZ / "locale"

#Idioma -> carpeta de locale y regla de plurales (la misma de Django)
TRADUCCIONES = {
    "en": ("en", "nplurals=2; plural=(n != 1);"),
    "pt-br": ("pt_BR", "nplurals=2; plural=(n > 1);"),
    "de": ("de", "nplurals=2; plural=(n != 1);"),
}
DOMINIOS = ("django", "djangojs")

FUNCIONES = {
    "gettext": "s", "gettext_lazy": "s", "gettext_noop": "s", "_": "s",
    "ngettext": "p", "ngettext_lazy": "p",
    "pgettext": "c", "pgettext_lazy": "c",
    "npgettext": "cp", "npgettext_lazy": "cp",
}


class TextoNoExtraible(Exception):
    pass


def _clave(tipo, args):
    #(contexto, texto, plural)
    if tipo == "s":
        return (None, args[0], None)
    if tipo == "p":
        return (None, args[0], args[1])
    if tipo == "c":
        return (args[0], args[1], None)
    return (args[0], args[1], args[2])


def _cuantos(tipo):
    return {"s": 1, "p": 2, "c": 2, "cp": 3}[tipo]


# ------------------------------------------------------------
#  EXTRACCION
# ------------------------------------------------------------
def _textos_python(codigo, archivo):
    salida = []
    for nodo in ast.walk(ast.parse(codigo, filename=str(archivo))):
        if not isinstance(nodo, ast.Call):
            continue
        f = nodo.func
        nombre = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
        if nombre not in FUNCIONES:
            continue
        tipo = FUNCIONES[nombre]
        args = nodo.args[:_cuantos(tipo)]
        if len(args) < _cuantos(tipo) or not all(
                isinstance(a, ast.Constant) and isinstance(a.value, str) for a in args):
            #Con una variable (gettext(nombre_guardado)) el texto se traduce
            #al pintarlo; su texto original se marca donde se escribe.
            continue
        salida.append((_clave(tipo, [a.value for a in args]), nodo.lineno))
    return salida


_LLAMADA = re.compile(r"(?<![\w.$])(gettext|ngettext|pgettext|npgettext)\s*\(")


def _fin_de_llamada(texto, i):
    #Posicion del parentesis que cierra la llamada que abre en texto[i]
    nivel, comilla = 0, None
    while i < len(texto):
        c = texto[i]
        if comilla:
            if c == "\\":
                i += 1
            elif c == comilla:
                comilla = None
        elif c in "'\"`":
            comilla = c
        elif c == "(":
            nivel += 1
        elif c == ")":
            nivel -= 1
            if nivel == 0:
                return i
        i += 1
    return -1


def _textos_templatize(codigo):
    #templatize deja las llamadas como codigo Python: gettext(u'...')
    salida = []
    for m in _LLAMADA.finditer(codigo):
        fin = _fin_de_llamada(codigo, m.end() - 1)
        llamada = ast.parse(codigo[m.start():fin + 1], mode="eval").body
        tipo = FUNCIONES[m.group(1)]
        args = [a.value for a in llamada.args if isinstance(a, ast.Constant)][:_cuantos(tipo)]
        if len(args) < _cuantos(tipo):
            continue        # {% translate variable %}: se traduce al pintar
        salida.append((_clave(tipo, args), codigo.count("\n", 0, m.start()) + 1))
    return salida


_ESCAPES_JS = {"n": "\n", "t": "\t", "r": "\r", "'": "'", '"': '"', "\\": "\\", "/": "/", "`": "`"}


def _cadena_js(texto, i):
    #Lee una cadena de JavaScript que empieza en texto[i]; devuelve (valor, fin)
    comilla = texto[i]
    i += 1
    valor = []
    while i < len(texto):
        c = texto[i]
        if c == "\\":
            sig = texto[i + 1]
            if sig == "u":
                valor.append(chr(int(texto[i + 2:i + 6], 16)))
                i += 6
                continue
            if sig == "x":
                valor.append(chr(int(texto[i + 2:i + 4], 16)))
                i += 4
                continue
            valor.append(_ESCAPES_JS.get(sig, sig))
            i += 2
            continue
        if c == comilla:
            return "".join(valor), i + 1
        if comilla == "`" and texto.startswith("${", i):
            raise ValueError("plantilla con ${}")
        valor.append(c)
        i += 1
    raise ValueError("cadena sin cerrar")


def _textos_js(codigo, archivo, desde_linea=0):
    salida = []
    for m in _LLAMADA.finditer(codigo):
        tipo = FUNCIONES[m.group(1)]
        linea = desde_linea + codigo.count("\n", 0, m.start()) + 1
        i, args = m.end(), []
        try:
            while len(args) < _cuantos(tipo):
                while codigo[i].isspace():
                    i += 1
                if codigo[i] not in "'\"`":
                    if not args and (codigo[i].isalpha() or codigo[i] in "_$"):
                        break       # gettext(variable): se traduce al pintar
                    raise ValueError("no es un texto")
                valor, i = _cadena_js(codigo, i)
                while codigo[i].isspace():
                    i += 1
                if codigo[i] not in ",)":
                    raise ValueError("texto armado con pedazos")
                args.append(valor)
                if codigo[i] == ")":
                    break
                i += 1
        except (ValueError, IndexError) as e:
            raise TextoNoExtraible(f"{archivo}:{linea}: {m.group(1)}() {e}: el texto va escrito tal cual")
        if not args:
            continue
        if len(args) < _cuantos(tipo):
            raise TextoNoExtraible(f"{archivo}:{linea}: a {m.group(1)}() le faltan textos")
        salida.append((_clave(tipo, args), linea))
    return salida


_SCRIPT = re.compile(r"<script\b[^>]*>(.*?)</script>", re.S | re.I)


def archivos_plantillas():
    for carpeta in CARPETAS_PLANTILLAS:
        if carpeta.is_dir():
            yield from sorted(carpeta.rglob("*.html"))
            yield from sorted(carpeta.rglob("*.txt"))


def archivos_python():
    for app in APPS:
        for archivo in sorted((RAIZ / app).rglob("*.py")):
            partes = set(archivo.relative_to(RAIZ).parts)
            if "migrations" in partes or archivo.name in ("tests.py", "textos.py", "settings.py"):
                continue
            yield archivo


def archivos_js():
    yield from sorted(CARPETA_JS.glob("*.js"))


def extraer():
    #{dominio: {clave: [lugares]}} en el orden en que aparecen
    textos = {d: {} for d in DOMINIOS}

    def anotar(dominio, archivo, encontrados):
        relativo = archivo.relative_to(RAIZ).as_posix()
        for clave, linea in encontrados:
            textos[dominio].setdefault(clave, []).append(f"{relativo}:{linea}")

    for archivo in archivos_plantillas():
        codigo = archivo.read_text(encoding="utf-8-sig")
        anotar("django", archivo, _textos_templatize(templatize(codigo, origin=str(archivo))))
        for m in _SCRIPT.finditer(codigo):
            anotar("djangojs", archivo, _textos_js(m.group(1), archivo, codigo.count("\n", 0, m.start(1))))
    for archivo in archivos_python():
        anotar("django", archivo, _textos_python(archivo.read_text(encoding="utf-8-sig"), archivo))
    for archivo in archivos_js():
        anotar("djangojs", archivo, _textos_js(archivo.read_text(encoding="utf-8-sig"), archivo))
    from inicio import manual
    anotar("django", manual.RUTA, [((manual.CONTEXTO, texto, None), linea)
                                   for texto, linea in manual.textos(manual.original())])
    return textos


# ------------------------------------------------------------
#  ARCHIVOS .po
# ------------------------------------------------------------
def _po_cadena(texto):
    texto = (texto.replace("\\", "\\\\").replace('"', '\\"')
             .replace("\t", "\\t").replace("\r", "\\r").replace("\n", "\\n"))
    return f'"{texto}"'


def leer_po(ruta):
    #{clave: traduccion} (traduccion: texto, o lista de 2 textos si es plural).
    #Las marcadas "fuzzy" (dudosas) cuentan como sin traducir.
    entradas = {}
    if not ruta.exists():
        return entradas
    for bloque in re.split(r"\n\s*\n", ruta.read_text(encoding="utf-8")):
        campos, campo, dudosa = {}, None, False
        for linea in bloque.splitlines():
            linea = linea.strip()
            if linea.startswith("#,") and "fuzzy" in linea:
                dudosa = True
            if not linea or linea.startswith("#"):
                continue
            if linea.startswith('"'):
                if campo:
                    campos[campo] += ast.literal_eval(linea)
                continue
            campo, _, resto = linea.partition(" ")
            campos[campo] = ast.literal_eval(resto)
        if not campos.get("msgid"):
            continue
        clave = (campos.get("msgctxt"), campos["msgid"], campos.get("msgid_plural"))
        if clave[2] is None:
            entradas[clave] = "" if dudosa else campos.get("msgstr", "")
        else:
            entradas[clave] = ["", ""] if dudosa else [campos.get(f"msgstr[{i}]", "") for i in range(2)]
    return entradas


def _escribir_po(ruta, idioma, regla, claves, lugares, traducciones):
    lineas = [
        "# Traducciones de xGol. El texto original (msgid) es el español del sitio.",
        "# Se actualiza con: python manage.py textos",
        'msgid ""',
        'msgstr ""',
        '"Project-Id-Version: xGol\\n"',
        f'"Language: {idioma}\\n"',
        '"MIME-Version: 1.0\\n"',
        '"Content-Type: text/plain; charset=UTF-8\\n"',
        '"Content-Transfer-Encoding: 8bit\\n"',
        f'"Plural-Forms: {regla}\\n"',
        "",
    ]
    for clave in claves:
        contexto, texto, plural = clave
        lineas.append("#: " + " ".join(lugares[clave][:3]))
        if "%(" in texto or (plural and "%(" in plural):
            lineas.append("#, python-format")
        if contexto is not None:
            lineas.append("msgctxt " + _po_cadena(contexto))
        lineas.append("msgid " + _po_cadena(texto))
        traduccion = traducciones.get(clave)
        if plural is None:
            lineas.append("msgstr " + _po_cadena(traduccion if isinstance(traduccion, str) else ""))
        else:
            lineas.append("msgid_plural " + _po_cadena(plural))
            formas = traduccion if isinstance(traduccion, list) else []
            for i in range(2):
                lineas.append(f"msgstr[{i}] " + _po_cadena(formas[i] if i < len(formas) else ""))
        lineas.append("")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    contenido = "\n".join(lineas)
    if not ruta.exists() or ruta.read_text(encoding="utf-8") != contenido:
        ruta.write_text(contenido, encoding="utf-8", newline="\n")
        return True
    return False


# ------------------------------------------------------------
#  ARCHIVOS .mo (lo que lee Django)
# ------------------------------------------------------------
def compilar_mo(idioma, regla, traducciones):
    #Formato GNU gettext: cabecera, tabla de originales, tabla de
    #traducciones y los textos terminados en \0. Solo entra lo traducido;
    #lo que falte se queda en español.
    pares = {"": (f"Content-Type: text/plain; charset=UTF-8\n"
                  f"Language: {idioma}\nPlural-Forms: {regla}\n")}
    for (contexto, texto, plural), traduccion in traducciones.items():
        if plural is None:
            if not traduccion:
                continue
            original, valor = texto, traduccion
        else:
            if not traduccion or not all(traduccion):
                continue
            original, valor = texto + "\0" + plural, "\0".join(traduccion)
        if contexto is not None:
            original = contexto + "\x04" + original
        pares[original] = valor
    claves = sorted(pares, key=lambda k: k.encode("utf-8"))
    originales = [k.encode("utf-8") for k in claves]
    valores = [pares[k].encode("utf-8") for k in claves]
    n = len(claves)
    inicio_tablas = 7 * 4
    inicio_textos = inicio_tablas + n * 16
    tabla_o, tabla_v, textos = [], [], b""
    for o in originales:
        tabla_o.append((len(o), inicio_textos + len(textos)))
        textos += o + b"\0"
    for v in valores:
        tabla_v.append((len(v), inicio_textos + len(textos)))
        textos += v + b"\0"
    salida = struct.pack("<7I", 0x950412DE, 0, n, inicio_tablas, inicio_tablas + n * 8, 0, 0)
    for largo, pos in tabla_o + tabla_v:
        salida += struct.pack("<2I", largo, pos)
    return salida + textos


def ruta_po(carpeta, dominio):
    return CARPETA_LOCALE / carpeta / "LC_MESSAGES" / f"{dominio}.po"


# ------------------------------------------------------------
#  CHOQUES CON LAS TRADUCCIONES PROPIAS DE DJANGO
# ------------------------------------------------------------
def choques_en_espanol(textos):
    #Los textos del sitio estan en español y Django trae sus propias
    #traducciones al español (de textos en ingles). Si un texto nuestro
    #coincidiera con uno ingles de Django ("No", "Total"...), en español
    #saldria la version de Django. Esos pocos se guardan tal cual en
    #locale/es para que el español quede siempre como esta escrito.
    from django.test.utils import override_settings
    from django.utils.translation.trans_real import DjangoTranslation
    choques = {}
    with override_settings(LOCALE_PATHS=[]):
        for dominio, claves in textos.items():
            t = DjangoTranslation("es", domain=dominio)
            for clave in claves:
                contexto, texto, plural = clave
                if plural is None:
                    obtenido = t.pgettext(contexto, texto) if contexto else t.gettext(texto)
                    if obtenido != texto:
                        choques.setdefault(dominio, {})[clave] = texto
                else:
                    if t.ngettext(texto, plural, 1) != texto or t.ngettext(texto, plural, 2) != plural:
                        choques.setdefault(dominio, {})[clave] = [texto, plural]
    return choques


# ------------------------------------------------------------
#  TODO JUNTO
# ------------------------------------------------------------
def actualizar(escribir=True):
    #Devuelve un informe: {"faltan": {idioma: {dominio: [claves]}}, "cambios": [...]}
    textos = extraer()
    informe = {"faltan": {}, "cambios": [], "textos": textos}
    choques = choques_en_espanol(textos)
    trabajos = [(idioma, carpeta, regla) for idioma, (carpeta, regla) in TRADUCCIONES.items()]
    trabajos.append(("es", "es", "nplurals=2; plural=(n != 1);"))
    for idioma, carpeta, regla in trabajos:
        for dominio in DOMINIOS:
            if idioma == "es":
                claves = list(choques.get(dominio, {}))
                traducciones = choques.get(dominio, {})
            else:
                claves = list(textos[dominio])
                anteriores = leer_po(ruta_po(carpeta, dominio))
                traducciones = {c: anteriores.get(c) for c in claves}
                faltan = [c for c in claves if not traducciones[c]
                          or (isinstance(traducciones[c], list) and not all(traducciones[c]))]
                if faltan:
                    informe["faltan"].setdefault(idioma, {})[dominio] = faltan
            po, mo = ruta_po(carpeta, dominio), ruta_po(carpeta, dominio).with_suffix(".mo")
            if not claves:
                for viejo in (po, mo):
                    if viejo.exists():
                        informe["cambios"].append(str(viejo.relative_to(RAIZ)))
                        if escribir:
                            viejo.unlink()
                continue
            lugares = {c: textos[dominio].get(c, ["?"]) for c in claves}
            binario = compilar_mo(idioma, regla, traducciones)
            if escribir:
                if _escribir_po(po, idioma, regla, claves, lugares, traducciones):
                    informe["cambios"].append(str(po.relative_to(RAIZ)))
                if not mo.exists() or mo.read_bytes() != binario:
                    mo.write_bytes(binario)
                    informe["cambios"].append(str(mo.relative_to(RAIZ)))
            else:
                if not mo.exists() or mo.read_bytes() != binario:
                    informe["cambios"].append(str(mo.relative_to(RAIZ)))
    return informe
