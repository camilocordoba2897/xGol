#LA RETROALIMENTACION. Este es el comando que hace que el motor mejore solo.
#
#   python manage.py evaluar_motor
#   python manage.py evaluar_motor --liga PD
#   python manage.py evaluar_motor --maximo 20
#
#Que hace, en orden:
#  1. Busca los pronosticos guardados de partidos que YA se jugaron y les pone
#     el resultado real.
#  2. Con ese historial recalcula cuanto vale la opinion de cada fuente.
#  3. Recalcula la calibracion, y la aplica SOLO si demuestra que mejora en
#     partidos que no uso para calcularla.
#  4. Imprime el boletin de notas del motor.
#
#Nada de esto funciona si los pronosticos no se guardaron ANTES del partido.
#Por eso motor_vistas guarda cada pronostico al emitirlo, y no deja
#sobrescribirlo. Sin eso, medirse seria hacerse trampa al solitario.
#
#COSTE EN CUOTA: una peticion por partido pendiente de resultado (topada con
#--maximo). Ejecutalo una vez al dia, despues de ajustar_motor.
from django.core.management.base import BaseCommand
from analizador.api_datos import resultado_partido
from analizador.models import PesosMotor,PrediccionMotor
from analizador.motor import calibracion,combinacion,evaluacion

def _resultado(gl,gv):
    if gl>gv:
        return "local"
    if gl==gv:
        return "empate"
    return "visitante"

class Command(BaseCommand):
    help="Evalua los pronosticos guardados y reaprende pesos y calibracion."

    def add_arguments(self,parser):
        parser.add_argument("--liga",type=str,default=None,
            help="Codigo de una liga concreta. Por defecto, todas.")
        parser.add_argument("--maximo",type=int,default=8,
            help="Cuantos resultados pedir a la API por tanda (10 por minuto en el plan gratuito).")

    def handle(self,*args,**opciones):
        # ---------- 1. poner resultados a lo que ya se jugo ----------
        pendientes=PrediccionMotor.objects.filter(evaluado=False)
        if opciones["liga"]:
            pendientes=pendientes.filter(liga=opciones["liga"])
        pendientes=list(pendientes.order_by("creado")[:max(1,opciones["maximo"])])

        nuevos=0
        sin_terminar=0
        for fila in pendientes:
            dato,error=resultado_partido(fila.id_partido)
            if error:
                continue
            if not dato or not dato.get("terminado"):
                sin_terminar+=1
                continue
            fila.goles_local=dato["gf"]
            fila.goles_visitante=dato["gc"]
            fila.resultado=_resultado(dato["gf"],dato["gc"])
            fila.evaluado=True
            fila.save(update_fields=["goles_local","goles_visitante","resultado","evaluado"])
            nuevos+=1

        self.stdout.write("")
        self.stdout.write(f"Resultados nuevos incorporados: {nuevos}"
                          f"   (pendientes de jugarse: {sin_terminar})")

        # ---------- 2 y 3. reaprender por liga ----------
        if opciones["liga"]:
            ligas=[opciones["liga"]]
        else:
            ligas=list(PrediccionMotor.objects.filter(evaluado=True)
                       .values_list("liga",flat=True).distinct())

        if not ligas:
            self.stdout.write("Aun no hay ninguna prediccion evaluada. Vuelve cuando")
            self.stdout.write("se hayan jugado los partidos que ya pronosticaste.")
            self.stdout.write("")
            return

        for liga in ligas:
            filas=list(PrediccionMotor.objects
                       .filter(liga=liga,evaluado=True)
                       .exclude(resultado="")
                       .order_by("creado"))
            if len(filas)<10:
                self.stdout.write(f"  {liga}: solo {len(filas)} partidos evaluados, "
                                  f"aun no hay con que aprender.")
                continue

            historial=[{"fuentes":f.por_fuente or {},"real":f.resultado}
                       for f in filas if f.por_fuente]
            #Se arranca desde los pesos que la liga YA tenga, no desde los de
            #fabrica. Si no, la primera vez que se corra esto con 15 partidos
            #reales se borraria lo aprendido con miles de partidos historicos:
            #optimizar_pesos devuelve el punto de partida cuando hay pocos
            #datos, y ese punto de partida debe ser lo mejor que ya sabemos.
            previos=PesosMotor.objects.filter(liga=liga).first()
            arranque=(previos.pesos if previos and previos.pesos else None)
            if historial:
                pesos,info=combinacion.optimizar_pesos(historial,pesos_iniciales=arranque)
            else:
                pesos,info=dict(arranque or combinacion.PESOS_POR_DEFECTO),{"movido":False}

            casos=[{"probabilidades":{"local":f.prob_local,
                                      "empate":f.prob_empate,
                                      "visitante":f.prob_visitante},
                    "real":f.resultado,
                    "cuotas":f.cuotas or {}} for f in filas]

            temperatura,info_cal=calibracion.ajustar_temperatura(
                [{"probabilidades":c["probabilidades"],"real":c["real"]} for c in casos])

            #Tramos para mercados de si/no, usando "mas de 2.5 goles" como guia
            hist_25=[]
            for f in filas:
                try:
                    p=f.mercados["totales"]["2.5"]["mas"]
                except (KeyError,TypeError):
                    continue
                if f.goles_local is None or f.goles_visitante is None:
                    continue
                hist_25.append({"probabilidad":p,
                                "acierto":(f.goles_local+f.goles_visitante)>2.5})
            tramos=calibracion.construir_tramos(hist_25) if hist_25 else {}

            informe=evaluacion.informe(casos,liga)
            apuestas=evaluacion.rendimiento_apuestas(casos)

            PesosMotor.objects.update_or_create(
                liga=liga,
                defaults={
                    "pesos":pesos,
                    "temperatura":temperatura,
                    "tramos":tramos,
                    "partidos_evaluados":len(casos),
                    "log_perdida":informe["log_perdida"],
                    "rps":informe["rps"],
                    "acierto":informe["acierto"],
                    "ece":informe["ece"],
                },
            )

            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS(f"  ===== {liga} ====="))
            self.stdout.write(f"  partidos evaluados  : {len(casos)}")
            self.stdout.write(f"  log-perdida         : {informe['log_perdida']:.4f}")
            self.stdout.write(f"      referencias -> 1.0986 no saber nada | 1.0300 solo localia")
            self.stdout.write(f"                     0.9900 modelo decente | 0.9600 el mercado")
            self.stdout.write(f"  RPS                 : {informe['rps']:.4f}   (0.19-0.21 es bueno)")
            self.stdout.write(f"  acierto             : {informe['acierto']*100:.1f}%   (50-55% es lo normal en 1X2)")
            self.stdout.write(f"  error de calibracion: {informe['ece']:.4f}   (por debajo de 0.03 esta bien)")
            self.stdout.write("")
            legible=" | ".join(f"{k} {v:.3f}" for k,v in sorted(pesos.items()))
            self.stdout.write(f"  pesos               : {legible}")
            if not info.get("movido"):
                self.stdout.write(f"      {info.get('motivo','sin cambios')}")
            self.stdout.write(f"  temperatura         : {temperatura:.3f} "
                              f"({'aplicada' if info_cal.get('aplicada') else 'NO aplicada'})")
            if not info_cal.get("aplicada") and info_cal.get("motivo"):
                self.stdout.write(f"      {info_cal['motivo']}")
            if apuestas["apuestas"]:
                self.stdout.write("")
                self.stdout.write(f"  apuestas con valor  : {apuestas['apuestas']} | "
                                  f"ROI {apuestas['roi']*100:+.2f}% | "
                                  f"acierto {apuestas['acierto']*100:.1f}%")

        self.stdout.write("")
        self.stdout.write("Listo.")
        self.stdout.write("")