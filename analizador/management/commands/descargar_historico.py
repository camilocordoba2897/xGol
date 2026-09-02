#DESCARGA DEL HISTORICO. Se corre UNA VEZ y ya.
#
#   python manage.py descargar_historico
#   python manage.py descargar_historico --desde C:\Users\tu\Downloads\Matches.csv
#
#QUE HACE:
#  Baja un archivo de 42 MB con 230.000 partidos de 38 ligas desde GitHub, se
#  queda solo con las 8 ligas del analizador y solo con las columnas que el
#  motor usa, y las guarda partidas en datos_historicos/. De 42 MB quedan
#  menos de 5 MB en disco y cada liga se lee despues en centesimas de segundo.
#
#POR QUE DESDE GITHUB Y NO DESDE football-data.co.uk:
#  Porque ese dominio esta bloqueado en tu red (falla en el puerto 443 y en el
#  80, con y sin navegador simulado: las peticiones no llegan al servidor).
#  Son los mismos datos: el repositorio los recopila de ahi. GitHub si te
#  funciona, el proyecto ya lo usa.
#
#SI GITHUB TAMBIEN FALLA:
#  Abre esta direccion en el navegador y guarda el archivo donde quieras:
#     https://raw.githubusercontent.com/xgabora/Club-Football-Match-Data-2000-2025/master/data/Matches.csv
#  Despues corre el comando con --desde y la ruta del archivo. El resto es
#  identico: partir el archivo no necesita internet.
#
#CADA CUANTO REPETIRLO:
#  Casi nunca. El historico es historia: no cambia. Vale la pena repetirlo solo
#  cuando el repositorio publique temporadas nuevas, una o dos veces al año.
#  Los partidos recientes no salen de aqui, salen de football-data.org.
import csv
import os

from django.core.management.base import BaseCommand

from analizador import api_historico

URL = ("https://raw.githubusercontent.com/xgabora/"
       "Club-Football-Match-Data-2000-2025/master/data/Matches.csv")

#Codigo de division en el archivo de origen -> codigo de liga de xGol
DIVISIONES = {v: k for k, v in api_historico.LIGAS_HISTORICO.items()}


class Command(BaseCommand):
    help = "Descarga el historico de partidos con cuotas y lo guarda por liga."

    def add_arguments(self, parser):
        parser.add_argument("--desde", type=str, default=None,
            help="Ruta de un Matches.csv ya descargado a mano. Salta la descarga.")
        parser.add_argument("--guardar-crudo", action="store_true",
            help="Conserva el archivo grande de 42 MB. Por defecto se borra tras partirlo.")

    def handle(self, *args, **opciones):
        carpeta = api_historico.carpeta_datos()
        os.makedirs(carpeta, exist_ok=True)
        crudo = opciones["desde"] or os.path.join(carpeta, "_Matches.csv")

        self.stdout.write("")

        # ---------- 1. conseguir el archivo grande ----------
        if opciones["desde"]:
            if not os.path.exists(crudo):
                self.stderr.write(self.style.ERROR(f"No existe el archivo: {crudo}"))
                return
            self.stdout.write(f"Usando el archivo que indicaste: {crudo}")
        else:
            self.stdout.write("Descargando el historico desde GitHub (42 MB)...")
            if not self._descargar(crudo):
                return

        # ---------- 2. partir por liga ----------
        self.stdout.write("")
        self.stdout.write("Separando por liga...")
        try:
            resumen = self._partir(crudo, carpeta)
        except OSError as e:
            self.stderr.write(self.style.ERROR(f"No se pudo leer el archivo: {e}"))
            return

        if not resumen:
            self.stderr.write(self.style.ERROR(
                "El archivo no traia ninguna de las 8 ligas. "
                "Puede estar incompleto: borralo y vuelve a correr el comando."))
            return

        # ---------- 3. informe ----------
        self.stdout.write("")
        total = con_cuotas = 0
        for liga in sorted(resumen):
            datos = resumen[liga]
            total += datos["partidos"]
            con_cuotas += datos["cuotas"]
            porcentaje = 100.0 * datos["cuotas"] / max(1, datos["partidos"])
            self.stdout.write(self.style.SUCCESS(
                f"  {liga:<4} {datos['partidos']:>6} partidos | "
                f"{datos['cuotas']:>6} con cuotas ({porcentaje:.0f}%) | "
                f"{datos['desde'][:7]} a {datos['hasta'][:7]}"))

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Listo: {total} partidos, {con_cuotas} con cuotas, en {carpeta}"))

        # ---------- 4. limpiar ----------
        if not opciones["guardar_crudo"] and not opciones["desde"]:
            try:
                os.remove(crudo)
                self.stdout.write("Archivo grande borrado: ya no hace falta.")
            except OSError:
                pass

        self.stdout.write("")
        self.stdout.write("Siguiente paso:  python manage.py verificar_historico")
        self.stdout.write("")

    # ------------------------------------------------------------
    def _descargar(self, destino):
        #Se descarga por trozos y no de un golpe: 42 MB enteros en memoria en
        #un equipo justo de RAM puede fallar, y ademas asi se ve el avance en
        #vez de dejar la terminal muda dos minutos.
        import requests
        try:
            r = requests.get(URL, stream=True, timeout=300,
                             headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                self.stderr.write(self.style.ERROR(
                    f"GitHub respondio {r.status_code}. Descarga el archivo a mano:"))
                self.stderr.write(f"   {URL}")
                self.stderr.write("   y corre:  python manage.py descargar_historico --desde <ruta>")
                return False

            escritos = 0
            with open(destino, "wb") as fh:
                for trozo in r.iter_content(1024 * 256):
                    if not trozo:
                        continue
                    fh.write(trozo)
                    escritos += len(trozo)
                    if escritos % (1024 * 1024 * 5) < 1024 * 256:
                        self.stdout.write(f"   {escritos // (1024 * 1024)} MB...")
            self.stdout.write(f"   descargados {escritos // (1024 * 1024)} MB")
            return True

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"No se pudo descargar: {type(e).__name__}"))
            self.stderr.write("")
            self.stderr.write("Si GitHub tambien esta bloqueado en tu red, abre esta")
            self.stderr.write("direccion en el navegador y guarda el archivo:")
            self.stderr.write(f"   {URL}")
            self.stderr.write("Despues corre:")
            self.stderr.write("   python manage.py descargar_historico --desde <ruta del archivo>")
            return False

    # ------------------------------------------------------------
    def _partir(self, crudo, carpeta):
        #Se guarda en memoria por liga y se escribe al final. Son 62.000 filas
        #de las 230.000: cabe de sobra y evita tener ocho archivos abiertos.
        cubos = {}
        with open(crudo, encoding="utf-8", errors="replace", newline="") as fh:
            for fila in csv.DictReader(fh):
                liga = DIVISIONES.get((fila.get("Division") or "").strip())
                if not liga:
                    continue
                #Sin marcador no sirve: el archivo trae partidos futuros con
                #las cuotas puestas y los goles vacios.
                if not (fila.get("FTHome") or "").strip():
                    continue
                if not (fila.get("FTAway") or "").strip():
                    continue
                cubos.setdefault(liga, []).append(
                    [(fila.get(c) or "").strip() for c in api_historico.COLUMNAS])

        resumen = {}
        for liga, filas in cubos.items():
            filas.sort(key=lambda f: f[0])
            ruta = os.path.join(carpeta, f"{liga}.csv")
            with open(ruta, "w", encoding="utf-8", newline="") as fh:
                escritor = csv.writer(fh)
                escritor.writerow(api_historico.COLUMNAS)
                escritor.writerows(filas)
            resumen[liga] = {
                "partidos": len(filas),
                #indices 5,6,7 = OddHome, OddDraw, OddAway
                "cuotas": sum(1 for f in filas if f[5] and f[6] and f[7]),
                "desde": filas[0][0],
                "hasta": filas[-1][0],
            }
        return resumen