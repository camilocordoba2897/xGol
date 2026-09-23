#Pruebas del registro y de sus validaciones.
#
#Correr con:  python manage.py test usuarios
from datetime import date

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from usuarios.models import Perfil, Rol
from usuarios.validaciones import (validar_contrasena, validar_correo,
                                   validar_documento, validar_fecha_nacimiento,
                                   validar_nombre, validar_usuario)


def crear_cuenta(username="juan", email="juan@correo.com", documento="1234567890"):
    usuario = User.objects.create_user(username=username, email=email, password="Clave#123")
    Perfil.objects.create(usuario=usuario, documento=documento)
    return usuario


class ValidacionesFormatoTests(TestCase):

    def test_nombre_se_capitaliza_por_partes(self):
        self.assertEqual(validar_nombre("  ana   maría o'connor ")[0], "Ana María O'Connor")
        self.assertEqual(validar_nombre("sánchez-prieto")[0], "Sánchez-Prieto")

    def test_nombre_rechaza_numeros_simbolos_y_relleno(self):
        for malo in ("Juan3", "Ana%", "a", "aaaa", ""):
            self.assertIsNotNone(validar_nombre(malo)[1], malo)

    def test_usuario_formato(self):
        self.assertIsNone(validar_usuario("camilo97")[1])
        for malo in ("ab", "con espacio", "sim#bolo", "12345", "x" * 21):
            self.assertIsNotNone(validar_usuario(malo)[1], malo)

    def test_correo_se_guarda_en_minusculas(self):
        self.assertEqual(validar_correo(" Juan@Correo.COM ")[0], "juan@correo.com")
        self.assertIsNotNone(validar_correo("sin-arroba.com")[1])

    def test_contrasena_reglas(self):
        self.assertIsNone(validar_contrasena("Clave#123")[1])
        for mala in ("Cl#1", "clave#123", "CLAVE#123", "Clave#abc", "Clave1234", "Clave#1234567890X"):
            self.assertIsNotNone(validar_contrasena(mala)[1], mala)

    def test_documento_se_limpia_de_puntos(self):
        self.assertEqual(validar_documento("1.234.567.890"), ("1234567890", None))

    def test_documento_invalido(self):
        for malo in ("", "12a456", "0123456", "12345", "12345678901", "7777777"):
            self.assertIsNotNone(validar_documento(malo)[1], malo)

    def test_fecha_solo_mayores_de_edad(self):
        hoy = date(2026, 9, 22)
        self.assertIsNone(validar_fecha_nacimiento("2008-09-22", hoy)[1])
        self.assertIsNotNone(validar_fecha_nacimiento("2008-09-23", hoy)[1])
        self.assertIsNotNone(validar_fecha_nacimiento("2030-01-01", hoy)[1])
        self.assertIsNotNone(validar_fecha_nacimiento("no-es-fecha", hoy)[1])


class DuplicadosTests(TestCase):

    def setUp(self):
        self.existente = crear_cuenta()

    def test_usuario_repetido_sin_importar_mayusculas(self):
        self.assertIsNotNone(validar_usuario("JUAN")[1])

    def test_correo_repetido_sin_importar_mayusculas(self):
        self.assertIsNotNone(validar_correo("JUAN@correo.com")[1])

    def test_cedula_repetida_aunque_venga_con_puntos(self):
        self.assertIsNotNone(validar_documento("1.234.567.890")[1])

    def test_al_editar_no_choca_consigo_mismo(self):
        pk = self.existente.pk
        self.assertIsNone(validar_usuario("juan", excluir_id=pk)[1])
        self.assertIsNone(validar_correo("juan@correo.com", excluir_id=pk)[1])
        self.assertIsNone(validar_documento("1234567890", excluir_id=pk)[1])

    def test_la_base_rechaza_cedula_repetida(self):
        #Garantia final: aunque alguien se salte la validacion, el indice
        #unico de la base no deja guardar la misma cedula dos veces.
        otro = User.objects.create_user(username="pedro", password="Clave#123")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Perfil.objects.create(usuario=otro, documento="1234567890")

    def test_la_base_admite_varias_cuentas_sin_cedula(self):
        #Las cuentas de Google y las del panel no tienen cedula (NULL).
        for nombre in ("sinced1", "sinced2"):
            u = User.objects.create_user(username=nombre, password="Clave#123")
            Perfil.objects.create(usuario=u, documento=None)
        self.assertEqual(Perfil.objects.filter(documento__isnull=True).count(), 2)


class RegistroVistaTests(TestCase):

    DATOS = {
        "nombre": "camilo", "apellidos": "córdoba muriel", "username": "camilo97",
        "email": "Camilo@Correo.com", "password": "Clave#123",
        "documento": "1.098.765.432", "fecha_nacimiento": "1997-05-10",
    }

    def setUp(self):
        Rol.objects.create(nombre="usuario")

    def test_registro_correcto_guarda_datos_limpios(self):
        r = self.client.post(reverse("Registro"), self.DATOS)
        self.assertRedirects(r, reverse("Ingresar"), fetch_redirect_response=False)
        usuario = User.objects.get(username="camilo97")
        self.assertEqual(usuario.email, "camilo@correo.com")
        self.assertEqual(usuario.first_name, "Camilo")
        self.assertEqual(usuario.perfil.documento, "1098765432")
        self.assertEqual(usuario.perfil.rol.nombre, "usuario")

    def test_no_deja_registrar_datos_ya_usados(self):
        crear_cuenta(username="camilo97", email="otro@correo.com", documento="555555")
        crear_cuenta(username="otro1", email="camilo@correo.com", documento="666666")
        crear_cuenta(username="otro2", email="otro2@correo.com", documento="1098765432")
        r = self.client.post(reverse("Registro"), self.DATOS)
        self.assertEqual(r.status_code, 200)
        errores = [str(m) for m in r.context["messages"]]
        self.assertTrue(any("usuario ya está en uso" in e for e in errores))
        self.assertTrue(any("correo ya tiene una cuenta" in e for e in errores))
        self.assertTrue(any("registrada con esa cedula" in e for e in errores))
        self.assertEqual(User.objects.count(), 3)

    def test_la_contrasena_nunca_se_devuelve_al_formulario(self):
        datos = dict(self.DATOS, documento="abc")
        r = self.client.post(reverse("Registro"), datos)
        self.assertNotIn("password", r.context["datos"])
        self.assertNotContains(r, "Clave#123")


class DisponibleTests(TestCase):

    def setUp(self):
        cache.clear()
        crear_cuenta()
        self.url = reverse("RegistroDisponible")

    def consultar(self, campo, valor):
        return self.client.post(self.url, {"campo": campo, "valor": valor})

    def test_datos_tomados(self):
        for campo, valor in (("username", "Juan"), ("email", "JUAN@correo.com"),
                             ("documento", "1.234.567.890")):
            d = self.consultar(campo, valor).json()
            self.assertFalse(d["disponible"], campo)
            self.assertTrue(d["mensaje"], campo)

    def test_datos_libres(self):
        for campo, valor in (("username", "libre1"), ("email", "libre@correo.com"),
                             ("documento", "98765432")):
            self.assertTrue(self.consultar(campo, valor).json()["disponible"], campo)

    def test_campo_no_permitido(self):
        self.assertEqual(self.consultar("password", "x").status_code, 400)

    def test_solo_post(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_tope_de_consultas_por_ip(self):
        from usuarios.views import TOPE_CONSULTAS
        for _ in range(TOPE_CONSULTAS):
            self.assertEqual(self.consultar("username", "libre1").status_code, 200)
        self.assertEqual(self.consultar("username", "libre1").status_code, 429)



class IngresoTests(TestCase):

    def setUp(self):
        cache.clear()
        self.usuario = crear_cuenta()
        #La pagina de ingreso pinta el boton de Google: en produccion la app
        #de Google existe en la base, en la base de pruebas hay que crearla.
        from allauth.socialaccount.models import SocialApp
        from django.contrib.sites.models import Site
        app = SocialApp.objects.create(provider="google", name="Google", client_id="x", secret="y")
        app.sites.add(Site.objects.get_current())

    def entrar(self, clave="Clave#123", **extra):
        return self.client.post(reverse("Ingresar"), {"username": "juan", "password": clave}, **extra)

    def test_navegador_con_agente_largo_puede_entrar(self):
        #El navegador de Instagram manda mas de 200 caracteres: antes daba 500
        r = self.entrar(HTTP_USER_AGENT="Mozilla/5.0 " + "Instagram " * 40)
        self.assertEqual(r.status_code, 302)

    def test_vuelve_a_la_pagina_que_pedia(self):
        r = self.client.post(reverse("Ingresar"), {"username": "juan", "password": "Clave#123",
                                                   "next": "/suscripcion"})
        self.assertRedirects(r, "/suscripcion", fetch_redirect_response=False)

    def test_no_redirige_a_otro_dominio(self):
        r = self.client.post(reverse("Ingresar"), {"username": "juan", "password": "Clave#123",
                                                   "next": "https://malicioso.com/"})
        self.assertNotIn("malicioso", r["Location"])

    def test_bloquea_tras_varios_fallos(self):
        from usuarios.views import FALLOS_POR_CUENTA
        for _ in range(FALLOS_POR_CUENTA):
            self.entrar("mala")
        #Ni con la clave correcta entra mientras dura el bloqueo
        r = self.entrar()
        self.assertEqual(r.status_code, 200)
        self.assertIn("Demasiados intentos", str(list(r.context["messages"])[0]))

    def test_formulario_incompleto_no_da_500(self):
        self.assertEqual(self.client.post(reverse("Ingresar"), {}).status_code, 200)


class PerfilTests(TestCase):

    def setUp(self):
        self.usuario = User.objects.create_user(username="ana", email="ana@correo.com",
                                                password="Clave#123")
        Perfil.objects.create(usuario=self.usuario)
        self.client.force_login(self.usuario)
        self.url = reverse("EditarPerfil")

    def mensajes(self, r):
        return [str(m) for m in r.context["messages"]]

    def test_completar_identidad_una_vez(self):
        self.client.post(self.url, {"accion": "identidad", "documento": "1.234.567",
                                    "fecha_nacimiento": "1990-05-10"})
        perfil = Perfil.objects.get(usuario=self.usuario)
        self.assertEqual((perfil.documento, str(perfil.fecha_nacimiento)), ("1234567", "1990-05-10"))
        #Una segunda vez no la cambia
        self.client.post(self.url, {"accion": "identidad", "documento": "7654321",
                                    "fecha_nacimiento": "1980-01-01"})
        self.assertEqual(Perfil.objects.get(usuario=self.usuario).documento, "1234567")

    def test_menor_de_edad_no_completa_identidad(self):
        r = self.client.post(self.url, {"accion": "identidad", "documento": "1234567",
                                        "fecha_nacimiento": "2015-01-01"}, follow=True)
        self.assertIsNone(Perfil.objects.get(usuario=self.usuario).fecha_nacimiento)
        self.assertTrue(any("mayor de 18" in m for m in self.mensajes(r)))

    def test_cedula_de_otro_no_se_puede_usar(self):
        crear_cuenta(username="pepe", email="pepe@correo.com", documento="1234567")
        self.client.post(self.url, {"accion": "identidad", "documento": "1234567",
                                    "fecha_nacimiento": "1990-05-10"})
        self.assertIsNone(Perfil.objects.get(usuario=self.usuario).documento)

    def test_avatar_que_no_es_imagen_se_rechaza(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        falso = SimpleUploadedFile("foto.png", b"<script>alert(1)</script>", content_type="image/png")
        r = self.client.post(self.url, {"accion": "datos", "correo": "ana@correo.com", "avatar": falso},
                             follow=True)
        self.assertFalse(Perfil.objects.get(usuario=self.usuario).avatar)
        self.assertTrue(any("imagen" in m for m in self.mensajes(r)))

    def test_telefono_invalido_no_tumba_el_guardado(self):
        r = self.client.post(self.url, {"accion": "datos", "correo": "ana@correo.com",
                                        "telefono": "3" * 40}, follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(any("telefono" in m for m in self.mensajes(r)))

    def test_cambio_de_clave_sin_campos_no_da_500(self):
        r = self.client.post(self.url, {"accion": "clave", "clave_actual": "Clave#123"}, follow=True)
        self.assertEqual(r.status_code, 200)


class PanelAdminTests(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser("jefe", password="Clave#123")
        self.client.force_login(self.admin)
        self.cliente = crear_cuenta()

    def test_bloquear_solo_por_post(self):
        url = reverse("AdminEstadoUsuario", args=[self.cliente.id])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.post(url)
        self.cliente.refresh_from_db()
        self.assertFalse(self.cliente.is_active)

    def test_no_borra_a_quien_tiene_facturas(self):
        from pagos.models import Pago
        Pago.objects.create(usuario=self.cliente, referencia="R1", estado="Aprobado")
        self.client.post(reverse("AdminEliminarUsuario", args=[self.cliente.id]))
        self.assertTrue(User.objects.filter(pk=self.cliente.pk).exists())
        self.assertTrue(Pago.objects.filter(referencia="R1").exists())
