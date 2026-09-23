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
from analizador.models import AjusteMotor, PesosMotor
from analizador.motor import calibracion, combinacion, elo, evaluacion, nucleo, tasas

MINIMO_PARA_APRENDER = 200

#Se sube cada vez que cambia algo que invalida una calibracion ya guardada
#(como se forma una fuente, como se aprende la temperatura...). El
#mantenimiento automatico ve que la marca no coincide y recalibra solo.
#  2: cuotas de favoritos claros bien leidas, sin la linea de 2.5 que en vivo
#     no existe, temperatura aprendida con los pesos que se usan.
VERSION_CALIBRACION = 2
CLAVE_VERSION = "motor_calibracion_version"


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
        parser.add_argument("--parametros-fabrica", action="store_true",
            help="Ajusta Dixon-Coles con la memoria de fabrica en vez de la afinada "
                 "de cada liga. Solo para comparar con --simular: el motor en vivo "
                 "usa la afinada.")

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

        self.afinados = not opciones["parametros_fabrica"]
        for liga in ligas:
            self._una_liga(liga, n_prueba, simular)

        #La marca solo cuando se calibraron TODAS las ligas y de verdad
        if not simular and not opciones["liga"]:
            from django.core.cache import cache
            cache.set(CLAVE_VERSION, VERSION_CALIBRACION, None)

        self.stdout.write("")
        self.stdout.write("Listo.")
        if not simular:
            self.stdout.write("Los pesos quedaron guardados y el motor ya los esta usando.")
        self.stdout.write("")

    # ------------------------------------------------------------
    @staticmethod
    def _brecha(casos):
        #La comprobacion de calibracion que de verdad importa: comparar la
        #probabilidad que el modelo ANUNCIA con la frecuencia real de aciertos.
        #
        #"Acierta mas" NO es "esta bien calibrado". Un modelo que dice 70% y
        #acierta el 52% esta inflado aunque ese 52% suene bien; y uno que dice
        #40% y acierta el 41% esta bien calibrado aunque acierte menos. Son dos
        #preguntas distintas y hay que responder las dos por separado.
        if not casos:
            return None, None
        anunciada = sum(max(c["probabilidades"].values()) for c in casos) / len(casos)
        aciertos = sum(1 for c in casos
                       if max(c["probabilidades"], key=c["probabilidades"].get) == c["real"])
        return anunciada, aciertos / len(casos)

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

        #El Dixon-Coles del examen usa la MISMA memoria que el motor en vivo:
        #la afinada de esta liga (ajustar_motor --afinar), o la de fabrica si
        #afinar no la mejoro. Comparado a ciegas sobre 5.353 partidos: con
        #cuotas da lo mismo (0.9669 contra 0.9668 de log-perdida) y sin
        #cuotas, que es cuando Dixon-Coles pesa de verdad, mejora (1.0027
        #contra 1.0064; RPS 0.2046 contra 0.2058). Y sobre todo: pesos y
        #temperatura se aprenden para el Dixon-Coles que de verdad se usa.
        xi, ridge = tasas.XI_POR_DEFECTO, tasas.RIDGE_POR_DEFECTO
        if self.afinados:
            fila = AjusteMotor.objects.filter(liga=liga).first()
            parametros = (fila.parametros or {}) if fila else {}
            if parametros.get("xi") is not None and parametros.get("ridge") is not None:
                xi, ridge = parametros["xi"], parametros["ridge"]
        self.stdout.write(f"  memoria del modelo: xi {xi:.4f}, ridge {ridge:.3f}")

        #--- avance temporada por temporada ---
        historial_fuentes = []
        casos_calibracion = []
        historial_25 = []
        for temporada in examen:
            #El motor solo ve lo ANTERIOR a la temporada que va a pronosticar.
            entreno = [p for p in partidos if p["temporada"] < temporada]
            if len(entreno) < MINIMO_PARA_APRENDER:
                continue
            ajuste = tasas.ajustar(entreno, xi=xi, ridge=ridge)
            tabla = elo.calcular(entreno)

            for p in partidos:
                if p["temporada"] != temporada or not p.get("cuotas"):
                    continue
                casas = [{"casa": "historico", **p["cuotas"]}]
                #Sin la cuota de mas/menos 2.5 goles aunque el historico la
                #traiga: en vivo solo se pide el 1X2 a the-odds-api (cada
                #mercado extra gasta otro credito). Si aqui se usara, se
                #mediria y se calibraria un motor distinto al que se despliega.
                try:
                    r = nucleo.pronosticar(
                        p["local"], p["visitante"],
                        ajuste_liga=ajuste, tabla_elo=tabla, casas=casas)
                except Exception:
                    continue
                if not r.fuentes or "mercado" not in r.fuentes:
                    continue

                gl, gv = p["goles_local"], p["goles_visitante"]
                real = "local" if gl > gv else ("empate" if gl == gv else "visitante")
                historial_fuentes.append({"fuentes": r.fuentes, "real": real,
                                          "temporada": temporada})
                casos_calibracion.append({
                    "probabilidades": r.mercados["1x2"],
                    "real": real,
                    "cuotas": p["cuotas"],
                    "temporada": temporada,
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

        # ------------------------------------------------------------
        #  PLIEGUES RODANTES: SE APRENDE CON EL PASADO, SE MIDE EL FUTURO
        #
        #  Antes la temperatura se aprendia sobre los MISMOS partidos sobre los
        #  que despues se medía. El avance temporada por temporada ya evitaba
        #  que el motor viera el marcador, pero la recalibracion si lo veia, y
        #  eso inflaba la ventaja del modelo recalibrado sobre el base.
        #
        #  Ahora se mide temporada por temporada, y para cada una solo se
        #  aprende con las ANTERIORES:
        #
        #     mide 2024  ->  aprende con 2023
        #     mide 2025  ->  aprende con 2023 + 2024
        #
        #  Se gana por los dos lados. Ninguna medida usa datos de su propio
        #  futuro, y aun asi se mide sobre varias temporadas en vez de una, que
        #  es el doble de muestra y por tanto la mitad de ruido.
        # ------------------------------------------------------------
        pliegues = [(examen[i], set(examen[:i])) for i in range(1, len(examen))]

        #Con una sola temporada de examen no hay pasado con que aprender. Se
        #avisa en vez de callarlo: un numero medido sobre sus propios datos no
        #vale igual, y presentarlo como si valiera es peor que no tenerlo.
        #Se arranca SIEMPRE de los pesos de fabrica. Antes se arrancaba de los
        #guardados en la base, pero esos se aprendieron con estas mismas
        #temporadas de examen: medir 2024 partiendo de pesos que ya vieron 2024
        #es colar el futuro por la puerta de atras. Asi, ademas, calibrar dos
        #veces da el mismo resultado en vez de ir acumulandose.
        arranque = None
        tramos = calibracion.construir_tramos(historial_25) if historial_25 else {}

        def _mezclados(casos, pesos_):
            #La temperatura se aprende sobre la mezcla con LOS PESOS QUE SE VAN
            #A USAR. Antes se aprendia sobre la mezcla de fabrica y luego se
            #aplicaba sobre la de pesos aprendidos: otra cosa distinta.
            return [{"probabilidades": combinacion.mezclar_probabilidades(c["fuentes"], pesos_),
                     "real": c["real"]} for c in casos]

        def _sin_mercado(casos):
            #El mismo partido tal como lo veria el motor si no hubiera cuotas
            #(the-odds-api solo publica los partidos cercanos): Dixon-Coles y Elo.
            return [{"fuentes": {k: v for k, v in c["fuentes"].items() if k != "mercado"},
                     "real": c["real"]} for c in casos]

        casos_base, casos_recal, fuentes_medidas, mezclas = [], [], [], []
        #Sin cuotas: sin recalibrar / con la temperatura del mercado (lo que
        #hacia el motor antes) / con su propia temperatura
        sm_t1, sm_tmkt, sm_propia = [], [], []
        medidas = []
        pesos, temperatura, temperatura_sm = None, 1.0, 1.0
        info, info_cal, info_cal_sm = {}, {}, {}

        for medir, aprender in pliegues:
            ap_f = [c for c in historial_fuentes if c["temporada"] in aprender]
            me_f = [c for c in historial_fuentes if c["temporada"] == medir]
            me_c = [c for c in casos_calibracion if c["temporada"] == medir]
            if not ap_f or not me_f:
                continue

            pesos, info = combinacion.optimizar_pesos(ap_f, pesos_iniciales=arranque)
            temperatura, info_cal = calibracion.ajustar_temperatura(_mezclados(ap_f, pesos))
            temperatura_sm, info_cal_sm = calibracion.ajustar_temperatura(
                _mezclados(_sin_mercado(ap_f), pesos))

            for c in _mezclados(_sin_mercado(me_f), pesos):
                sm_t1.append(c)
                sm_tmkt.append({"probabilidades": calibracion.aplicar_temperatura(
                    c["probabilidades"], temperatura), "real": c["real"]})
                sm_propia.append({"probabilidades": calibracion.aplicar_temperatura(
                    c["probabilidades"], temperatura_sm), "real": c["real"]})

            for c_fuentes, c_base in zip(me_f, me_c):
                mezclado = combinacion.mezclar_probabilidades(c_fuentes["fuentes"], pesos)
                mezclas.append(mezclado)
                casos_recal.append({
                    "probabilidades": calibracion.aplicar_temperatura(mezclado, temperatura),
                    "real": c_base["real"],
                    "cuotas": c_base["cuotas"],
                })
            casos_base.extend(me_c)
            fuentes_medidas.extend(me_f)
            medidas.append((medir, sorted(aprender), len(me_c)))

        rodante = bool(medidas)
        if not rodante:
            self.stdout.write(self.style.WARNING(
                "  AVISO: no hay temporadas suficientes para medir sin usar el propio "
                "futuro."))
            self.stdout.write(self.style.WARNING(
                "  Corre con --temporadas-prueba 3 para que la comparacion sea limpia."))
            pesos, info = combinacion.optimizar_pesos(historial_fuentes,
                                                      pesos_iniciales=arranque)
            temperatura, info_cal = calibracion.ajustar_temperatura(
                _mezclados(historial_fuentes, pesos))
            temperatura_sm, info_cal_sm = calibracion.ajustar_temperatura(
                _mezclados(_sin_mercado(historial_fuentes), pesos))
            sm_t1 = _mezclados(_sin_mercado(historial_fuentes), pesos)
            sm_tmkt = [{"probabilidades": calibracion.aplicar_temperatura(
                c["probabilidades"], temperatura), "real": c["real"]} for c in sm_t1]
            sm_propia = [{"probabilidades": calibracion.aplicar_temperatura(
                c["probabilidades"], temperatura_sm), "real": c["real"]} for c in sm_t1]
            casos_base = casos_calibracion
            fuentes_medidas = historial_fuentes
            mezclas = [combinacion.mezclar_probabilidades(c["fuentes"], pesos)
                       for c in historial_fuentes]
            casos_recal = [{
                "probabilidades": calibracion.aplicar_temperatura(m, temperatura),
                "real": c["real"], "cuotas": c["cuotas"],
            } for m, c in zip(mezclas, casos_calibracion)]

        informe = evaluacion.informe(casos_base, liga)

        #--- lo que se DESPLIEGA ---
        #Los pliegues de arriba estiman, sin ver el futuro, que tan bien sale
        #el PROCEDIMIENTO (aprender pesos + temperatura con lo anterior). Para
        #el motor en vivo se repite ese mismo procedimiento con TODAS las
        #temporadas de examen: antes se desplegaba lo del ultimo pliegue, que
        #nunca vio la temporada mas reciente.
        if rodante:
            pesos, info = combinacion.optimizar_pesos(historial_fuentes,
                                                      pesos_iniciales=arranque)
            temperatura, info_cal = calibracion.ajustar_temperatura(
                _mezclados(historial_fuentes, pesos))
            temperatura_sm, info_cal_sm = calibracion.ajustar_temperatura(
                _mezclados(_sin_mercado(historial_fuentes), pesos))

        #--- comparar contra los pesos de fabrica, sobre los partidos medidos ---
        reales = [c["real"] for c in fuentes_medidas]
        p_fabrica = combinacion.log_perdida(
            [combinacion.mezclar_probabilidades(c["fuentes"], combinacion.PESOS_POR_DEFECTO)
             for c in fuentes_medidas], reales)
        #Los pesos aprendidos NO son unos fijos: cada temporada se midio con los
        #que se habian aprendido con las anteriores. Por eso se usa la mezcla
        #que se guardo pliegue a pliegue y no un recalculo con los ultimos.
        p_nuevos = combinacion.log_perdida(mezclas, reales)
        solo_mercado = combinacion.log_perdida(
            [c["fuentes"]["mercado"] for c in fuentes_medidas], reales)

        #--- informe ---
        self.stdout.write(f"  temporadas de examen  : {examen}")
        if rodante:
            for medir, aprender, cuantos in medidas:
                self.stdout.write(
                    f"     mide {medir}  ->  aprende con {aprender}"
                    f"   ({cuantos} partidos medidos)")
            self.stdout.write(
                f"  total medido          : {len(casos_base)} partidos")
            self.stdout.write(
                "  Ninguna temporada se midio con datos de su propio futuro: ni el modelo,")
            self.stdout.write(
                "  ni los pesos, ni la temperatura vieron nunca el partido que pronostican.")
        else:
            self.stdout.write(f"  partidos medidos      : {len(casos_base)}")
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
        self.stdout.write(f"  Brier                : {informe['brier']:.4f}   "
                          f"(0 seria perfecto, 0.667 es no saber nada)")
        self.stdout.write(f"  error de calibracion : {informe['ece']:.4f}   (bajo 0.03 esta bien)")

        #--- MODELO BASE vs MODELO RECALIBRADO, sobre los MISMOS partidos ---
        #
        #Los dos se miden sobre la temporada de medida, que el motor no vio al
        #ajustarse Y que tampoco se uso para aprender los pesos ni la
        #temperatura. Sin esta separacion no se puede afirmar que recalibrar
        #mejore nada: se estaria midiendo la recalibracion con sus propios datos.
        informe_recal = evaluacion.informe(casos_recal, liga)

        self.stdout.write("")
        self.stdout.write("  MODELO BASE vs RECALIBRADO (solo partidos medidos en limpio):")
        self.stdout.write("                        log-perdida   Brier     RPS      ECE    acierto")
        for etiqueta, inf in (("base       ", informe), ("recalibrado", informe_recal)):
            self.stdout.write(
                f"     {etiqueta}        {inf['log_perdida']:.4f}    "
                f"{inf['brier']:.4f}   {inf['rps']:.4f}   {inf['ece']:.4f}   "
                f"{inf['acierto']*100:.1f}%")
        self.stdout.write("     (se guarda el recalibrado: es el que pronostica en vivo)")

        #--- SIN CUOTAS: lo que ve el usuario cuando el partido aun no tiene
        #    cuotas publicadas. Mismos partidos, sin la fuente mercado. ---
        self.stdout.write("")
        self.stdout.write("  SIN CUOTAS (solo Dixon-Coles + Elo, mismos partidos):")
        self.stdout.write("                             log-perdida    RPS      ECE    anuncia  acierta")
        for etiqueta, cs in (("sin recalibrar          ", sm_t1),
                             ("temperatura del mercado ", sm_tmkt),
                             ("temperatura propia      ", sm_propia)):
            if not cs:
                continue
            inf = evaluacion.informe(cs)
            a, o = self._brecha(cs)
            self.stdout.write(
                f"     {etiqueta}  {inf['log_perdida']:.4f}     {inf['rps']:.4f}   "
                f"{inf['ece']:.4f}   {a*100:5.1f}%   {o*100:5.1f}%")
        self.stdout.write(f"     se guarda la propia: {temperatura_sm:.3f} "
                          f"({'aplicada' if info_cal_sm.get('aplicada') else 'NO aplicada'})")

        #Apostar donde el motor ve valor sobre la cuota: se mide si eso gana o
        #pierde plata en temporadas que el motor no habia visto. Por esta
        #medida (ROI muy negativo) el sitio ya no marca "apuestas de valor".
        valor = evaluacion.rendimiento_apuestas(casos_recal, cuota_minima=1.01,
                                                cuota_maxima=1000.0)
        if valor["apuestas"]:
            self.stdout.write(
                f"  apuestas con valor   : {valor['apuestas']} | ROI "
                f"{valor['roi']*100:+.1f}% | acierto {valor['acierto']*100:.1f}%")

        #--- CALIBRACION: lo anunciado contra lo que de verdad pasa ---
        self.stdout.write("")
        self.stdout.write("  CALIBRACION (probabilidad anunciada vs frecuencia observada):")
        for etiqueta, casos in (("base       ", casos_base),
                                ("recalibrado", casos_recal)):
            anunciada, observada = self._brecha(casos)
            if anunciada is None:
                continue
            self.stdout.write(
                f"     {etiqueta}  anuncia {anunciada*100:>5.1f}%  |  "
                f"acierta {observada*100:>5.1f}%  |  "
                f"desfase {(observada - anunciada)*100:+.1f} puntos")
        self.stdout.write("     Un desfase positivo significa que el motor se queda corto "
                          "(es mas fiable de lo que dice);")
        self.stdout.write("     uno negativo, que promete mas de lo que cumple. "
                          "Cerca de cero es lo que se busca.")
        self.stdout.write("")
        legible = " | ".join(f"{k} {v:.3f}" for k, v in sorted(pesos.items()))
        self.stdout.write(f"  pesos                : {legible}")
        if not info.get("movido"):
            self.stdout.write(f"     {info.get('motivo', 'sin cambios')}")
        self.stdout.write(f"  temperatura          : {temperatura:.3f} "
                          f"({'aplicada' if info_cal.get('aplicada') else 'NO aplicada'})")
        if not info_cal.get("aplicada") and info_cal.get("motivo"):
            self.stdout.write(f"     {info_cal['motivo']}")

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
                    "temperatura_sin_mercado": temperatura_sm,
                    "tramos": tramos,
                    #Las metricas son las del RECALIBRADO (pesos aprendidos +
                    #temperatura, cada temporada con lo aprendido de las
                    #anteriores), que es el procedimiento que se despliega.
                    #Antes se guardaban las del modelo BASE (pesos de fabrica,
                    #sin temperatura): el panel describia un motor que no era
                    #el que estaba pronosticando.
                    "partidos_evaluados": len(casos_recal),
                    "log_perdida": informe_recal["log_perdida"],
                    "rps": informe_recal["rps"],
                    "acierto": informe_recal["acierto"],
                    "ece": informe_recal["ece"],
                },
            )
        self.stdout.write(f"  ({time.time() - inicio:.0f}s)")
        self.stdout.write("")