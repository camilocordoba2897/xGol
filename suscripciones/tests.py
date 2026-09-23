#Pruebas de planes, vigencia y control de acceso por suscripcion.
#
#Correr con:  python manage.py test suscripciones
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from suscripciones.models import Suscripcion
from suscripciones.planes import PLANES, desglosar_precio, nivel_de_plan, obtener_plan
from usuarios.models import Perfil, Rol


def hoy():
    return timezone.localdate()


class PlanesTests(TestCase):

    def test_desglose_del_iva_cuadra_con_el_total(self):
        for plan in PLANES.values():
            d = desglosar_precio(plan["precio"])
            self.assertEqual(d["subtotal"] + d["iva"], plan["precio"])
        self.assertEqual(desglosar_precio(20000)["subtotal"], 16807)

    def test_niveles(self):
        self.assertEqual(nivel_de_plan("Mensual"), 1)
        self.assertEqual(nivel_de_plan("Trimestral"), 2)
        self.assertEqual(nivel_de_plan("Inventado"), 0)
        self.assertIsNone(obtener_plan("gratis"))


class VigenciaTests(TestCase):

    def setUp(self):
        self.s = Suscripcion.objects.create(
            usuario=User.objects.create_user(username="ana", password="Clave#123"))

    def test_nueva_no_esta_vigente(self):
        self.assertFalse(self.s.esta_vigente())
        self.assertEqual(self.s.dias_restantes(), 0)

    def test_activar_desde_cero(self):
        self.s.activar("Mensual", 20000, 30)
        self.assertTrue(self.s.esta_vigente())
        self.assertEqual(self.s.vencimiento, hoy() + timedelta(days=30))

    def test_renovar_suma_sobre_los_dias_que_quedan(self):
        #Quien renueva antes de vencer no pierde los dias que ya pago
        self.s.activar("Mensual", 20000, 30)
        self.s.activar("Trimestral", 50000, 90)
        self.assertEqual(self.s.vencimiento, hoy() + timedelta(days=120))
        self.assertEqual(self.s.plan, "Trimestral")

    def test_vencida_no_esta_vigente(self):
        self.s.activa = True
        self.s.vencimiento = hoy() - timedelta(days=1)
        self.assertFalse(self.s.esta_vigente())

    def test_vence_hoy_todavia_vale(self):
        self.s.activa = True
        self.s.vencimiento = hoy()
        self.assertTrue(self.s.esta_vigente())

    def test_cancelar_no_quita_los_dias_pagados(self):
        self.s.activar("Mensual", 20000, 30)
        self.s.cancelar()
        self.s.refresh_from_db()
        self.assertTrue(self.s.esta_vigente())
        self.assertEqual(self.s.cancelada_en, hoy())


class AccesoTests(TestCase):
    #El analizador es lo que se vende: sin suscripcion vigente no se entra.

    def setUp(self):
        self.usuario = User.objects.create_user(username="ana", password="Clave#123")
        Perfil.objects.create(usuario=self.usuario)
        self.url = reverse("Analizador")

    def test_anonimo_va_a_ingresar(self):
        self.client.logout()
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("Ingresar"), r["Location"])

    def test_sin_suscripcion_va_a_planes(self):
        self.client.force_login(self.usuario)
        self.assertRedirects(self.client.get(self.url), reverse("Suscripcion"),
                             fetch_redirect_response=False)

    def test_vencida_se_apaga_y_va_a_planes(self):
        Suscripcion.objects.create(usuario=self.usuario, activa=True,
                                   vencimiento=hoy() - timedelta(days=1))
        self.client.force_login(self.usuario)
        self.assertRedirects(self.client.get(self.url), reverse("Suscripcion"),
                             fetch_redirect_response=False)
        self.assertFalse(Suscripcion.objects.get(usuario=self.usuario).activa)

    def test_vigente_entra(self):
        Suscripcion.objects.create(usuario=self.usuario).activar("Mensual", 20000, 30)
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_administrador_entra_sin_pagar(self):
        self.usuario.perfil.rol = Rol.objects.create(nombre="administrador")
        self.usuario.perfil.save()
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.get(self.url).status_code, 200)


class CheckoutTests(TestCase):

    def setUp(self):
        self.usuario = User.objects.create_user(username="ana", password="Clave#123")
        Perfil.objects.create(usuario=self.usuario, documento="1234567",
                              fecha_nacimiento=date(1990, 1, 1))
        self.client.force_login(self.usuario)

    def test_cuenta_de_google_sin_cedula_va_a_completar_perfil(self):
        Perfil.objects.filter(usuario=self.usuario).update(documento=None, fecha_nacimiento=None)
        self.assertRedirects(self.client.get(reverse("Checkout", args=["mensual"])),
                             reverse("EditarPerfil"), fetch_redirect_response=False)

    def test_muestra_el_precio_del_servidor(self):
        r = self.client.get(reverse("Checkout", args=["mensual"]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["plan"]["precio"], PLANES["mensual"]["precio"])

    def test_plan_inexistente(self):
        self.assertRedirects(self.client.get(reverse("Checkout", args=["gratis"])),
                             reverse("Suscripcion"), fetch_redirect_response=False)

    def test_no_deja_comprar_un_plan_igual_o_inferior_al_vigente(self):
        Suscripcion.objects.create(usuario=self.usuario).activar("Trimestral", 50000, 90)
        self.assertRedirects(self.client.get(reverse("Checkout", args=["mensual"])),
                             reverse("Suscripcion"), fetch_redirect_response=False)


class ActivacionManualTests(TestCase):

    def test_un_usuario_normal_no_puede_regalarse_una_suscripcion(self):
        usuario = User.objects.create_user(username="ana", password="Clave#123")
        Perfil.objects.create(usuario=usuario)
        self.client.force_login(usuario)
        self.client.post(reverse("AdminActivarSuscripcion", args=[usuario.id]), {"plan": "trimestral"})
        s = Suscripcion.objects.filter(usuario=usuario).first()
        self.assertFalse(s is not None and s.esta_vigente())


class ActivacionManualNoDegradaTests(TestCase):

    def test_mensual_encima_de_trimestral_suma_dias_sin_cambiar_el_plan(self):
        admin = User.objects.create_superuser("jefe", password="Clave#123")
        usuario = User.objects.create_user(username="ana", password="Clave#123")
        Suscripcion.objects.create(usuario=usuario).activar("Trimestral", 50000, 90)
        self.client.force_login(admin)
        self.client.post(reverse("AdminActivarSuscripcion", args=[usuario.id]), {"plan": "mensual"})
        s = Suscripcion.objects.get(usuario=usuario)
        self.assertEqual(s.plan, "Trimestral")
        self.assertEqual(s.vencimiento, hoy() + timedelta(days=120))


class ZonaHorariaTests(TestCase):

    def test_el_dia_del_vencimiento_vale_hasta_medianoche_en_colombia(self):
        #22/10 a las 8 p. m. en Bogota ya es 23/10 en UTC. Antes el plan se
        #daba por vencido 5 horas antes de tiempo.
        from datetime import datetime, timezone as dtz
        from unittest import mock
        noche = datetime(2026, 10, 23, 1, 0, tzinfo=dtz.utc)
        with mock.patch("django.utils.timezone.now", return_value=noche):
            s = Suscripcion(activa=True, vencimiento=date(2026, 10, 22))
            self.assertTrue(s.esta_vigente())
