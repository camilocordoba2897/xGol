#Pruebas de planes, vigencia y control de acceso por suscripcion.
#
#Correr con:  python manage.py test suscripciones
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from suscripciones.models import Suscripcion
from suscripciones.planes import PLANES, desglosar_precio, nivel_de_plan, obtener_plan
from usuarios.models import Perfil, Rol


def hoy():
    return timezone.now().date()


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
        self.client.force_login(self.usuario)

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
