#Ajusta el motor para cada liga y guarda los parametros en base de datos.
#
#   python manage.py ajustar_motor
#   python manage.py ajustar_motor --liga PD
#   python manage.py ajustar_motor --liga PD --temporadas 3
#
#COSTE EN CUOTA: una peticion a football-data.org por liga y temporada.
#Con 9 ligas y 2 temporadas son 18 peticiones. El plan gratuito permite 10 por
#minuto, por eso el comando espera entre liga y liga.
#
#Cada cuanto ejecutarlo: UNA VEZ AL DIA sobra, o despues de cada jornada. Las
#fuerzas de un equipo no cambian entre el jueves y el viernes, y reajustar mas
#seguido solo gasta cuota sin mejorar nada.
import math
import time
from django.core.management.base import BaseCommand
from analizador.api_datos import LIGAS
from analizador.models import AjusteMotor
from analizador import motor_datos

class Command(BaseCommand):
    help="Ajusta Dixon-Coles y Elo de cada liga y guarda los parametros."

    def add_arguments(self,parser):
        parser.add_argument("--liga",type=str,default=None,
            help="Codigo de una liga concreta (PD, PL, SA, BL1, FL1, DED, PPL, BSA, CL).")
        parser.add_argument("--temporadas",type=int,default=2,
            help="Cuantas temporadas hacia atras usar. Mas temporadas = mejor ajuste pero mas peticiones.")
        parser.add_argument("--espera",type=float,default=7.0,
            help="Segundos de espera entre ligas para no agotar la cuota por minuto.")
        parser.add_argument("--afinar",action="store_true",
            help="Busca el decaimiento y la regularizacion optimos de CADA liga con sus propios datos. NO gasta API, pero tarda ~40s por liga. Correr una vez al mes.")

    def handle(self,*args,**opciones):
        ligas=[opciones["liga"]] if opciones["liga"] else list(LIGAS.keys())
        temporadas=max(1,opciones["temporadas"])
        espera=max(0.0,opciones["espera"])
        afinar=opciones["afinar"]
        ok=0
        fallos=[]

        self.stdout.write("")
        self.stdout.write(f"Ajustando {len(ligas)} liga(s) con {temporadas} temporada(s)...")
        if afinar:
            self.stdout.write("Modo AFINADO: se buscan los parametros optimos de cada liga.")
            self.stdout.write("No gasta API, pero tarda cerca de 40 segundos por liga.")
        self.stdout.write("")

        for i,liga in enumerate(ligas):
            if liga not in LIGAS:
                self.stderr.write(self.style.ERROR(f"  {liga}: codigo desconocido"))
                fallos.append(liga)
                continue

            etiqueta=f"{liga} ({LIGAS[liga]})"
            self.stdout.write(f"  {etiqueta:<28} ",ending="")

            #Si ya se afino esta liga antes, se reutilizan sus parametros en
            #vez de volver a los de fabrica. Afinar una vez y perderlo en el
            #siguiente ajuste diario no tendria ningun sentido.
            xi=ridge=None
            if not afinar:
                previo=AjusteMotor.objects.filter(liga=liga).first()
                if previo and previo.parametros:
                    xi=previo.parametros.get("xi")
                    ridge=previo.parametros.get("ridge")

            ajuste,tabla,mapa,error,info=motor_datos.construir_ajuste(
                liga,temporadas,xi=xi,ridge=ridge,afinar=afinar)

            if error:
                #cuota=se agoto el limite por minuto; red=fallo de conexion;
                #sin_datos=la liga no tiene partidos suficientes todavia
                self.stdout.write(self.style.WARNING(f"sin datos ({error})"))
                fallos.append(liga)
            else:
                #El mapa de ids viaja dentro de parametros: asi un equipo que
                #cambia de nombre corto entre temporadas no se parte en dos.
                parametros=ajuste.a_dict()
                parametros["mapa_ids"]=mapa
                if info and info.get("afinado"):
                    parametros["xi"]=info["xi"]
                    parametros["ridge"]=info["ridge"]
                elif xi is not None and ridge is not None:
                    parametros["xi"]=xi
                    parametros["ridge"]=ridge
                AjusteMotor.objects.update_or_create(
                    liga=liga,
                    defaults={
                        "parametros":parametros,
                        "elo":tabla.a_dict(),
                        "partidos_usados":ajuste.partidos_usados,
                        "temporadas":temporadas,
                    },
                )
                self.stdout.write(self.style.SUCCESS(
                    f"{ajuste.partidos_usados:>4} partidos | "
                    f"media {math.exp(ajuste.mu):.2f} goles | "
                    f"local x{math.exp(ajuste.ventaja_local):.2f} | "
                    f"rho {ajuste.rho:+.3f}"))
                ok+=1

                if afinar and info:
                    if info.get("afinado"):
                        self.stdout.write(self.style.SUCCESS(
                            f"      afinado: memoria {info['vida_media_dias']:.0f} dias "
                            f"(xi {info['xi']:.4f}, ridge {info['ridge']:.3f}) | "
                            f"log-perdida {info['log_perdida_fabrica']:.4f} -> "
                            f"{info['log_perdida_mejor']:.4f}  ({info['mejora']:+.4f})"))
                    else:
                        self.stdout.write(f"      sin afinar: {info.get('motivo','')}")

            if i<len(ligas)-1 and espera:
                time.sleep(espera)

        self.stdout.write("")
        if ok:
            self.stdout.write(self.style.SUCCESS(f"Listo: {ok} liga(s) ajustada(s)."))
        if fallos:
            self.stdout.write(self.style.WARNING(f"Sin datos: {', '.join(fallos)}"))
            self.stdout.write("Si el error es 'cuota', espera un minuto y vuelve a correrlo:")
            self.stdout.write("las ligas que si se ajustaron quedan guardadas y no se repiten.")
        self.stdout.write("")