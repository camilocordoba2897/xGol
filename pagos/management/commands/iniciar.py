#Arranca el tunel de ngrok y el servidor de desarrollo en UNA sola terminal.
#
#Uso:
#  python manage.py iniciar
#  python manage.py iniciar --puerto 8001
#  python manage.py iniciar --sin-tunel     (solo Django, sin ngrok)
#
#Ctrl+C apaga las dos cosas.
import atexit
import json
import os
import platform
import shutil
import subprocess
import time
import urllib.request

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

#Panel local de ngrok. De aqui se lee la URL publica sin tener que copiarla.
API_NGROK="http://127.0.0.1:4040/api/tunnels"


class Command(BaseCommand):
    help="Levanta el tunel de ngrok y el servidor de desarrollo en una sola terminal."

    def add_arguments(self,parser):
        parser.add_argument("--puerto",default="8000",help="Puerto del servidor. Por defecto 8000.")
        parser.add_argument("--sin-tunel",action="store_true",help="Arranca solo Django, sin ngrok.")

    # ------------------------------------------------------------
    def handle(self,*args,**opciones):
        puerto=str(opciones["puerto"])

        #runserver se reinicia solo cuando cambia un archivo: relanza este
        #mismo comando con RUN_MAIN=true. Sin esta guarda, cada guardado
        #levantaria otro ngrok y chocarian por el mismo dominio.
        if os.environ.get("RUN_MAIN")!="true" and not opciones["sin_tunel"]:
            self._levantar_tunel(puerto)

        call_command("runserver",puerto)

    # ------------------------------------------------------------
    def _ruta_ngrok(self):
        #Primero el ejecutable que esta en la carpeta del proyecto; si no,
        #el que este instalado en el sistema.
        nombre="ngrok.exe" if platform.system()=="Windows" else "ngrok"
        raiz=str(getattr(settings,"BASE_DIR","") or os.getcwd())
        local=os.path.join(raiz,nombre)
        if os.path.exists(local):
            return local
        return shutil.which("ngrok")

    def _matar_sobrantes(self):
        #Un ngrok viejo colgado se queda con el dominio y el nuevo falla con
        #ERR_NGROK_334. Se limpia antes de arrancar.
        try:
            if platform.system()=="Windows":
                subprocess.run(["taskkill","/IM","ngrok.exe","/F"],
                               stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
            else:
                subprocess.run(["pkill","-f","ngrok"],
                               stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
        except Exception:
            pass

    def _url_publica(self,intentos=20):
        #ngrok tarda un momento en levantar. Se le pregunta a su panel local
        #hasta que responda, en vez de esperar un tiempo fijo a ciegas.
        for _ in range(intentos):
            try:
                with urllib.request.urlopen(API_NGROK,timeout=1) as respuesta:
                    datos=json.loads(respuesta.read().decode("utf-8"))
                for tunel in datos.get("tunnels") or []:
                    url=tunel.get("public_url") or ""
                    if url.startswith("https://"):
                        return url
            except Exception:
                pass
            time.sleep(0.7)
        return ""

    # ------------------------------------------------------------
    def _levantar_tunel(self,puerto):
        ejecutable=self._ruta_ngrok()
        if not ejecutable:
            self.stdout.write(self.style.WARNING(
                "\n  No encontre ngrok.exe en la carpeta del proyecto ni en el PATH."
                "\n  El servidor arranca igual, pero sin URL publica los pagos no se pueden probar."
                "\n  Para saltarte el tunel a proposito: python manage.py iniciar --sin-tunel\n"))
            return

        self._matar_sobrantes()

        orden=[ejecutable,"http",puerto]
        base=(getattr(settings,"PAGOS_URL_BASE","") or "").rstrip("/")
        if base:
            orden.append(f"--url={base}")

        self.stdout.write("\n  Levantando el tunel...")
        try:
            proceso=subprocess.Popen(orden,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        except Exception as error:
            self.stdout.write(self.style.ERROR(f"  No se pudo arrancar ngrok: {error}\n"))
            return

        #Que el tunel no quede huerfano cuando se cierre Django.
        atexit.register(self._apagar,proceso)

        url=self._url_publica()
        if not url:
            salida=""
            if proceso.poll() is not None and proceso.stderr is not None:
                salida=proceso.stderr.read().decode("utf-8","ignore")[:600]
            self.stdout.write(self.style.ERROR(
                "\n  El tunel no arranco.\n"+(f"\n{salida}\n" if salida else
                "\n  Revisa que el authtoken este registrado:\n"
                "    ngrok config add-authtoken TU_TOKEN\n")))
            return

        self._reportar(url,puerto,base)

    def _reportar(self,url,puerto,base):
        ruta_webhook=url+"/pago/eventos/wompi/x7k2"
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"  Tunel activo:  {url}"))
        self.stdout.write(f"  Webhook:       {ruta_webhook}")
        self.stdout.write(f"  Local:         http://127.0.0.1:{puerto}")

        dominio=url.replace("https://","")
        if base and base!=url:
            #Aviso ruidoso a proposito: con la URL desalineada, el usuario
            #vuelve de la pasarela a un dominio que no existe.
            self.stdout.write(self.style.ERROR(
                "\n  OJO: la URL del tunel no coincide con PAGOS_URL_BASE."
                f"\n  Corrige estas tres lineas en .env:\n"
                f"\n    PAGOS_URL_BASE={url}"
                f"\n    ALLOWED_HOSTS=127.0.0.1,localhost,{dominio}"
                f"\n    CSRF_TRUSTED_ORIGINS={url}\n"
                f"\n  Y la URL de eventos en el panel de Wompi:\n    {ruta_webhook}\n"))
        elif dominio not in (getattr(settings,"ALLOWED_HOSTS",None) or []):
            self.stdout.write(self.style.ERROR(
                f"\n  OJO: falta '{dominio}' en ALLOWED_HOSTS del .env."
                "\n  Sin eso, entrar por el tunel devuelve DisallowedHost.\n"))
        self.stdout.write("")

    def _apagar(self,proceso):
        try:
            if proceso.poll() is None:
                proceso.terminate()
        except Exception:
            pass