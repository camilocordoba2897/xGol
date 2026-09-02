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
// ============================================================
(function() {
  var card = document.getElementById('predCard');
  if (!card) return;

  var URL_DATOS = card.getAttribute('data-url');
  var URL_PLANES = card.getAttribute('data-planes') || '#planes';
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

  function fechaBonita(iso) {
    if (!iso) return '';
    var meses = ['ene', 'feb', 'mar', 'abr', 'may', 'jun',
                 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
    var p = String(iso).split('-');
    if (p.length !== 3) return '';
    return parseInt(p[2], 10) + ' ' + (meses[parseInt(p[1], 10) - 1] || '');
  }

  // ------------------------------------------------------------
  //  PIE COMUN: el balance verificado
  // ------------------------------------------------------------
  function pie() {
    if (!balance || !balance.verificados) {
      // Sin historial todavia: se enseña de que esta hecho el motor, que es
      // cierto y no revela nada. Nunca un numero inventado para rellenar.
      return '<div class="pc-metricas">' +
        '<div class="pc-metrica"><div class="v">3</div><div class="l">Fuentes cruzadas</div></div>' +
        '<div class="pc-metrica"><div class="v">12</div><div class="l">Mercados</div></div>' +
      '</div>';
    }
    return '<div class="pc-metricas">' +
      '<div class="pc-metrica"><div class="v">' + balance.verificados + '</div>' +
        '<div class="l">Partidos verificados</div></div>' +
      '<div class="pc-metrica"><div class="v acc">' + balance.acierto + '%</div>' +
        '<div class="l">Acierto real</div></div>' +
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
      ? '<span class="pc-sello ok">✓ Acertado</span>'
      : '<span class="pc-sello no">✗ Fallado</span>';

    return cabeza('Pronóstico verificado', sello) +
      equipos(t) +
      '<div class="pc-resultado">' +
        '<div class="pc-marcador">' + escapar(t.marcador || '—') + '</div>' +
        '<div class="pc-contexto">' +
          (t.liga ? escapar(t.liga) + ' · ' : '') + escapar(t.cuando || '') +
        '</div>' +
      '</div>' +
      '<div class="pc-dijo' + (ok ? ' ok' : ' no') + '">' +
        '<span class="pc-dijo-l">xGol anticipó</span>' +
        '<strong>' + escapar(t.dijo) + '</strong>' +
      '</div>' +
      pie();
  }

  // ------------------------------------------------------------
  //  ESTADO 2 — PROXIMO PARTIDO, BLOQUEADO
  // ------------------------------------------------------------
  function pintarBloqueado(t) {
    var vivo = (t.estado === 'IN_PLAY' || t.estado === 'PAUSED');
    var distintivo = vivo
      ? '<span class="pc-live">En vivo</span>'
      : '<span class="pc-hora">' + escapar(t.hora || '') + '</span>';

    return cabeza('Próximo análisis', distintivo) +
      equipos(t) +
      '<div class="pc-resultado">' +
        '<div class="pc-contexto">' +
          (t.liga ? escapar(t.liga) : '') +
          (t.fecha ? ' · ' + fechaBonita(t.fecha) : '') +
        '</div>' +
      '</div>' +
      '<a class="pc-candado" href="' + escapar(URL_PLANES) + '">' +
        '<div class="pc-borroso"><span></span><span></span><span></span></div>' +
        '<div class="pc-candado-txt">' +
          '<div class="pc-candado-t">🔒 Pronóstico completo</div>' +
          '<div class="pc-candado-s">Ganador · goles · marcador · valor</div>' +
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
    sin_partidos:        'No hay partidos programados en este momento.',
    sin_ligas_cubiertas: 'No hay partidos de las ligas que analiza xGol ahora mismo.',
    sin_conexion:        'No se pudo conectar con el proveedor de datos.',
    sin_datos:           'No hay partidos disponibles en este momento.'
  };

  function pintarVacio(motivo) {
    return cabeza('xGol', '<span class="pc-live">IA en vivo</span>') +
      '<div class="pc-vacio">' +
        '<div class="pc-vacio-i">⚽</div>' +
        '<div class="pc-vacio-t">' + escapar(MOTIVOS[motivo] || MOTIVOS.sin_datos) + '</div>' +
        '<div class="pc-vacio-s">Vuelve en unos minutos: la agenda se actualiza sola.</div>' +
      '</div>' +
      '<a class="pc-candado" href="' + escapar(URL_PLANES) + '">' +
        '<div class="pc-candado-txt">' +
          '<div class="pc-candado-t">Analiza cualquier partido</div>' +
          '<div class="pc-candado-s">Ganador · goles · marcador · valor</div>' +
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