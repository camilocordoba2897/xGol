#Pruebas de los partidos del home. No llaman a football-data.org: la API se
#sustituye por datos de ejemplo para que las pruebas no dependan de la red
#ni gasten el cupo de 10 peticiones por minuto.
#
#Correr con:  python manage.py test inicio
from datetime import date, timedelta
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from inicio import api_partidos


def partido(fecha, estado="TIMED", liga="PL", local="Arsenal", visitante="Chelsea"):
    return {"local": local, "visitante": visitante, "liga": liga, "liga_codigo": liga,
            "fecha": fecha, "hora": "10:00", "estado": estado, "utc": fecha + "T15:00:00Z",
            "local_logo": "", "visitante_logo": ""}


class ProximosTests(TestCase):

    def setUp(self):
        cache.clear()
        self.hoy = date.today()

    def test_semana_con_partidos_no_busca_mas(self):
        with mock.patch.object(api_partidos, "_partidos_rango",
                               return_value=[partido(self.hoy.isoformat())]) as rango:
            self.assertEqual(len(api_partidos.partidos_proximos()), 1)
        self.assertEqual(rango.call_count, 1)

    def test_paron_de_selecciones_busca_hacia_adelante(self):
        #Semana vacia (fecha FIFA): tiene que seguir buscando y parar en el
        #primer bloque de 10 dias que traiga partidos.
        lejano = (self.hoy + timedelta(days=12)).isoformat()
        respuestas = [[], [], [partido(lejano)]]
        with mock.patch.object(api_partidos, "_partidos_rango",
                               side_effect=respuestas) as rango:
            datos = api_partidos.partidos_proximos()
        self.assertEqual([p["fecha"] for p in datos], [lejano])
        self.assertEqual(rango.call_count, 3)
        #Ningun bloque pasa de 10 dias, el maximo que acepta football-data
        for llamada in rango.call_args_list[1:]:
            desde, hasta = (date.fromisoformat(x) for x in llamada.args)
            self.assertEqual((hasta - desde).days, 9)

    def test_sin_partidos_en_todo_el_rango_no_se_queda_en_bucle(self):
        with mock.patch.object(api_partidos, "_partidos_rango", return_value=[]) as rango:
            self.assertEqual(api_partidos.partidos_proximos(), [])
        self.assertLessEqual(rango.call_count, 1 + api_partidos.BUSCAR_HASTA // 10 + 1)

    def test_descarta_partidos_terminados(self):
        hoy = self.hoy.isoformat()
        with mock.patch.object(api_partidos, "_partidos_rango",
                               return_value=[partido(hoy, "FINISHED"), partido(hoy)]):
            self.assertEqual([p["estado"] for p in api_partidos.partidos_proximos()], ["TIMED"])

    def test_solo_ligas_que_cubre_el_analizador(self):
        self.assertTrue(api_partidos._cubierta({"competition": {"code": "PD"}}))
        self.assertFalse(api_partidos._cubierta({"competition": {"code": "ELC"}}))


class EquiposYTablasTests(TestCase):
    #Un fallo de la API (por ejemplo, pasarse del limite de 10 peticiones por
    #minuto) no puede dejar una liga vacia durante 24 horas.

    EQUIPOS = {"teams": [{"name": "Inter", "shortName": "Inter", "crest": "x.png"}]}

    def setUp(self):
        cache.clear()

    def test_un_fallo_no_se_guarda_por_un_dia(self):
        with mock.patch.object(api_partidos, "_pedir", return_value={}):
            self.assertEqual(api_partidos.equipos_liga("SA"), [])
        #Pasado el minuto de reintento, la liga se vuelve a pedir y aparece
        cache.delete("equipos_v2_SA")
        with mock.patch.object(api_partidos, "_pedir", return_value=self.EQUIPOS) as pedir:
            self.assertEqual(api_partidos.equipos_liga("SA")[0]["nombre"], "Inter")
        self.assertEqual(pedir.call_count, 1)

    def test_si_la_api_falla_se_usa_la_ultima_copia_buena(self):
        with mock.patch.object(api_partidos, "_pedir", return_value=self.EQUIPOS):
            api_partidos.equipos_liga("SA")
        cache.delete("equipos_v2_SA")   #vencio la cache normal
        with mock.patch.object(api_partidos, "_pedir", return_value={}):
            self.assertEqual(api_partidos.equipos_liga("SA")[0]["nombre"], "Inter")

    def test_la_respuesta_buena_se_reutiliza_sin_volver_a_pedir(self):
        with mock.patch.object(api_partidos, "_pedir", return_value=self.EQUIPOS) as pedir:
            api_partidos.equipos_liga("SA")
            api_partidos.equipos_liga("SA")
        self.assertEqual(pedir.call_count, 1)

    def test_la_tabla_tampoco_guarda_fallos(self):
        with mock.patch.object(api_partidos, "_pedir", return_value={}):
            self.assertEqual(api_partidos.tabla_posiciones("SA"), [])
        self.assertEqual(cache.get("tabla_v2_SA"), [])
        self.assertIsNone(cache.get("tabla_v2_SA_respaldo"))


class LigaNoCubiertaTests(TestCase):

    def test_codigos_inventados_no_gastan_cupo_de_la_api(self):
        with mock.patch.object(api_partidos, "_pedir") as pedir:
            for ruta in ("TablaPosiciones", "EquiposLiga"):
                self.assertEqual(self.client.get(reverse(ruta) + "?liga=XYZ").status_code, 400)
        pedir.assert_not_called()


class TarjetaDestacadaTests(TestCase):

    def setUp(self):
        cache.clear()

    def _con_partidos(self, proximos):
        with mock.patch.object(api_partidos, "partidos_vivo", return_value=[]), \
             mock.patch.object(api_partidos, "partidos_hoy", return_value=[]), \
             mock.patch.object(api_partidos, "partidos_proximos", return_value=proximos):
            return self.client.get(reverse("PrediccionesDestacadas")).json()["predicciones"]

    def test_muestra_los_proximos_sin_ningun_numero_de_pronostico(self):
        fecha = (date.today() + timedelta(days=10)).isoformat()
        datos = self._con_partidos([partido(fecha)])
        self.assertIsNone(datos["motivo"])
        tarjeta = datos["tarjetas"][0]
        self.assertEqual((tarjeta["local"], tarjeta["fecha"]), ("Arsenal", fecha))
        #Regla de oro: del servidor no sale ni un porcentaje ni goles
        #esperados. Se fija la lista exacta de campos: uno nuevo tiene que
        #pasar por aqui a proposito, no colarse.
        self.assertEqual(set(tarjeta), {"tipo", "local", "local_escudo", "visitante",
                                        "visitante_escudo", "liga", "hora", "fecha", "estado"})

    def test_sin_partidos_explica_el_motivo(self):
        self.assertEqual(self._con_partidos([])["motivo"], "sin_partidos")



class PaginasSinError500Tests(TestCase):
    #Recorre todas las paginas como visitante, como suscriptor y como
    #administrador. Ninguna puede responder 500. Las APIs externas se
    #sustituyen: esto prueba el codigo y las plantillas, no la red.

    PUBLICAS = ["Inicio", "TerminosCondiciones", "PoliticaPrivacidad", "AvisoLegal",
                "JuegoResponsable", "Registro", "Ingresar"]
    DE_USUARIO = ["Suscripcion", "EditarPerfil", "Analizador", "CargarApuestas"]
    DE_ADMIN = ["PanelAdmin", "PanelFinanzas", "AdminCrearUsuario"]

    def setUp(self):
        from datetime import date
        from allauth.socialaccount.models import SocialApp
        from django.contrib.auth.models import User
        from django.contrib.sites.models import Site
        from pagos.models import Pago
        from suscripciones.models import Suscripcion
        from usuarios.models import Perfil
        cache.clear()
        app = SocialApp.objects.create(provider="google", name="Google", client_id="x", secret="y")
        app.sites.add(Site.objects.get_current())
        self.cliente = User.objects.create_user("cliente", email="c@correo.com", password="Clave#123")
        Perfil.objects.create(usuario=self.cliente, documento="1234567",
                              fecha_nacimiento=date(1990, 1, 1), telefono="3001234567")
        Suscripcion.objects.create(usuario=self.cliente).activar("Mensual", 20000, 30)
        self.pago = Pago.objects.create(usuario=self.cliente, referencia="R1", estado="Aprobado",
                                        monto=20000, subtotal=16807, iva=3193,
                                        monto_centavos=2000000, numero_factura="FAC-00001",
                                        aplicado=True)
        self.admin = User.objects.create_superuser("jefe", email="j@correo.com", password="Clave#123")

    def revisar(self, nombres, args=None):
        for nombre in nombres:
            r = self.client.get(reverse(nombre, args=args))
            self.assertLess(r.status_code, 500, nombre)

    def test_visitante(self):
        self.revisar(self.PUBLICAS)

    def test_suscriptor(self):
        self.client.force_login(self.cliente)
        self.revisar(self.PUBLICAS + self.DE_USUARIO)
        self.revisar(["Checkout"], args=["trimestral"])
        self.revisar(["PagoConfirmado", "DescargarFactura"], args=[self.pago.id])

    def test_administrador(self):
        self.client.force_login(self.admin)
        self.revisar(self.DE_ADMIN + ["Inicio", "Analizador"])
        self.revisar(["AdminEditarUsuario", "AdminEliminarUsuario"], args=[self.cliente.id])
        for formato in ("pdf", "xlsx", "csv"):
            r = self.client.get(reverse("ExportarFinanzas") + "?formato=" + formato)
            self.assertEqual(r.status_code, 200, formato)
