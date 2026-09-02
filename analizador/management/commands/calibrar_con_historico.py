#APRENDER DE LA HISTORIA. Este es el comando que faltaba.
#
#   python manage.py calibrar_con_historico
#   python manage.py calibrar_con_historico --liga PD
#   python manage.py calibrar_con_historico --temporadas-prueba 3
#
#EL PROBLEMA QUE RESUELVE:
#  evaluar_motor aprende los pesos de tus propios pronosticos ya jugados. Es lo
#  correcto, pero al empezar tienes cero: habria que esperar media temporada
#  para saber si el motor sirve, y mientras tanto funciona con los pesos de
#  fabrica sin que nadie sepa si son buenos.
#
#  Ya no hace falta esperar. El historico trae 14.000 partidos CON CUOTAS y con
#  resultado. Eso es exactamente lo que evaluar_motor necesita, solo que del
#  pasado. Este comando se lo da y escribe en la MISMA tabla (PesosMotor), asi
#  que el motor lo usa igual, sin tocar nada mas.
#
#COMO EVITA HACERSE TRAMPA:
#  Aqui es facil engañarse solo. Si se ajusta el motor con TODOS los partidos y
#  despues se mide sobre esos mismos, el resultado sale precioso y no significa
#  nada: el motor ya conocia el marcador.
#
#  Por eso se avanza temporada por temporada. Para medir la temporada 2024 se
#  ajusta el motor SOLO con lo anterior a 2024 y se pronostica a ciegas. Luego
#  se repite con 2023, con 2022. Cada pronostico se hace sin haber visto nunca
#  ese partido. Es lento, pero es la unica forma de que el numero final sea
#  verdad.
#
#COSTE EN CUOTA DE API: CERO. Todo sale de los archivos locales.
#TIEMPO: alrededor de un minuto por liga.
import time

from django.core.management.base import BaseCommand

from analizador import api_historico, motor_datos
from analizador.api_datos import LIGAS
from analizador.models import PesosMotor
from analizador.motor import calibracion, combinacion, elo, evaluacion, nucleo, tasas

MINIMO_PARA_APRENDER = 200


class Command(BaseCommand):
    help = "Aprende pesos y calibracion con el historico, sin gastar cuota de API."

    def add_arguments(self, parser):
        parser.add_argument("--liga", type=str, default=None,
            help="Codigo de una liga concreta. Por defecto, todas las descargadas.")
        parser.add_argument("--temporadas-prueba", type=int, default=3,
            help="Cuantas temporadas recientes usar como examen. Mas temporadas = "
                 "medida mas fiable pero mas lento.")
        parser.add_argument("--simular", action="store_true",
            help="Calcula y muestra todo, pero NO guarda nada en la base de datos.")

    def handle(self, *args, **opciones):
        descargadas = api_historico.ligas_descargadas()
        if not descargadas:
            self.stderr.write(self.style.ERROR("No hay historico descargado."))
            self.stdout.write("Corre primero:  python manage.py descargar_historico")
            return

        ligas = [opciones["liga"]] if opciones["liga"] else descargadas
        n_prueba = max(1, opciones["temporadas_prueba"])
        simular = opciones["simular"]

        self.stdout.write("")
        if simular:
            self.stdout.write(self.style.WARNING("MODO SIMULACION: no se guarda nada."))
        self.stdout.write(f"Aprendiendo de {len(ligas)} liga(s), "
                          f"examen sobre {n_prueba} temporada(s).")
        self.stdout.write("Esto no gasta cuota de API. Tarda alrededor de un minuto por liga.")
        self.stdout.write("")

        for liga in ligas:
            self._una_liga(liga, n_prueba, simular)

        self.stdout.write("")
        self.stdout.write("Listo.")
        if not simular:
            self.stdout.write("Los pesos quedaron guardados y el motor ya los esta usando.")
        self.stdout.write("")

    # ------------------------------------------------------------
    def _una_liga(self, liga, n_prueba, simular):
        inicio = time.time()
        self.stdout.write(self.style.SUCCESS(f"  ===== {liga} ({LIGAS.get(liga, liga)}) ====="))

        #Los nombres oficiales vienen cacheados de verificar_historico. Si no
        #estan, se piden: una sola peticion, y solo la primera vez.
        oficiales, _ = motor_datos.equipos_oficiales(liga)
        partidos, _, error = api_historico.historial(
            liga, temporadas=None, nombres_oficiales=(oficiales or None))
        if error:
            self.stdout.write(self.style.WARNING(f"  sin historico ({error})"))
            return

        temporadas = sorted({p["temporada"] for p in partidos})
        if len(temporadas) < n_prueba + 2:
            self.stdout.write(self.style.WARNING(
                f"  solo hay {len(temporadas)} temporadas: hacen falta al menos "
                f"{n_prueba + 2} para examinar sin hacerse trampa."))
            return
        examen = temporadas[-n_prueba:]

        #--- avance temporada por temporada ---
        historial_fuentes = []
        casos_calibracion = []
        historial_25 = []
        for temporada in examen:
            #El motor solo ve lo ANTERIOR a la temporada que va a pronosticar.
            entreno = [p for p in partidos if p["temporada"] < temporada]
            if len(entreno) < MINIMO_PARA_APRENDER:
                continue
            ajuste = tasas.ajustar(entreno)
            tabla = elo.calcular(entreno)

            for p in partidos:
                if p["temporada"] != temporada or not p.get("cuotas"):
                    continue
                casas = [{"casa": "historico", **p["cuotas"]}]
                try:
                    r = nucleo.pronosticar(
                        p["local"], p["visitante"],
                        ajuste_liga=ajuste, tabla_elo=tabla, casas=casas,
                        prob_mercado_mas_25=p.get("prob_mas_25"))
                except Exception:
                    continue
                if not r.fuentes or "mercado" not in r.fuentes:
                    continue

                gl, gv = p["goles_local"], p["goles_visitante"]
                real = "local" if gl > gv else ("empate" if gl == gv else "visitante")
                historial_fuentes.append({"fuentes": r.fuentes, "real": real})
                casos_calibracion.append({
                    "probabilidades": r.mercados["1x2"],
                    "real": real,
                    "cuotas": p["cuotas"],
                })
                try:
                    historial_25.append({
                        "probabilidad": r.mercados["totales"]["2.5"]["mas"],
                        "acierto": (gl + gv) > 2.5,
                    })
                except (KeyError, TypeError):
                    pass

        if len(historial_fuentes) < MINIMO_PARA_APRENDER:
            self.stdout.write(self.style.WARNING(
                f"  solo {len(historial_fuentes)} partidos utilizables: muy pocos "
                f"para aprender sin quedarse con el ruido."))
            return

        #--- aprender ---
        #Se parte de los pesos que ya tenga la liga, no de los de fabrica: si
        #este comando se corre dos veces, la segunda debe seguir desde donde
        #quedo la primera, no empezar de cero.
        previos = PesosMotor.objects.filter(liga=liga).first()
        arranque = (previos.pesos if previos and previos.pesos else None)
        pesos, info = combinacion.optimizar_pesos(historial_fuentes, pesos_iniciales=arranque)
        temperatura, info_cal = calibracion.ajustar_temperatura(
            [{"probabilidades": c["probabilidades"], "real": c["real"]}
             for c in casos_calibracion])
        tramos = calibracion.construir_tramos(historial_25) if historial_25 else {}
        informe = evaluacion.informe(casos_calibracion, liga)

        #--- comparar contra los pesos de fabrica, que es la pregunta real ---
        def perdida(pesos_usados):
            mezcladas = [combinacion.mezclar_probabilidades(c["fuentes"], pesos_usados)
                         for c in historial_fuentes]
            return combinacion.log_perdida(mezcladas, [c["real"] for c in historial_fuentes])

        p_fabrica = perdida(combinacion.PESOS_POR_DEFECTO)
        p_nuevos = perdida(pesos)
        solo_mercado = combinacion.log_perdida(
            [c["fuentes"]["mercado"] for c in historial_fuentes],
            [c["real"] for c in historial_fuentes])

        #--- informe ---
        self.stdout.write(f"  temporadas de examen : {examen}")
        self.stdout.write(f"  partidos pronosticados a ciegas: {len(historial_fuentes)}")
        self.stdout.write("")
        self.stdout.write("  LOG-PERDIDA (menos es mejor):")
        self.stdout.write(f"     sin saber nada          : 1.0986")
        self.stdout.write(f"     solo las cuotas         : {solo_mercado:.4f}")
        self.stdout.write(f"     pesos de fabrica        : {p_fabrica:.4f}")
        marca = "  <-- mejor" if p_nuevos <= min(p_fabrica, solo_mercado) else ""
        self.stdout.write(f"     pesos aprendidos        : {p_nuevos:.4f}{marca}")
        self.stdout.write("")
        self.stdout.write(f"  acierto              : {informe['acierto']*100:.1f}%")
        self.stdout.write(f"  RPS                  : {informe['rps']:.4f}   (0.19-0.21 es bueno)")
        self.stdout.write(f"  error de calibracion : {informe['ece']:.4f}   (bajo 0.03 esta bien)")
        legible = " | ".join(f"{k} {v:.3f}" for k, v in sorted(pesos.items()))
        self.stdout.write(f"  pesos                : {legible}")
        if not info.get("movido"):
            self.stdout.write(f"     {info.get('motivo', 'sin cambios')}")
        self.stdout.write(f"  temperatura          : {temperatura:.3f} "
                          f"({'aplicada' if info_cal.get('aplicada') else 'NO aplicada'})")

        if p_nuevos > p_fabrica:
            #Puede pasar y hay que decirlo, no esconderlo: significa que en esta
            #liga el optimizador no encontro nada mejor que lo que ya habia.
            self.stdout.write(self.style.WARNING(
                "     Los pesos aprendidos NO mejoran a los de fabrica en esta liga."))

        if not simular:
            PesosMotor.objects.update_or_create(
                liga=liga,
                defaults={
                    "pesos": pesos,
                    "temperatura": temperatura,
                    "tramos": tramos,
                    "partidos_evaluados": len(casos_calibracion),
                    "log_perdida": informe["log_perdida"],
                    "rps": informe["rps"],
                    "acierto": informe["acierto"],
                    "ece": informe["ece"],
                },
            )
        self.stdout.write(f"  ({time.time() - inicio:.0f}s)")
        self.stdout.write("")