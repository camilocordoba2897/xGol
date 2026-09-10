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
import io
import os
from datetime import date, datetime

from django.core.management.base import BaseCommand

from analizador import api_historico

URL = ("https://raw.githubusercontent.com/xgabora/"
       "Club-Football-Match-Data-2000-2025/master/data/Matches.csv")

# ------------------------------------------------------------
#  SEGUNDA FUENTE — SOLO PARA COMPLETAR LO QUE FALTA
#
#  El archivo de arriba se quedo parado en mayo de 2025. Este espejo publica
#  los MISMOS datos de football-data.co.uk temporada por temporada y si trae
#  2025/26 completa (con cuotas, tiros y corners) y Brasil hasta hoy.
#
#  Se comprobo cruzando la temporada 2024/25 contra la que ya estaba
#  descargada: mismos partidos, mismos marcadores, mismas cuotas.
#
#  Se usa SOLO con --completar y nunca reescribe lo que ya hay: agrega los
#  partidos que faltan y respeta los que ya estaban.
# ------------------------------------------------------------
ESPEJO = ("https://raw.githubusercontent.com/huhao930422-debug/"
          "football-odds-mirror/HEAD/data")

CARPETAS_ESPEJO = {
    "PL": "premier-league", "PD": "la-liga", "SA": "serie-a",
    "BL1": "bundesliga", "FL1": "ligue-1", "DED": "eredivisie",
    "PPL": "primeira-liga", "BSA": "brazil",
}

#Brasil juega por año natural y viene en un solo archivo con otro esquema
#de columnas (Home/Away/HG/AG en vez de HomeTeam/AwayTeam/FTHG/FTAG).
ARCHIVO_UNICO = {"BSA": "all-seasons.csv"}

#Alternativas por columna, de la mejor a la peor. Se toma la primera que
#tenga las TRES cuotas: un libro incompleto o mezclado no se puede limpiar.
CUOTAS_POSIBLES = [
    ("AvgH", "AvgD", "AvgA"),      #media de todas las casas (lo que ya usa el archivo grande)
    ("AvgCH", "AvgCD", "AvgCA"),   #media de cierre
    ("B365H", "B365D", "B365A"),
    ("B365CH", "B365CD", "B365CA"),
    ("PSCH", "PSCD", "PSCA"),
]
MAS_MENOS_POSIBLES = [("Avg>2.5", "Avg<2.5"), ("B365>2.5", "B365<2.5")]

#Codigo de division en el archivo de origen -> codigo de liga de xGol
DIVISIONES = {v: k for k, v in api_historico.LIGAS_HISTORICO.items()}


class Command(BaseCommand):
    help = "Descarga el historico de partidos con cuotas y lo guarda por liga."

    def add_arguments(self, parser):
        parser.add_argument("--desde", type=str, default=None,
            help="Ruta de un Matches.csv ya descargado a mano. Salta la descarga.")
        parser.add_argument("--guardar-crudo", action="store_true",
            help="Conserva el archivo grande de 42 MB. Por defecto se borra tras partirlo.")
        parser.add_argument("--completar", action="store_true",
            help="NO baja el archivo grande. Solo agrega a datos_historicos/ las "
                 "temporadas que le falten (2025/26 y Brasil al dia). Correr esto "
                 "despues del descargar_historico normal, o cada vez que quieras "
                 "ponerte al dia.")

    def handle(self, *args, **opciones):
        carpeta = api_historico.carpeta_datos()
        os.makedirs(carpeta, exist_ok=True)

        if opciones["completar"]:
            self._completar(carpeta)
            return

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
    #  COMPLETAR: agregar las temporadas que faltan
    # ------------------------------------------------------------
    def _completar(self, carpeta):
        import requests

        self.stdout.write("")
        self.stdout.write("Completando el historico con las temporadas que falten.")
        self.stdout.write("No se toca nada de lo que ya esta descargado.")
        self.stdout.write("")

        total_nuevos = 0
        for liga in sorted(CARPETAS_ESPEJO):
            ruta = api_historico.archivo_de_liga(liga)
            existentes, claves, ultima = self._leer_propio(ruta)
            self.stdout.write(f"  {liga:<4} ", ending="")

            nuevos = []
            for nombre_archivo in self._archivos_a_probar(liga):
                url = f"{ESPEJO}/{CARPETAS_ESPEJO[liga]}/{nombre_archivo}"
                try:
                    r = requests.get(url, timeout=120,
                                     headers={"User-Agent": "Mozilla/5.0"})
                except Exception:
                    continue
                if r.status_code != 200:
                    continue
                nuevos.extend(self._filas_del_espejo(r.text, claves, ultima))

            if not nuevos:
                self.stdout.write("ya estaba al dia")
                continue

            filas = existentes + nuevos
            filas.sort(key=lambda f: f[0])
            with open(ruta, "w", encoding="utf-8", newline="") as fh:
                escritor = csv.writer(fh)
                escritor.writerow(api_historico.COLUMNAS)
                escritor.writerows(filas)

            total_nuevos += len(nuevos)
            con_cuotas = sum(1 for f in nuevos if f[5] and f[6] and f[7])
            self.stdout.write(self.style.SUCCESS(
                f"+{len(nuevos):>4} partidos ({con_cuotas} con cuotas) | "
                f"antes hasta {ultima or '-'} | ahora hasta {filas[-1][0]}"))

        self.stdout.write("")
        if total_nuevos:
            self.stdout.write(self.style.SUCCESS(
                f"Listo: {total_nuevos} partidos nuevos."))
            self.stdout.write("Siguiente paso, para que el motor los aprenda:")
            self.stdout.write("   python manage.py calibrar_con_historico")
        else:
            self.stdout.write("No habia nada nuevo que agregar.")
        self.stdout.write("")

    # ------------------------------------------------------------
    def _archivos_a_probar(self, liga):
        #Brasil viene en un archivo unico. Las europeas, por temporada: se
        #prueban las tres ultimas y las que no existan devuelven 404 y ya.
        if liga in ARCHIVO_UNICO:
            return [ARCHIVO_UNICO[liga]]
        hoy = date.today()
        arranque = hoy.year if hoy.month >= 7 else hoy.year - 1
        nombres = []
        for i in range(3):
            a = arranque - i
            nombres.append(f"season-{str(a)[2:]}{str(a + 1)[2:]}.csv")
        return nombres

    # ------------------------------------------------------------
    def _leer_propio(self, ruta):
        #Lo que ya hay en datos_historicos/<liga>.csv.
        #Devuelve (filas, claves_normalizadas, ultima_fecha).
        filas, claves, ultima = [], set(), ""
        if not os.path.exists(ruta):
            return filas, claves, ultima
        try:
            with open(ruta, encoding="utf-8", errors="replace", newline="") as fh:
                for fila in csv.DictReader(fh):
                    valores = [(fila.get(c) or "").strip() for c in api_historico.COLUMNAS]
                    if not valores[0]:
                        continue
                    filas.append(valores)
                    claves.add(self._clave(valores[0], valores[1], valores[2]))
                    if valores[0] > ultima:
                        ultima = valores[0]
        except OSError:
            pass
        return filas, claves, ultima

    # ------------------------------------------------------------
    def _clave(self, fecha, local, visitante):
        #Los nombres se normalizan para el cruce: el espejo escribe
        #"Nott'm Forest" donde el archivo grande escribe "Nottm Forest", y sin
        #normalizar se colarian los mismos partidos dos veces. Un partido
        #duplicado pesa el doble en el ajuste y deforma al equipo.
        return (fecha,
                api_historico.normalizar(local),
                api_historico.normalizar(visitante))

    # ------------------------------------------------------------
    def _filas_del_espejo(self, texto, claves, ultima):
        #Traduce el CSV de football-data.co.uk al esquema de COLUMNAS.
        #
        #SOLO SE AGREGA LO QUE VA DESPUES DEL ULTIMO PARTIDO QUE YA HAY.
        #Esta regla es la que evita duplicar historia, y no es teorica: las dos
        #fuentes fechan distinto los partidos de Brasil (un partido de las
        #21:30 de Sao Paulo cae al dia siguiente en UTC), asi que cruzar por
        #nombre y fecha dejaba pasar cientos de partidos repetidos. Un partido
        #duplicado pesa el doble en el ajuste y deforma al equipo sin que se
        #vea por ninguna parte.
        #
        #Este comando sirve para completar la cola, no para reconciliar el
        #pasado: lo viejo ya esta y se respeta tal cual.
        filas = []
        lector = csv.DictReader(io.StringIO(texto.lstrip("\ufeff")))
        for fila in lector:
            fecha = self._fecha(fila.get("Date"))
            if not fecha or (ultima and fecha <= ultima):
                continue
            local = (fila.get("HomeTeam") or fila.get("Home") or "").strip()
            visitante = (fila.get("AwayTeam") or fila.get("Away") or "").strip()
            if not local or not visitante or local == visitante:
                continue
            gl = (fila.get("FTHG") or fila.get("HG") or "").strip()
            gv = (fila.get("FTAG") or fila.get("AG") or "").strip()
            if not gl or not gv:
                continue
            clave = self._clave(fecha, local, visitante)
            if clave in claves:
                continue
            claves.add(clave)

            cl = ce = cv = ""
            for a, b, c in CUOTAS_POSIBLES:
                x, y, z = ((fila.get(a) or "").strip(), (fila.get(b) or "").strip(),
                           (fila.get(c) or "").strip())
                if x and y and z:
                    cl, ce, cv = x, y, z
                    break
            mas = menos = ""
            for a, b in MAS_MENOS_POSIBLES:
                x, y = (fila.get(a) or "").strip(), (fila.get(b) or "").strip()
                if x and y:
                    mas, menos = x, y
                    break

            def dato(nombre):
                return (fila.get(nombre) or "").strip()

            filas.append([
                fecha, local, visitante, gl, gv,
                cl, ce, cv, mas, menos,
                dato("HS"), dato("AS"), dato("HST"), dato("AST"),
                dato("HC"), dato("AC"),
            ])
        return filas

    # ------------------------------------------------------------
    def _fecha(self, valor):
        #football-data.co.uk escribe dd/mm/yyyy y a veces dd/mm/yy
        texto = (valor or "").strip()
        for formato in ("%d/%m/%Y", "%d/%m/%y"):
            try:
                return datetime.strptime(texto, formato).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return ""

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