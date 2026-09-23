#CALIBRACION — que un 70% signifique de verdad 70%.
#
#Un modelo puede tener buen "olfato" (ordena bien los partidos) y a la vez
#mentir en el numero: decir 75% cuando la realidad de esos casos es 62%. Eso es
#exactamente lo que hace que un analizador "no se sienta real". El olfato y la
#sinceridad del numero son dos cosas distintas y se arreglan por separado.
#
#Aqui se arregla la sinceridad con la TEMPERATURA: un solo parametro T que
#estira o encoge la confianza, p_nueva ∝ p^(1/T). T>1 = el modelo era
#demasiado atrevido y se le baja el humo; T<1 = era demasiado tibio. Un solo
#parametro es la unica opcion segura: con muchos parametros lo unico que se
#aprende es el ruido del propio historial.
import math



# ============================================================
#  TEMPERATURA (para el 1X2 y cualquier mercado de varias salidas)
# ============================================================
def aplicar_temperatura(probabilidades, t):
    if t is None or abs(t - 1.0) < 1e-6:
        return dict(probabilidades)
    inv = 1.0 / max(0.25, min(4.0, float(t)))
    crudo = {k: max(1e-12, v) ** inv for k, v in probabilidades.items()}
    total = sum(crudo.values())
    return {k: v / total for k, v in crudo.items()}


def _perdida(casos, t):
    total = 0.0
    for c in casos:
        p = aplicar_temperatura(c["probabilidades"], t)
        total -= math.log(max(1e-9, p.get(c["real"], 0.0)))
    return total / len(casos) if casos else None


def _desvio(casos, t):
    #Error de calibracion: cuanto se aleja lo prometido de lo que paso.
    from analizador.motor import evaluacion
    return evaluacion.error_calibracion(
        [{"probabilidades": aplicar_temperatura(c["probabilidades"], t),
          "real": c["real"]} for c in casos])


def _buscar_t(casos, objetivo=None):
    #POR QUE SE BUSCA POR CALIBRACION Y NO POR LOG-PERDIDA:
    #
    #Antes esta funcion devolvia la temperatura que minimizaba la log-perdida,
    #que es lo que dice el manual. Medido de verdad sobre ocho ligas, esa
    #temperatura se pasaba SIEMPRE de frenada: el modelo base se quedaba corto
    #entre 0.2 y 4 puntos, y despues de aplicarla se pasaba entre 0.5 y 5.8.
    #En la Premier el error de calibracion iba de 0.011 a 0.060.
    #
    #No es contradictorio: la log-perdida premia afinar la probabilidad y se
    #puede ganar afinando de mas, porque lo que pierde en los partidos donde
    #se pasa lo recupera en los muchos partidos faciles. La calibracion mide
    #otra cosa: si el numero que se le ENSEÑA al usuario se cumple.
    #
    #Este proyecto vende probabilidades. Si en pantalla dice 62%, esa es la
    #promesa. Asi que la temperatura apunta a la calibracion y la log-perdida
    #se queda de vigilante, no de objetivo.
    medir = objetivo or _desvio
    mejor_t, mejor = 1.0, medir(casos, 1.0)
    if mejor is None:
        return 1.0
    t = 0.55
    while t <= 1.80001:
        v = medir(casos, t)
        if v is not None and v < mejor:
            mejor_t, mejor = t, v
        t += 0.05
    paso = 0.025
    for _ in range(6):
        for cand in (mejor_t - paso, mejor_t + paso):
            if 0.5 <= cand <= 2.0:
                v = medir(casos, cand)
                if v is not None and v < mejor:
                    mejor_t, mejor = cand, v
        paso /= 2.0
    return mejor_t


#Minimo de partidos para tocar la temperatura.
#
#POR QUE 600 Y NO 60: se midio. Con una sola temporada (306-380 partidos) la
#validacion cruzada aprueba temperaturas que despues estropean la temporada
#siguiente, y no es un fallo de la validacion: los 5 pliegues salen todos de
#la MISMA temporada, asi que comprueban contra partidos parecidos y no ven el
#cambio de una temporada a otra. Con dos temporadas (600+) la comprobacion ya
#atraviesa ese cambio y las temperaturas malas se caen solas.
MINIMO_TEMPERATURA = 600


def ajustar_temperatura(historial, minimo=MINIMO_TEMPERATURA, pliegues=5, margen=0.002,
                        margen_ece=0.005):
    #historial: lista de {"probabilidades": {...}, "real": clave}
    #
    #REGLA IMPORTANTE: la temperatura NO se aplica solo porque mejore los
    #partidos con los que se calculo. Eso es trampa (siempre mejora, por
    #construccion). Se valida con VALIDACION CRUZADA de 5 pliegues: el
    #historial se parte en 5, se calcula la temperatura con 4 y se comprueba
    #en el que se dejo fuera, cinco veces. Solo si mejora en el conjunto de
    #partidos no vistos, y por un margen que no sea ruido, se aplica.
    #
    #Un solo corte 70/30 NO basta: probado, deja pasar temperaturas que luego
    #empeoran el modelo. Con 5 pliegues cada partido se usa una vez como
    #prueba y cuatro como entrenamiento, y el resultado deja de depender de
    #donde cayo el corte.
    #
    #Un modelo bien calibrado que se deja en paz es mejor que uno "arreglado"
    #con el ruido de 40 partidos.
    #
    #SEGUNDA CONDICION, Y NO ES UN DETALLE: no basta con que baje la
    #log-perdida. Se comprobo midiendo de verdad: hay ligas donde la
    #temperatura mejoraba la log-perdida y AL MISMO TIEMPO empeoraba la
    #calibracion (en la Premier el error de calibracion pasaba de 0.020 a
    #0.067). Es posible porque la log-perdida premia afinar la probabilidad y
    #la calibracion mide otra cosa: si el numero que se anuncia se cumple.
    #
    #Para un producto que vende probabilidades, empeorar la calibracion para
    #ganar unas milesimas de log-perdida es el peor negocio posible: el
    #usuario ve "62%" y esa es la promesa que hay que cumplir. Asi que la
    #temperatura solo se aplica si mejora la log-perdida Y NO estropea la
    #calibracion, las dos cosas medidas en partidos no vistos.
    casos = [c for c in historial if c.get("probabilidades") and c.get("real")]
    if len(casos) < minimo:
        return 1.0, {"partidos": len(casos), "aplicada": False,
                     "motivo": f"hacen falta al menos {minimo} partidos "
                               f"(hay {len(casos)}): con menos, recalibrar es adivinar"}

    def con_freno(t_bruta, n_entren):
        #Freno por tamaño de muestra: con 80 partidos se aplica la mitad del
        #ajuste, con 500 casi todo. Nunca el 100% de golpe.
        peso = n_entren / (n_entren + 80.0)
        return 1.0 + peso * (t_bruta - 1.0)

    #--- validacion cruzada ---
    n = len(casos)
    perdida_con = 0.0
    perdida_sin = 0.0
    fuera_con, fuera_sin = [], []
    for k in range(pliegues):
        prueba = [c for i, c in enumerate(casos) if i % pliegues == k]
        entren = [c for i, c in enumerate(casos) if i % pliegues != k]
        if not prueba or len(entren) < 20:
            continue
        t_k = con_freno(_buscar_t(entren), len(entren))
        perdida_con += _perdida(prueba, t_k) * len(prueba)
        perdida_sin += _perdida(prueba, 1.0) * len(prueba)
        #Se guardan las predicciones del pliegue que se dejo fuera, con y sin
        #temperatura, para poder medir la calibracion sobre partidos no vistos.
        for c in prueba:
            fuera_con.append({
                "probabilidades": aplicar_temperatura(c["probabilidades"], t_k),
                "real": c["real"]})
            fuera_sin.append({
                "probabilidades": c["probabilidades"], "real": c["real"]})
    perdida_con /= n
    perdida_sin /= n

    from analizador.motor import evaluacion
    ece_con = evaluacion.error_calibracion(fuera_con) if fuera_con else 1.0
    ece_sin = evaluacion.error_calibracion(fuera_sin) if fuera_sin else 0.0

    #Manda la calibracion; la log-perdida solo tiene derecho a veto si se
    #estropea de verdad. Al reves de como estaba antes.
    mejora_calibracion = ece_con < ece_sin - margen_ece
    no_daña_perdida = perdida_con <= perdida_sin + margen

    if not (mejora_calibracion and no_daña_perdida):
        if not mejora_calibracion:
            motivo = (f"la calibracion no mejoro en validacion cruzada "
                      f"({ece_sin:.4f} -> {ece_con:.4f}): se deja como esta")
        else:
            motivo = (f"calibraba mejor pero empeoraba la log-perdida "
                      f"({perdida_sin:.4f} -> {perdida_con:.4f}): no se aplica")
        return 1.0, {
            "partidos": n, "aplicada": False,
            "log_perdida_cruzada_sin": perdida_sin,
            "log_perdida_cruzada_con": perdida_con,
            "ece_cruzado_sin": ece_sin,
            "ece_cruzado_con": ece_con,
            "motivo": motivo,
        }

    #--- pasa la validacion: se reajusta con todo el historial y se aplica ---
    t_final = con_freno(_buscar_t(casos), n)
    return t_final, {
        "partidos": n,
        "temperatura_aplicada": t_final,
        "log_perdida_cruzada_sin": perdida_sin,
        "log_perdida_cruzada_con": perdida_con,
        "ece_cruzado_sin": ece_sin,
        "ece_cruzado_con": ece_con,
        "mejora": perdida_sin - perdida_con,
        "aplicada": True,
    }
