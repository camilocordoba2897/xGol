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
