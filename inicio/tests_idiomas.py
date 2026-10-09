#Pruebas de los idiomas del sitio (español, ingles, portugues y aleman).
#
#La persona elige el idioma con las banderas del home y cambia TODO el sitio.
#Estas pruebas avisan de lo que mas facil se rompe al tocar textos:
#  - un texto nuevo sin traducir, o traducido y sin compilar
#  - una traduccion que pierde una variable (%(nombre)s), un %% o una etiqueta
#    HTML: eso rompe la pagina o la deja con un hueco
#  - una pagina que en otro idioma todavia muestra frases en español
#
#Correr con:  python manage.py test inicio.tests_idiomas
import json
import re
from datetime import date
from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from inicio import manual
from xgol import textos

COOKIE = "django_language"
OTROS = ["en", "pt-br", "de"]


def _marcas(texto):
    #Variables de formato y llaves que una traduccion debe conservar
    return sorted(re.findall(r"%\([^)]+\)[sd]|%%|%[sd]|\{\w+\}", texto))


def _etiquetas(texto):
    #Las etiquetas completas, con sus atributos: deben quedar identicas
    return sorted(re.findall(r"<[^<>]+>", texto))


def _comillas_fuera_de_etiquetas(texto):
    return re.sub(r"<[^<>]+>", "", texto).count('"')


def _visible(html):
    #El HTML sin scripts ni comentarios: lo que la persona lee
    html = re.sub(r"<script\b.*?</script>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<style\b.*?</style>", " ", html, flags=re.S | re.I)
    return re.sub(r"<!--.*?-->", " ", html, flags=re.S)


class CatalogosTests(TestCase):

    def test_todo_traducido_y_compilado(self):
        informe = textos.actualizar(escribir=False)
        faltan = {idioma: {d: [c[1][:60] for c in cl] for d, cl in dom.items()}
                  for idioma, dom in informe["faltan"].items()}
        self.assertEqual(faltan, {}, "Hay textos sin traducir: corre 'python manage.py textos'")
        self.assertEqual(informe["cambios"], [], "Las traducciones no estan compiladas: corre 'python manage.py textos'")

    def test_las_traducciones_conservan_variables_html_y_comillas(self):
        for idioma, (carpeta, _) in textos.TRADUCCIONES.items():
            for dominio in textos.DOMINIOS:
                for (contexto, original, plural), traduccion in textos.leer_po(textos.ruta_po(carpeta, dominio)).items():
                    formas = traduccion if isinstance(traduccion, list) else [traduccion]
                    for forma in formas:
                        donde = f"{idioma}/{dominio}: {original[:70]!r} -> {forma[:70]!r}"
                        self.assertEqual(_marcas(forma), _marcas(original), donde)
                        self.assertEqual(_etiquetas(forma), _etiquetas(original), donde)
                        #Una comilla recta de mas rompe el texto cuando va dentro de
                        #un atributo HTML: las traducciones usan comillas tipograficas
                        self.assertLessEqual(_comillas_fuera_de_etiquetas(forma),
                                             _comillas_fuera_de_etiquetas(original), donde)

    def test_el_espanol_queda_como_esta_escrito(self):
        #Ningun texto del sitio choca con las traducciones propias de Django
        with translation.override("es"):
            for (contexto, original, plural) in list(textos.extraer()["django"])[:2000]:
                if plural is None and contexto is None:
                    self.assertEqual(translation.gettext(original), original)


class EleccionDeIdiomaTests(TestCase):

    def setUp(self):
        cache.clear()

    def test_sin_eleccion_es_espanol_aunque_el_navegador_pida_otro(self):
        r = self.client.get(reverse("Inicio"), HTTP_ACCEPT_LANGUAGE="en-US,en;q=0.9")
        self.assertEqual(r.headers["Content-Language"], "es")
        self.assertContains(r, '<html lang="es">')

    def test_la_cookie_del_selector_cambia_el_idioma(self):
        for idioma, titulo in (("en", "AI-powered soccer predictions"),
                               ("pt-br", "Previsões de futebol com Inteligência Artificial"),
                               ("de", "Fußballprognosen mit künstlicher Intelligenz")):
            self.client.cookies[COOKIE] = idioma
            r = self.client.get(reverse("Inicio"))
            self.assertEqual(r.headers["Content-Language"], idioma)
            self.assertContains(r, titulo)

    def test_un_idioma_inventado_vuelve_a_espanol(self):
        self.client.cookies[COOKIE] = "xx"
        self.assertEqual(self.client.get(reverse("Inicio")).headers["Content-Language"], "es")

    def test_el_selector_marca_la_bandera_elegida(self):
        self.client.cookies[COOKIE] = "pt-br"
        html = self.client.get(reverse("Inicio")).content.decode()
        for bandera in ("co", "us", "br", "de"):
            self.assertIn(f"img/banderas/{bandera}.svg", html)
        self.assertRegex(html, r'class="idioma-op sel"[^>]*data-idioma="pt-br"')
        self.assertIn('<span class="idioma-cod">PT</span>', html)

    def test_el_idioma_queda_guardado_en_el_perfil(self):
        #Lo usa la factura por correo, que se envia sin la persona en el sitio
        from usuarios.models import Perfil
        usuario = User.objects.create_user("ana", password="Clave#123")
        Perfil.objects.create(usuario=usuario)
        self.client.force_login(usuario)
        self.client.cookies[COOKIE] = "de"
        self.client.get(reverse("Inicio"))
        self.assertEqual(Perfil.objects.get(usuario=usuario).idioma, "de")

    def test_el_catalogo_del_javascript_sale_en_cada_idioma(self):
        for idioma, texto in (("en", "View analysis"), ("pt-br", "Ver análise"), ("de", "Analyse ansehen")):
            self.client.cookies[COOKIE] = idioma
            r = self.client.get(reverse("TextosJS") + "?idioma=" + idioma)
            self.assertEqual(r.status_code, 200)
            contenido = r.content.decode("utf-8")
            #El catalogo va en JSON: los acentos pueden venir escapados
            self.assertTrue(texto in contenido or json.dumps(texto)[1:-1] in contenido, idioma)


class FormatosTests(TestCase):

    def test_precios_con_el_separador_de_cada_pais(self):
        from pagos.templatetags.formato import pesos
        for idioma, esperado in (("es", "20.000"), ("en", "20,000"), ("pt-br", "20.000"), ("de", "20.000")):
            with translation.override(idioma):
                self.assertEqual(pesos(20000), esperado, idioma)

    def test_fechas_cortas_al_estilo_de_cada_pais(self):
        from django.utils.formats import date_format
        dia = date(2026, 10, 9)
        for idioma, esperado in (("es", "09/10/2026"), ("en", "10/09/2026"), ("pt-br", "09/10/2026"), ("de", "09.10.2026")):
            with translation.override(idioma):
                self.assertEqual(date_format(dia, "SHORT_DATE_FORMAT"), esperado, idioma)

    def test_los_numeros_siguen_con_punto_decimal(self):
        #Varias plantillas meten estos numeros en anchos y graficas
        from django.template import Context, Template
        for idioma in ["es"] + OTROS:
            with translation.override(idioma):
                self.assertEqual(Template("{{ v|floatformat:1 }}").render(Context({"v": 54.66})), "54.7", idioma)

    def test_nombres_de_las_ligas(self):
        from analizador.api_datos import nombre_liga
        with translation.override("pt-br"):
            self.assertEqual(nombre_liga("CL"), "Liga dos Campeões")
            self.assertEqual(nombre_liga("PPL"), "Primeira Liga")
        for idioma in ("es", "en", "de"):
            with translation.override(idioma):
                self.assertEqual(nombre_liga("CL"), "Champions League")
                self.assertEqual(nombre_liga("BSA"), "Brasileirão")


class DocumentosTests(TestCase):

    def setUp(self):
        from pagos.models import Pago
        from usuarios.models import Perfil
        self.usuario = User.objects.create_user("lucas", email="l@correo.com", password="Clave#123",
                                                first_name="Lucas")
        self.perfil = Perfil.objects.create(usuario=self.usuario, idioma="en")
        self.pago = Pago.objects.create(usuario=self.usuario, referencia="R9", estado="Aprobado",
                                        plan="Trimestral", monto=50000, subtotal=42017, iva=7983,
                                        monto_centavos=5000000, numero_factura="FAC-00009",
                                        aplicado=True, metodo="Tarjeta")

    def test_la_factura_por_correo_va_en_el_idioma_del_cliente(self):
        from pagos.correo import enviar_factura_correo
        for idioma, asunto, saludo in (("en", "Invoice FAC-00009 - xGol", "Thanks for your purchase"),
                                       ("pt-br", "Fatura FAC-00009 - xGol", "Obrigado pela sua compra"),
                                       ("de", "Rechnung FAC-00009 - xGol", "vielen Dank für Ihren Kauf"),
                                       ("es", "Factura FAC-00009 - xGol", "Gracias por tu compra")):
            mail.outbox = []
            self.perfil.idioma = idioma
            self.perfil.save()
            self.usuario.refresh_from_db()
            self.assertTrue(enviar_factura_correo(self.pago), idioma)
            self.assertEqual(mail.outbox[0].subject, asunto)
            self.assertIn(saludo, mail.outbox[0].body)
            self.assertTrue(mail.outbox[0].attachments[0][1].startswith(b"%PDF"))

    def test_factura_y_reportes_se_generan_en_los_cuatro_idiomas(self):
        from pagos import exportar, reporte_pdf
        from pagos.factura import generar_factura_pdf
        for idioma in ["es"] + OTROS:
            with translation.override(idioma):
                self.assertTrue(generar_factura_pdf(self.pago).getvalue().startswith(b"%PDF"), idioma)
                self.assertTrue(reporte_pdf.generar_reporte_pdf([self.pago], {"estado": "Aprobado"}).startswith(b"%PDF"))
                filas = list(exportar.filas_transacciones([self.pago]))
                self.assertTrue(exportar.a_xlsx(exportar.CABECERAS_TRANSACCIONES, filas,
                                                columnas_moneda=exportar.MONEDA_TRANSACCIONES,
                                                totalizar=exportar.TOTALIZAR_TRANSACCIONES,
                                                columna_estado=exportar.COLUMNA_ESTADO_TRANSACCIONES))
                self.assertTrue(exportar.a_csv(exportar.CABECERAS_TRANSACCIONES, filas))

    def test_el_total_del_excel_suma_lo_aprobado_en_cualquier_idioma(self):
        #El estado sale traducido en el archivo; la suma no puede depender de eso
        from pagos import exportar
        with translation.override("de"):
            filas = list(exportar.filas_transacciones([self.pago]))
            contenido = exportar.a_xlsx(exportar.CABECERAS_TRANSACCIONES, filas,
                                        columnas_moneda=exportar.MONEDA_TRANSACCIONES,
                                        totalizar=exportar.TOTALIZAR_TRANSACCIONES,
                                        columna_estado=exportar.COLUMNA_ESTADO_TRANSACCIONES)
        import io
        import zipfile
        hoja = zipfile.ZipFile(io.BytesIO(contenido)).read("xl/worksheets/sheet1.xml").decode()
        self.assertIn("GESAMT GENEHMIGT", hoja)
        self.assertIn("<v>50000</v>", hoja.split("GESAMT GENEHMIGT")[1])


class PaginasTraducidasTests(TestCase):
    #Cada pagina, en cada idioma, sin frases en español a la vista

    def setUp(self):
        from allauth.socialaccount.models import SocialApp
        from django.contrib.sites.models import Site
        from pagos.models import Pago
        from suscripciones.models import Suscripcion
        from usuarios.models import Bitacora, Perfil
        cache.clear()
        app = SocialApp.objects.create(provider="google", name="Google", client_id="x", secret="y")
        app.sites.add(Site.objects.get_current())
        self.cliente = User.objects.create_user("cliente", email="c@correo.com", password="Clave#123")
        Perfil.objects.create(usuario=self.cliente, documento="1234567",
                              fecha_nacimiento=date(1990, 1, 1), telefono="3001234567")
        Suscripcion.objects.create(usuario=self.cliente).activar("Mensual", 20000, 30)
        self.pago = Pago.objects.create(usuario=self.cliente, referencia="R1", estado="Aprobado",
                                        plan="Mensual", monto=20000, subtotal=16807, iva=3193,
                                        monto_centavos=2000000, numero_factura="FAC-00001",
                                        aplicado=True, metodo="Tarjeta")
        Bitacora.objects.create(usuario=self.cliente, accion="Inicio de sesión", ip="127.0.0.1")
        self.admin = User.objects.create_superuser("jefe", email="j@correo.com", password="Clave#123")
        #Textos en español que tienen traduccion distinta en cada idioma
        self.espanol = {}
        for idioma, (carpeta, _) in textos.TRADUCCIONES.items():
            self.espanol[idioma] = [
                original for (contexto, original, plural), t in
                textos.leer_po(textos.ruta_po(carpeta, "django")).items()
                if plural is None and isinstance(t, str) and t and t != original
                and len(original) >= 12 and "%" not in original and "<" not in original]

    def revisar(self, quien, nombres, args=None):
        for idioma in OTROS:
            self.client.cookies[COOKIE] = idioma
            for nombre in nombres:
                r = self.client.get(reverse(nombre, args=args))
                self.assertEqual(r.status_code, 200, f"{nombre} en {idioma}")
                visible = _visible(r.content.decode())
                #Frase completa (no un pedazo de otra palabra: "privacidad" esta
                #dentro de "privacidade" en portugues y no es un resto)
                restos = [t for t in self.espanol[idioma]
                          if re.search(r"(?<!\w)" + re.escape(t) + r"(?!\w)", visible)]
                self.assertEqual(restos, [], f"{quien}: {nombre} en {idioma} tiene español")

    def test_visitante(self):
        self.revisar("visitante", ["Inicio", "TerminosCondiciones", "PoliticaPrivacidad", "AvisoLegal",
                                   "JuegoResponsable", "Registro", "Ingresar", "password_reset",
                                   "password_reset_done"])

    def test_suscriptor(self):
        self.client.force_login(self.cliente)
        self.revisar("suscriptor", ["Inicio", "Suscripcion", "EditarPerfil", "Analizador"])
        self.revisar("suscriptor", ["Checkout"], args=["trimestral"])
        self.revisar("suscriptor", ["PagoConfirmado"], args=[self.pago.id])

    def test_administrador(self):
        self.client.force_login(self.admin)
        self.revisar("administrador", ["PanelAdmin", "AdminCrearUsuario", "Analizador"])
        self.revisar("administrador", ["AdminEditarUsuario", "AdminEliminarUsuario"], args=[self.cliente.id])

    def test_claves_que_lee_el_javascript_no_se_traducen(self):
        #El cuadro de confirmacion y los filtros buscan estos valores exactos:
        #si se tradujeran, cancelar una suscripcion no pediria confirmacion
        self.client.force_login(self.admin)
        for idioma in OTROS:
            self.client.cookies[COOKIE] = idioma
            r = self.client.get(reverse("PanelAdmin"))
            self.assertContains(r, 'data-confirmar="cancelar"')
            self.assertContains(r, '<option value="Aprobado"')

    def test_mensajes_y_errores_del_servidor(self):
        #El mensaje de un formulario tambien sale en el idioma elegido
        self.client.cookies[COOKIE] = "de"
        r = self.client.post(reverse("Ingresar"), {"username": "nadie", "password": "mala"})
        self.assertContains(r, "Benutzername oder Passwort falsch")
        r = self.client.post(reverse("RegistroDisponible"), {"campo": "username", "valor": "cliente"})
        self.assertEqual(r.json()["mensaje"], "Dieser Benutzername ist bereits vergeben, wählen Sie einen anderen.")


class ManualTests(TestCase):
    #El manual de usuario (static/manual) se entrega en el idioma elegido

    def manual(self, idioma):
        self.client.cookies[COOKIE] = idioma
        r = self.client.get(reverse("ManualUsuario"), {"idioma": idioma})
        self.assertEqual(r.status_code, 200)
        return r.content.decode()

    def test_el_home_abre_el_manual_del_idioma_elegido(self):
        self.client.cookies[COOKIE] = "de"
        r = self.client.get(reverse("Inicio"))
        self.assertContains(r, 'href="%s?idioma=de"' % reverse("ManualUsuario"), count=2)

    def test_en_espanol_es_el_mismo_archivo(self):
        self.assertEqual(self.manual("es"), manual.original())

    def test_en_otro_idioma_no_queda_ninguna_frase_en_espanol(self):
        original = manual.original()
        textos_originales = {t for _, _, t in manual.frases(original)}
        textos_originales |= {v for _, _, v in manual._atributos(original)}
        for idioma in OTROS:
            html = self.manual(idioma)
            with translation.override(idioma):
                cambian = {t for t in textos_originales if translation.pgettext(manual.CONTEXTO, t) != t}
            quedan = {t for _, _, t in manual.frases(html)} | {v for _, _, v in manual._atributos(html)}
            self.assertEqual(sorted(cambian & quedan), [], idioma)
            self.assertIn('<html lang="%s">' % {"en": "en", "pt-br": "pt-BR", "de": "de"}[idioma], html)

    def test_el_script_del_manual_tambien_se_traduce(self):
        html = self.manual("en")
        self.assertIn("'Enlarged screenshot'", html)
        self.assertIn("'Page ' + (a + 1) + ' of ' + TOTAL", html)
        self.assertNotIn("'Captura ampliada'", html)

    def test_los_textos_del_script_siguen_existiendo(self):
        #Si alguien edita el manual y cambia uno de estos textos, se veria en español
        script = manual._script_del_manual(manual.original()).group(2)
        for texto in manual.TEXTOS_SCRIPT:
            self.assertIn("'" + texto + "'", script)
