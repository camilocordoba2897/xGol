#Pruebas de la pasarela de pagos (Wompi). Ninguna sale a internet: se prueba
#lo que el proyecto arma y firma, no la respuesta de Wompi.
#
#Correr con:  python manage.py test pagos
import hashlib
from urllib.parse import parse_qs, urlparse

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from pagos import pasarela
from pagos.models import Pago
from pagos.views import _url_publica
from usuarios.models import Perfil
from datetime import date, timedelta
from unittest import mock
from django.utils import timezone

LLAVES = dict(WOMPI_LLAVE_PUBLICA="pub_test_x", WOMPI_LLAVE_PRIVADA="prv_test_x",
              WOMPI_SECRETO_INTEGRIDAD="integridad", WOMPI_SECRETO_EVENTOS="eventos")


@override_settings(**LLAVES)
class FirmasTests(TestCase):

    def test_firma_de_integridad(self):
        esperada = hashlib.sha256(b"REF1234500COPintegridad").hexdigest()
        self.assertEqual(pasarela.firma_integridad("REF1", 234500), esperada)

    def _evento(self, checksum):
        return {"data": {"transaction": {"id": "t1", "status": "APPROVED", "amount_in_cents": 100}},
                "signature": {"properties": ["transaction.id", "transaction.status",
                                             "transaction.amount_in_cents"],
                              "checksum": checksum},
                "timestamp": 1700000000}

    def test_webhook_con_firma_correcta(self):
        checksum = hashlib.sha256(b"t1APPROVED1001700000000eventos").hexdigest()
        self.assertTrue(pasarela.verificar_evento(self._evento(checksum))[0])

    def test_webhook_con_firma_falsa(self):
        self.assertFalse(pasarela.verificar_evento(self._evento("0" * 64))[0])


class UrlRetornoTests(TestCase):
    #Wompi (su CloudFront) responde 403 si la direccion de regreso es
    #127.0.0.1 o localhost. En el despliegue tiene que salir SIEMPRE https y
    #con el dominio publico.

    def setUp(self):
        self.fabrica = RequestFactory()

    @override_settings(PAGOS_URL_BASE="https://xgol.example.com", ALLOWED_HOSTS=["xgol.example.com"])
    def test_en_el_dominio_usa_la_base_https(self):
        request = self.fabrica.get("/", HTTP_HOST="xgol.example.com")
        self.assertEqual(_url_publica(request, "RetornoPago"),
                         "https://xgol.example.com" + reverse("RetornoPago"))

    @override_settings(PAGOS_URL_BASE="", ALLOWED_HOSTS=["xgol.example.com"],
                       SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"))
    def test_detras_del_proxy_sin_base_tambien_sale_https(self):
        request = self.fabrica.get("/", HTTP_HOST="xgol.example.com",
                                   HTTP_X_FORWARDED_PROTO="https")
        self.assertTrue(_url_publica(request, "RetornoPago").startswith("https://xgol.example.com/"))

    @override_settings(PAGOS_URL_BASE="https://xgol.example.com", ALLOWED_HOSTS=["127.0.0.1"])
    def test_en_local_no_manda_al_dominio(self):
        request = self.fabrica.get("/", HTTP_HOST="127.0.0.1:8000")
        self.assertTrue(_url_publica(request, "RetornoPago").startswith("http://127.0.0.1:8000/"))


@override_settings(PAGOS_URL_BASE="https://xgol.example.com",
                   ALLOWED_HOSTS=["xgol.example.com"], **LLAVES)
class CheckoutTests(TestCase):

    def setUp(self):
        cache.clear()
        self.usuario = User.objects.create_user(username="pagador", email="p@correo.com",
                                                password="Clave#123")
        Perfil.objects.create(usuario=self.usuario, documento="1234567",
                              fecha_nacimiento=date(1990, 1, 1))
        self.client.force_login(self.usuario)

    def pagar(self, plan="mensual"):
        return self.client.post(reverse("ProcesarPago", args=[plan]),
                                HTTP_HOST="xgol.example.com", secure=True)

    def test_manda_a_wompi_con_precio_del_servidor_y_regreso_publico(self):
        r = self.pagar()
        destino = urlparse(r["Location"])
        self.assertEqual(destino.netloc, "checkout.wompi.co")
        q = {k: v[0] for k, v in parse_qs(destino.query).items()}
        pago = Pago.objects.get(usuario=self.usuario)
        self.assertEqual(q["amount-in-cents"], str(pago.monto_centavos))
        self.assertEqual(q["reference"], pago.referencia)
        self.assertEqual(q["signature:integrity"],
                         pasarela.firma_integridad(pago.referencia, pago.monto_centavos))
        self.assertEqual(q["redirect-url"], "https://xgol.example.com" + reverse("RetornoPago"))
        self.assertEqual(pago.estado, "Pendiente")

    def test_plan_inexistente_no_crea_pago(self):
        self.pagar("gratis")
        self.assertFalse(Pago.objects.exists())

    def test_solo_post(self):
        r = self.client.get(reverse("ProcesarPago", args=["mensual"]),
                            HTTP_HOST="xgol.example.com", secure=True)
        self.assertEqual(r.status_code, 405)


    def sin_identidad(self):
        Perfil.objects.filter(usuario=self.usuario).update(documento=None, fecha_nacimiento=None)

    def test_sin_cedula_ni_fecha_no_deja_pagar(self):
        self.sin_identidad()
        r = self.pagar()
        self.assertRedirects(r, reverse("Checkout", args=["mensual"]), fetch_redirect_response=False)
        self.assertFalse(Pago.objects.exists())

    def test_identidad_y_pago_en_un_solo_clic(self):
        self.sin_identidad()
        r = self.client.post(reverse("ProcesarPago", args=["mensual"]),
                             {"documento": "1.234.567", "fecha_nacimiento": "1990-05-10"},
                             HTTP_HOST="xgol.example.com", secure=True)
        self.assertEqual(urlparse(r["Location"]).netloc, "checkout.wompi.co")
        perfil = Perfil.objects.get(usuario=self.usuario)
        self.assertEqual((perfil.documento, str(perfil.fecha_nacimiento)), ("1234567", "1990-05-10"))

    def test_menor_de_edad_vuelve_al_checkout_con_lo_que_escribio(self):
        self.sin_identidad()
        r = self.client.post(reverse("ProcesarPago", args=["mensual"]),
                             {"documento": "1234567", "fecha_nacimiento": "2015-01-01"},
                             HTTP_HOST="xgol.example.com", secure=True, follow=True)
        self.assertFalse(Pago.objects.exists())
        self.assertContains(r, 'value="1234567"')
        self.assertTrue(any("mayor de 18" in str(m) for m in r.context["messages"]))


@override_settings(**LLAVES)
class ConciliacionTests(TestCase):
    #Un pago cuyo webhook se perdio y cuyo usuario no volvio nunca recibe el
    #id de la pasarela. Antes se quedaba sin revisar y a las 24 h se anulaba
    #aunque el cliente SI hubiera pagado.

    def setUp(self):
        from pagos import servicios
        self.servicios = servicios
        self.usuario = User.objects.create_user(username="cliente", password="Clave#123")
        self.pago, _ = servicios.crear_pago_pendiente(self.usuario, "mensual")
        Pago.objects.filter(pk=self.pago.pk).update(creado=timezone.now() - timedelta(hours=2))

    def transaccion(self, estado="APPROVED"):
        return {"id": "tx-1", "reference": self.pago.referencia, "status": estado,
                "amount_in_cents": self.pago.monto_centavos, "currency": "COP",
                "payment_method_type": "PSE"}

    def test_pago_sin_id_se_busca_por_referencia_y_se_aplica(self):
        with mock.patch.object(pasarela, "buscar_por_referencia",
                               return_value=(self.transaccion(), None)) as buscar:
            revisados, aplicados = self.servicios.conciliar_pendientes()
        buscar.assert_called_once_with(self.pago.referencia)
        self.assertEqual((revisados, aplicados), (1, 1))
        self.pago.refresh_from_db()
        self.assertTrue(self.pago.aplicado)
        self.assertEqual(self.pago.id_pasarela, "tx-1")
        self.assertTrue(self.usuario.suscripcion.esta_vigente())

    def test_no_otorga_dos_veces(self):
        with mock.patch.object(pasarela, "buscar_por_referencia",
                               return_value=(self.transaccion(), None)):
            self.servicios.conciliar_pendientes()
        with mock.patch.object(pasarela, "consultar_transaccion",
                               return_value=(self.transaccion(), None)):
            _, resultado = self.servicios.aplicar_transaccion(
                pasarela.leer_transaccion(self.transaccion()))
        self.assertEqual(resultado, "ya_aplicado")

    def test_monto_distinto_no_otorga(self):
        tx = dict(self.transaccion(), amount_in_cents=100)
        with mock.patch.object(pasarela, "buscar_por_referencia", return_value=(tx, None)):
            self.servicios.conciliar_pendientes()
        self.pago.refresh_from_db()
        self.assertFalse(self.pago.aplicado)
        self.assertEqual(self.pago.estado, "Error")

    def test_buscar_por_referencia_prefiere_la_aprobada(self):
        respuesta = mock.Mock(status_code=200)
        respuesta.json.return_value = {"data": [
            self.transaccion("DECLINED"), self.transaccion("APPROVED"),
            dict(self.transaccion(), reference="OTRA")]}
        with mock.patch.object(pasarela.requests, "get", return_value=respuesta):
            datos, error = pasarela.buscar_por_referencia(self.pago.referencia)
        self.assertIsNone(error)
        self.assertEqual(datos["status"], "APPROVED")


class FacturaTests(TestCase):

    def test_la_factura_usa_la_vigencia_del_pago_y_no_se_cae_sin_suscripcion(self):
        from pagos.factura import generar_factura_pdf
        usuario = User.objects.create_user(username="f", password="Clave#123")
        pago = Pago.objects.create(usuario=usuario, referencia="R1", estado="Aprobado",
                                   monto=20000, subtotal=16807, iva=3193, monto_centavos=2000000)
        self.assertTrue(generar_factura_pdf(pago).getvalue().startswith(b"%PDF"))
