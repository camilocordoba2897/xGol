// ============================================================
//  TARJETA DESTACADA DEL HOME
//
//  Alterna entre dos estados, ninguno de los cuales regala el producto:
//
//    RESUELTO   El partido ya se jugo. Se ve que dijo el motor y que paso,
//               con su ✓ o su ✗. No se regala nada porque ya ocurrio, y es
//               mucho mas convincente que un porcentaje de un partido futuro.
//               Se muestran aciertos Y fallos: una tarjeta que solo enseñara
//               aciertos seria mentira, y ademas se nota enseguida.
//
//    BLOQUEADO  El proximo partido. Equipos, hora y liga; el pronostico
//               detras del muro de suscripcion. Demuestra que el sistema
//               esta vivo sin dar el numero por el que la gente paga.
//
//  IMPORTANTE: este archivo NUNCA recibe porcentajes de partidos por jugar.
//  El filtro esta en el servidor (inicio/api_partidos.py), no aqui. Ocultar
//  un dato en pantalla no sirve de nada si viaja en la respuesta: se lee
//  abriendo las herramientas del navegador.
//
//  Como en la version anterior, este script NO toca #predCard por fuera
//  (ni opacidad ni transform) para no romper la animacion card-float del CSS.
//  Solo reemplaza lo de dentro.
//
//  Los textos salen en el idioma elegido en el home (gettext, del catalogo
//  de traducciones que carga la plantilla antes de este archivo).
// ============================================================
(function() {
  var card = document.getElementById('predCard');
  if (!card) return;

  var URL_DATOS = card.getAttribute('data-url');
  // A donde lleva el boton y si esa persona ya puede ver el pronostico
  // (administrador o plan vigente): lo decide la plantilla, no este script.
  var URL_DESTINO = card.getAttribute('data-destino') || '#planes';
  var CON_ACCESO = card.getAttribute('data-acceso') === '1';
  var TITULO_BOTON = CON_ACCESO ? gettext('Ver pronóstico completo') : gettext('🔒 Pronóstico completo');
  if (!URL_DATOS) return;

  var SEGUNDOS_ROTACION = 7;

  var tarjetas = [];
  var balance = null;
  var indice = 0;
  var temporizador = null;

  function escapar(t) {
    return String(t == null ? '' : t)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function escudo(url, nombre) {
    if (url) {
      return '<img src="' + escapar(url) + '" alt="' + escapar(nombre) + '" loading="lazy">';
    }
    // Sin escudo se pone la inicial: mejor eso que un hueco vacio
    return '<span class="pc-inicial">' + escapar(nombre.charAt(0).toUpperCase()) + '</span>';
  }

  // "2026-10-11" -> "11 oct" (en aleman "11. Okt.")
  function fechaBonita(iso) {
    if (!iso) return '';
    var meses = [pgettext('mes corto', 'ene'), pgettext('mes corto', 'feb'), pgettext('mes corto', 'mar'),
                 pgettext('mes corto', 'abr'), pgettext('mes corto', 'may'), pgettext('mes corto', 'jun'),
                 pgettext('mes corto', 'jul'), pgettext('mes corto', 'ago'), pgettext('mes corto', 'sep'),
                 pgettext('mes corto', 'oct'), pgettext('mes corto', 'nov'), pgettext('mes corto', 'dic')];
    var p = String(iso).split('-');
    if (p.length !== 3) return '';
    return interpolate(gettext('%(dia)s %(mes)s'),
                       { dia: parseInt(p[2], 10), mes: meses[parseInt(p[1], 10) - 1] || '' }, true);
  }

  // "hace 3 días", a partir de los dias que manda el servidor
  function hace(dias) {
    if (dias <= 0) return gettext('hoy');
    if (dias === 1) return gettext('ayer');
    if (dias < 7) return interpolate(ngettext('hace %s día', 'hace %s días', dias), [dias]);
    if (dias < 30) {
      var semanas = Math.floor(dias / 7);
      return interpolate(ngettext('hace %s semana', 'hace %s semanas', semanas), [semanas]);
    }
    return gettext('hace más de un mes');
  }

  // ------------------------------------------------------------
  //  PIE COMUN: el balance verificado
  // ------------------------------------------------------------
  function pie() {
    if (!balance || !balance.verificados) {
      // Sin historial todavia: se enseña de que esta hecho el motor, que es
      // cierto y no revela nada. Nunca un numero inventado para rellenar.
      // LOS DOS NUMEROS DE ABAJO SON PROMESAS, NO ADORNOS: esta tarjeta lleva
      // candado, asi que es lo que se le ensena a alguien ANTES de que pague.
      //
      //   3 fuentes  -> dixon_coles, elo y mercado. Son las que mezcla el
      //                 motor y las que salen en "De donde sale este
      //                 pronostico". Comprobable en pantalla.
      //
      //   8 mercados -> 1X2, doble oportunidad, ambos marcan, mas/menos de
      //                 1.5, 2.5, 3.5 y 4.5 goles, y marcador exacto. Se
      //                 cuentan abriendo un pronostico.
      //
      // Aca decia 12 y no salia de ningun lado: estaba escrito a mano y no
      // coincidia con nada. Se dejan 8 a proposito aunque el motor calcula
      // mas cosas: prometer de menos y entregar de mas se perdona; al reves
      // no. Si algun dia se agrega un mercado a la pantalla, este numero se
      // sube AQUI, contando lo que se ve, no lo que se calcula por dentro.
      return '<div class="pc-metricas">' +
        '<div class="pc-metrica"><div class="v">3</div><div class="l">' + gettext('Fuentes cruzadas') + '</div></div>' +
        '<div class="pc-metrica"><div class="v">8</div><div class="l">' + gettext('Mercados') + '</div></div>' +
      '</div>';
    }
    return '<div class="pc-metricas">' +
      '<div class="pc-metrica"><div class="v">' + balance.verificados + '</div>' +
        '<div class="l">' + gettext('Partidos verificados') + '</div></div>' +
      '<div class="pc-metrica"><div class="v acc">' + balance.acierto + '%</div>' +
        '<div class="l">' + gettext('Acierto real') + '</div></div>' +
    '</div>';
  }

  function cabeza(etiqueta, distintivo) {
    return '<div class="pc-head">' +
      '<span class="pc-tag">' + etiqueta + '</span>' + distintivo +
    '</div>';
  }

  function equipos(t) {
    return '<div class="pc-teams">' +
      '<div class="pc-team">' +
        '<div class="pc-shield">' + escudo(t.local_escudo, t.local) + '</div>' +
        '<div class="pc-tname">' + escapar(t.local) + '</div>' +
      '</div>' +
      '<div class="pc-vs">VS</div>' +
      '<div class="pc-team">' +
        '<div class="pc-shield">' + escudo(t.visitante_escudo, t.visitante) + '</div>' +
        '<div class="pc-tname">' + escapar(t.visitante) + '</div>' +
      '</div>' +
    '</div>';
  }

  // ------------------------------------------------------------
  //  ESTADO 1 — PRONOSTICO YA RESUELTO
  // ------------------------------------------------------------
  function pintarResuelto(t) {
    var ok = !!t.acerto;
    var sello = ok
      ? '<span class="pc-sello ok">' + gettext('✓ Acertado') + '</span>'
      : '<span class="pc-sello no">' + gettext('✗ Fallado') + '</span>';

    // El servidor manda el signo (local / empate / visitante) y los dias,
    // para poder decirlo en el idioma de quien mira.
    var dijo = t.dijo;
    if (t.signo === 'empate') dijo = gettext('Empate');
    else if (t.signo === 'local') dijo = interpolate(gettext('Gana %s'), [t.local]);
    else if (t.signo === 'visitante') dijo = interpolate(gettext('Gana %s'), [t.visitante]);
    var cuando = (t.dias != null) ? hace(t.dias) : (t.cuando || '');

    return cabeza(gettext('Pronóstico verificado'), sello) +
      equipos(t) +
      '<div class="pc-resultado">' +
        '<div class="pc-marcador">' + escapar(t.marcador || '—') + '</div>' +
        '<div class="pc-contexto">' +
          (t.liga ? escapar(t.liga) + ' · ' : '') + escapar(cuando) +
        '</div>' +
      '</div>' +
      '<div class="pc-dijo' + (ok ? ' ok' : ' no') + '">' +
        '<span class="pc-dijo-l">' + gettext('xGol anticipó') + '</span>' +
        '<strong>' + escapar(dijo) + '</strong>' +
      '</div>' +
      pie();
  }

  // ------------------------------------------------------------
  //  ESTADO 2 — PROXIMO PARTIDO, BLOQUEADO
  // ------------------------------------------------------------
  function pintarBloqueado(t) {
    var vivo = (t.estado === 'IN_PLAY' || t.estado === 'PAUSED');
    var distintivo = vivo
      ? '<span class="pc-live">' + gettext('En vivo') + '</span>'
      : '<span class="pc-hora">' + escapar(t.hora || '') + '</span>';

    return cabeza(gettext('Próximo análisis'), distintivo) +
      equipos(t) +
      '<div class="pc-resultado">' +
        '<div class="pc-contexto">' +
          (t.liga ? escapar(t.liga) : '') +
          (t.fecha ? ' · ' + fechaBonita(t.fecha) : '') +
        '</div>' +
      '</div>' +
      '<a class="pc-candado" href="' + escapar(URL_DESTINO) + '">' +
        '<div class="pc-borroso"><span></span><span></span><span></span></div>' +
        '<div class="pc-candado-txt">' +
          '<div class="pc-candado-t">' + TITULO_BOTON + '</div>' +
          '<div class="pc-candado-s">' + gettext('Ganador · goles · marcador') + '</div>' +
        '</div>' +
      '</a>' +
      pie();
  }

  // ------------------------------------------------------------
  //  ESTADO 3 — NO HAY NADA QUE ENSEÑAR
  //  Una tarjeta atascada en "Cargando..." para siempre es lo peor que puede
  //  pasar en la cara de presentacion del proyecto: parece roto. Si no hay
  //  datos se dice, con el motivo, y se deja la llamada a la accion.
  // ------------------------------------------------------------
  var MOTIVOS = {
    sin_partidos:        gettext('No hay partidos programados en este momento.'),
    sin_ligas_cubiertas: gettext('No hay partidos de las ligas que analiza xGol ahora mismo.'),
    sin_conexion:        gettext('No se pudo conectar con el proveedor de datos.'),
    sin_datos:           gettext('No hay partidos disponibles en este momento.')
  };

  function pintarVacio(motivo) {
    return cabeza('xGol', '<span class="pc-live">' + gettext('IA en vivo') + '</span>') +
      '<div class="pc-vacio">' +
        '<div class="pc-vacio-i">⚽</div>' +
        '<div class="pc-vacio-t">' + escapar(MOTIVOS[motivo] || MOTIVOS.sin_datos) + '</div>' +
        '<div class="pc-vacio-s">' + gettext('Vuelve en unos minutos: la agenda se actualiza sola.') + '</div>' +
      '</div>' +
      '<a class="pc-candado" href="' + escapar(URL_DESTINO) + '">' +
        '<div class="pc-candado-txt">' +
          '<div class="pc-candado-t">' + gettext('Analiza cualquier partido') + '</div>' +
          '<div class="pc-candado-s">' + gettext('Ganador · goles · marcador') + '</div>' +
        '</div>' +
      '</a>' +
      pie();
  }

  function rotar() {
    if (!tarjetas.length) return;
    var t = tarjetas[indice % tarjetas.length];
    indice++;
    card.innerHTML = (t.tipo === 'resuelto') ? pintarResuelto(t) : pintarBloqueado(t);
  }

  fetch(URL_DATOS, { headers: { 'X-Requested-With': 'fetch' } })
    .then(function(r) { return r.json(); })
    .then(function(d) {
      var datos = d.predicciones || d || {};
      tarjetas = datos.tarjetas || [];
      balance = datos.balance || null;
      if (!tarjetas.length) {
        card.innerHTML = pintarVacio(datos.motivo);
        return;
      }
      rotar();
      if (tarjetas.length > 1) {
        temporizador = setInterval(rotar, SEGUNDOS_ROTACION * 1000);
      }
    })
    .catch(function() {
      card.innerHTML = pintarVacio('sin_conexion');
    });
})();