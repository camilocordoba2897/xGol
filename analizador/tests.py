#Pruebas del motor de prediccion y de las rutas del analizador.
#
#Correr con:  python manage.py test analizador
import json

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from analizador.models import RegistroApuesta
from analizador.motor import combinacion, elo, mercado, probabilidad as pr
from usuarios.models import Perfil


class ProbabilidadTests(SimpleTestCase):

    def setUp(self):
        self.m = pr.matriz_marcadores(1.8, 0.9)

    def test_la_matriz_suma_uno(self):
        self.assertAlmostEqual(sum(sum(f) for f in self.m), 1.0, places=9)

    def test_mercados_complementarios_suman_uno(self):
        self.assertAlmostEqual(sum(pr.resultado_1x2(self.m).values()), 1.0, places=9)
        for linea in (0.5, 1.5, 2.5, 3.5):
            t = pr.total_goles(self.m, linea)
            self.assertAlmostEqual(t["mas"] + t["menos"], 1.0, places=9)
        self.assertAlmostEqual(sum(pr.ambos_marcan(self.m).values()), 1.0, places=9)

    def test_el_equipo_con_mas_goles_esperados_es_favorito(self):
        r = pr.resultado_1x2(self.m)
        self.assertGreater(r["local"], r["visitante"])
        r = pr.resultado_1x2(pr.matriz_marcadores(0.9, 1.8))
        self.assertGreater(r["visitante"], r["local"])

    def test_doble_oportunidad_cuadra_con_el_1x2(self):
        r = pr.resultado_1x2(self.m)
        d = pr.doble_oportunidad(self.m)
        self.assertAlmostEqual(sum(d.values()), 2.0, places=9)
        self.assertAlmostEqual(max(d.values()), r["local"] + r["empate"], places=9)

    def test_recupera_los_goles_esperados(self):
        lam1, lam2 = pr.lambdas_de_matriz(pr.matriz_marcadores(1.8, 0.9, rho=0.0))
        self.assertAlmostEqual(lam1, 1.8, places=2)
        self.assertAlmostEqual(lam2, 0.9, places=2)

    def test_cuota_valor_y_kelly(self):
        self.assertAlmostEqual(pr.cuota_justa(0.5), 2.0)
        self.assertAlmostEqual(pr.valor_esperado(0.5, 2.0), 0.0)
        self.assertGreater(pr.valor_esperado(0.6, 2.0), 0)
        #Apuesta sin valor: Kelly nunca recomienda poner dinero
        self.assertEqual(pr.kelly(0.4, 2.0), 0.0)
        self.assertGreater(pr.kelly(0.6, 2.0), 0.0)


class MercadoYCombinacionTests(SimpleTestCase):

    def test_quitar_el_margen_de_la_casa(self):
        cuotas = [2.10, 3.40, 3.60]
        self.assertGreater(mercado.margen(cuotas), 1.0)
        for metodo in (mercado.sin_margen_proporcional, mercado.sin_margen_potencia):
            self.assertAlmostEqual(sum(metodo(cuotas)), 1.0, places=6)

    def test_cuota_invalida(self):
        with self.assertRaises(ValueError):
            mercado.margen([1.0, 3.0, 4.0])

    def test_pesos_normalizados(self):
        self.assertAlmostEqual(sum(combinacion.normalizar({"a": 2, "b": 6}).values()), 1.0)
        self.assertEqual(combinacion.normalizar({"a": 0, "b": 0}), {"a": 0.5, "b": 0.5})

    def test_mezcla_ignora_fuentes_ausentes(self):
        p = {"local": 0.5, "empate": 0.3, "visitante": 0.2}
        mezcla = combinacion.mezclar_probabilidades({"mercado": p, "elo": None},
                                                    {"mercado": 0.5, "elo": 0.5})
        for k in p:
            self.assertAlmostEqual(mezcla[k], p[k])
        self.assertIsNone(combinacion.mezclar_probabilidades({"elo": None}, {"elo": 1}))


class EloTests(SimpleTestCase):

    def test_el_ganador_sube_y_el_perdedor_baja(self):
        t = elo.calcular([{"local": "A", "visitante": "B", "goles_local": 3, "goles_visitante": 0}])
        self.assertGreater(t.ratings["a"], elo.ELO_INICIAL)
        self.assertLess(t.ratings["b"], elo.ELO_INICIAL)
        #Elo es de suma cero: lo que gana uno lo pierde el otro
        self.assertAlmostEqual(t.ratings["a"] + t.ratings["b"], 2 * elo.ELO_INICIAL)

    def test_ignora_filas_rotas(self):
        t = elo.calcular([{"local": "A", "visitante": "A", "goles_local": 1, "goles_visitante": 0},
                          {"local": "A", "visitante": "B", "goles_local": "x", "goles_visitante": 0}])
        self.assertEqual(t.ratings, {})


class AccesoAnalizadorTests(TestCase):
    #Cada ruta que entrega pronosticos o datos de pago exige suscripcion.
    RUTAS_DE_PAGO = ("Analizador", "AutoPartidos", "AutoEnfrentamiento", "AutoResultados",
                     "AutoCuotas", "MotorPronostico", "MotorFuerzas", "MotorRendimiento")

    def setUp(self):
        self.usuario = User.objects.create_user(username="ana", password="Clave#123")
        Perfil.objects.create(usuario=self.usuario)

    def test_anonimo_no_entra(self):
        for nombre in self.RUTAS_DE_PAGO:
            r = self.client.get(reverse(nombre))
            self.assertEqual(r.status_code, 302, nombre)
            self.assertIn(reverse("Ingresar"), r["Location"], nombre)

    def test_sin_suscripcion_no_entra(self):
        self.client.force_login(self.usuario)
        for nombre in self.RUTAS_DE_PAGO:
            r = self.client.get(reverse(nombre))
            self.assertEqual(r.status_code, 302, nombre)
            self.assertIn(reverse("Suscripcion"), r["Location"], nombre)

    def test_solo_el_administrador_modifica_la_biblioteca(self):
        self.client.force_login(self.usuario)
        r = self.client.post(reverse("GuardarBiblioteca"), json.dumps({"teamLibrary": {}}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 403)


class ApuestasTests(TestCase):

    def setUp(self):
        self.ana = User.objects.create_user(username="ana", password="Clave#123")
        self.luis = User.objects.create_user(username="luis", password="Clave#123")

    def guardar(self, usuario, etiqueta):
        self.client.force_login(usuario)
        cuerpo = {"betLog": [{"ts": 1, "team1": "A", "team2": "B", "label": etiqueta,
                              "prob": "0.61", "odds": "abc"}], "betLogMeta": {}}
        return self.client.post(reverse("GuardarApuestas"), json.dumps(cuerpo),
                                content_type="application/json")

    def test_cada_usuario_ve_solo_sus_apuestas(self):
        self.guardar(self.ana, "de Ana")
        self.guardar(self.luis, "de Luis")
        self.client.force_login(self.ana)
        etiquetas = [a["label"] for a in self.client.get(reverse("CargarApuestas")).json()["betLog"]]
        self.assertEqual(etiquetas, ["de Ana"])

    def test_datos_raros_no_rompen_el_guardado(self):
        self.assertEqual(self.guardar(self.ana, "x").status_code, 200)
        a = RegistroApuesta.objects.get(usuario=self.ana)
        self.assertAlmostEqual(a.probabilidad, 0.61)
        self.assertIsNone(a.cuota)

    def test_json_invalido(self):
        self.client.force_login(self.ana)
        r = self.client.post(reverse("GuardarApuestas"), "{no es json",
                             content_type="application/json")
        self.assertEqual(r.status_code, 400)



class BibliotecaYLigasTests(TestCase):

    def setUp(self):
        self.usuario = User.objects.create_user(username="ana", password="Clave#123")
        Perfil.objects.create(usuario=self.usuario)
        self.client.force_login(self.usuario)

    def test_la_biblioteca_compartida_exige_suscripcion(self):
        r = self.client.get(reverse("CargarBiblioteca"))
        self.assertIn(reverse("Suscripcion"), r["Location"])

    def test_apuestas_con_forma_rara_responden_400(self):
        for cuerpo in ([1, 2], {"betLog": "x"}, {"betLog": [], "betLogMeta": []}):
            r = self.client.post(reverse("GuardarApuestas"), json.dumps(cuerpo),
                                 content_type="application/json")
            self.assertEqual(r.status_code, 400, cuerpo)

    def test_motor_rechaza_ligas_que_no_cubre(self):
        from suscripciones.models import Suscripcion
        Suscripcion.objects.create(usuario=self.usuario).activar("Mensual", 20000, 30)
        r = self.client.get(reverse("MotorPronostico") + "?liga=XYZ&local=A&visitante=B")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["error"], "liga_no_cubierta")


class EvaluacionHonestaTests(TestCase):
    #Un pronostico guardado despues del saque no puede contar en las metricas

    def test_descarta_pronosticos_guardados_despues_del_saque(self):
        from io import StringIO
        from unittest import mock
        from django.core.management import call_command
        from analizador.models import PrediccionMotor
        p = PrediccionMotor.objects.create(liga="PL", id_partido="99", equipo_local="A",
                                           equipo_visitante="B", prob_local=.5,
                                           prob_empate=.3, prob_visitante=.2)
        dato = {"terminado": True, "gf": 2, "gc": 0, "utc": "2020-01-01T15:00:00Z"}
        with mock.patch("analizador.management.commands.evaluar_motor.resultado_partido",
                        return_value=(dato, None)):
            call_command("evaluar_motor", stdout=StringIO())
        p.refresh_from_db()
        self.assertTrue(p.evaluado)
        self.assertEqual(p.resultado, "")


class MantenimientoMotorTests(TestCase):
    #El motor se mantiene solo en produccion: sin cron y sin correr comandos a mano

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def visitar(self, hora):
        from datetime import datetime
        from unittest import mock
        from django.test import override_settings
        from django.utils import timezone
        from analizador import middleware
        momento = timezone.make_aware(datetime(2026, 9, 23, hora, 30))
        with override_settings(MOTOR_AUTOMATICO=True), \
             mock.patch.object(middleware.timezone, "localtime", return_value=momento), \
             mock.patch.object(middleware, "_lanzar") as lanzar:
            for _ in range(3):
                self.client.get(reverse("Inicio"))
        return [c.args[0] for c in lanzar.call_args_list]

    def test_base_vacia_se_calibra_y_se_ajusta_de_una_vez(self):
        from analizador import middleware
        lanzados = self.visitar(hora=14)
        self.assertEqual(lanzados.count(middleware._calibrar), 1)
        self.assertEqual(lanzados.count(middleware._primer_ajuste), 1)

    def test_con_datos_el_ajuste_solo_corre_de_madrugada_y_una_vez(self):
        from analizador import middleware
        from analizador.models import AjusteMotor, PesosMotor
        AjusteMotor.objects.create(liga="PL", parametros={"xi": 0.003})
        PesosMotor.objects.create(liga="PL", pesos={})
        self.assertEqual(self.visitar(hora=14), [])
        self.assertEqual(self.visitar(hora=4), [middleware._mantenimiento_nocturno])
        self.assertEqual(self.visitar(hora=5), [])   #ya corrio hoy

    def test_afina_una_vez_al_mes_y_no_todas_las_noches(self):
        #Una liga que se quedo con los parametros de fabrica (porque afinar no
        #los mejoraba) no puede provocar un afinado cada noche
        from django.core.cache import cache
        from analizador import middleware
        from analizador.models import AjusteMotor
        AjusteMotor.objects.create(liga="SA", parametros={})
        self.assertTrue(middleware._toca_afinar())          #nunca se afino
        cache.set("motor_afinado_reciente", 1, 60)
        self.assertFalse(middleware._toca_afinar())

    def test_el_primer_ajuste_es_el_rapido(self):
        from unittest import mock
        from analizador import middleware
        with mock.patch.object(middleware, "_correr") as correr:
            middleware._primer_ajuste()
        self.assertEqual([c.args for c in correr.call_args_list],
                         [("ajustar_motor",), ("evaluar_motor",)])
