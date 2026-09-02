#REVISION ANTES DE PRESENTAR. Este comando no cambia nada: solo mira y avisa.
#
#   python manage.py verificar_historico
#   python manage.py verificar_historico --liga PD
#
#PARA QUE EXISTE:
#  El unico fallo GRAVE que puede meter el historico es que un equipo no se
#  reconozca como el mismo que ya conoce el proyecto. Cuando eso pasa el motor
#  no se cae ni tira error: trata a ese equipo como "equipo promedio" y
#  devuelve un pronostico plano con toda normalidad. Es el peor tipo de fallo,
#  el que no se ve. Este comando lo saca a la luz.
#
#COSTE EN CUOTA: una peticion a football-data.org por liga, para saber los
#nombres oficiales. Los archivos locales no gastan nada.
#
#Correrlo despues de descargar_historico y ANTES de mostrarle esto a alguien.
import time

from django.core.management.base import BaseCommand

from analizador import api_historico, motor_datos
from analizador.api_datos import LIGAS

EXPLICACION = {
    "sin_archivo": "Falta el archivo. Corre primero:  python manage.py descargar_historico",
    "sin_liga": "Esta liga no esta en el historico (la Champions no: son ligas nacionales).",
    "sin_datos": "El archivo existe pero no trae partidos en ese rango de temporadas.",
}


class Command(BaseCommand):
    help = "Revisa el historico de cada liga y avisa de equipos sin emparejar."

    def add_arguments(self, parser):
        parser.add_argument("--liga", type=str, default=None,
            help="Codigo de una liga concreta. Por defecto, todas las descargadas.")
        parser.add_argument("--temporadas", type=int, default=5,
            help="Cuantas temporadas revisar.")
        parser.add_argument("--espera", type=float, default=8.0,
            help="Segundos entre ligas para no agotar el limite de 10 por minuto de football-data.org.")

    def handle(self, *args, **opciones):
        descargadas = api_historico.ligas_descargadas()
        if not descargadas:
            self.stderr.write(self.style.ERROR(
                "No hay ningun historico descargado todavia."))
            self.stdout.write("Corre primero:  python manage.py descargar_historico")
            return

        ligas = [opciones["liga"]] if opciones["liga"] else descargadas
        temporadas = max(1, opciones["temporadas"])
        espera = max(0.0, opciones["espera"])

        problemas = []
        total_partidos = total_cuotas = 0

        self.stdout.write("")
        self.stdout.write(f"Revisando {len(ligas)} liga(s), {temporadas} temporada(s).")
        self.stdout.write("")

        for i, liga in enumerate(ligas):
            self.stdout.write(f"  {liga} ({LIGAS.get(liga, liga)})")

            #Plantilla COMPLETA de la liga, no los equipos que ya jugaron.
            #En agosto casi nadie ha jugado y la lista sale a medias, y con la
            #lista a medias medio historico no empareja y nadie se entera.
            oficiales, error_org = motor_datos.equipos_oficiales(liga)
            if error_org or not oficiales:
                self.stdout.write(self.style.WARNING(
                    f"      no llego la plantilla ({error_org or 'vacio'})."))
                self.stdout.write(
                    "      Si dice 'cuota', espera un minuto: son 10 peticiones por minuto.")
                problemas.append(liga)
                if i < len(ligas) - 1 and espera:
                    time.sleep(espera)
                continue

            partidos, informe, error = api_historico.historial(
                liga, temporadas=temporadas, nombres_oficiales=oficiales)
            if error:
                self.stdout.write(self.style.WARNING(f"      sin historico ({error})"))
                self.stdout.write(f"      {EXPLICACION.get(error, '')}")
                problemas.append(liga)
                if i < len(ligas) - 1 and espera:
                    time.sleep(espera)
                continue

            cuotas = informe.get("con_cuotas", 0)
            porcentaje = 100.0 * cuotas / max(1, len(partidos))
            total_partidos += len(partidos)
            total_cuotas += cuotas
            self.stdout.write(self.style.SUCCESS(
                f"      {len(partidos):>5} partidos | "
                f"{cuotas} con cuotas ({porcentaje:.0f}%) | "
                f"{informe['desde'][:7]} a {informe['hasta'][:7]}"))

            #LA COMPROBACION QUE IMPORTA, y va al reves de la obvia.
            #Que un equipo del historico no empareje casi nunca es grave: suele
            #ser un descendido. Lo grave es que un equipo que JUEGA HOY se quede
            #sin ni un partido de historia: ese es el que el motor va a tratar
            #como equipo promedio y sobre el que dara un pronostico plano.
            huerfanos = informe.get("oficiales_sin_historia") or []
            self.stdout.write(
                f"      {len(oficiales) - len(huerfanos)} de {len(oficiales)} "
                f"equipos de la plantilla tienen historia")

            #AMBIGUOS: dos equipos oficiales empataron por el mismo nombre del
            #historico y se dejo sin emparejar a proposito. Siempre hay que
            #resolverlo con un alias: si no, ese equipo se queda sin historia.
            ambiguos = informe.get("ambiguos") or {}
            if ambiguos:
                self.stdout.write(self.style.ERROR("      NOMBRES AMBIGUOS (hay que resolverlos):"))
                for bruto, cuales in ambiguos.items():
                    self.stdout.write(f"         '{bruto}' podria ser {' o '.join(cuales)}")
                problemas.append(liga)

            if huerfanos:
                #Se separa lo que hay que arreglar de lo que es normal.
                #Un ascendido no tiene historia en esta liga y no hay nada que
                #hacer: es correcto. Un equipo que SI aparece en los datos con
                #otro nombre es un alias que falta. La diferencia se ve en el
                #parecido de su mejor candidato.
                del_historico = sorted({p["local"] for p in partidos} |
                                       {p["visitante"] for p in partidos})
                arreglables, ascendidos = [], []
                for equipo in huerfanos:
                    mejores = api_historico.candidatos(oficiales.get(equipo, equipo),
                                                       del_historico)
                    if mejores and mejores[0][0] >= 0.25:
                        arreglables.append((equipo, mejores))
                    else:
                        ascendidos.append(equipo)

                if arreglables:
                    self.stdout.write(self.style.ERROR(
                        "      FALTA UN ALIAS para estos (si aparecen en los datos):"))
                    for equipo, mejores in arreglables:
                        opciones = ", ".join(f"'{n}' ({p:.2f})" for p, n in mejores)
                        self.stdout.write(f"         {equipo}  <-  {opciones}")
                    self.stdout.write(
                        "      Agregalos a ALIAS_HISTORICO en analizador/api_historico.py")
                    problemas.append(liga)

                if ascendidos:
                    self.stdout.write(self.style.WARNING(
                        f"      Recien ascendidos, sin historia en esta liga: "
                        f"{', '.join(ascendidos)}"))
                    self.stdout.write(
                        "      Es correcto y no se puede arreglar: no han jugado aqui.")
                    self.stdout.write(
                        "      El motor les dara confianza baja hasta que acumulen partidos.")

            sin_emparejar = informe.get("sin_emparejar") or []
            if sin_emparejar:
                self.stdout.write(
                    f"      ({len(sin_emparejar)} equipos del historico ya no estan "
                    f"en la liga: es normal)")

            if i < len(ligas) - 1 and espera:
                time.sleep(espera)

        self.stdout.write("")
        self.stdout.write(f"Total: {total_partidos} partidos, {total_cuotas} con cuotas.")
        if problemas:
            self.stdout.write(self.style.WARNING(f"Revisar: {', '.join(sorted(set(problemas)))}"))
        else:
            self.stdout.write(self.style.SUCCESS(
                "Todo emparejado. Ya puedes correr:  python manage.py ajustar_motor"))
        self.stdout.write("")