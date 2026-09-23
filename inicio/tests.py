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
