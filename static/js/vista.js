// ============================================================
//  VISTA DEL PRONOSTICO — estructura de la referencia en video
//
//  Sobrescribe renderAll() para pintar solo las tarjetas del video.
//  NO toca analizador.js: reutiliza tal cual computeStats(),
//  buildModel(), ctxControls(), pct(), fmt() y el estado global.
//
//  Orden de carga obligatorio en la plantilla:
//    analizador.js  ->  vista.js  ->  auto.js
//  (auto.js envuelve renderAll para pintar los escudos; por eso
//   va despues, y por eso la cabecera conserva .match-header y .mteam)
// ============================================================
(function() {

  // ---- Datos del partido elegido en la lista (los pone auto.js) ----
  // En modo manual (CSV) no existe: la cabecera se pinta sin hora.
  function partido() { return window.XGOL_PARTIDO || null; }

  var MESES_C = ['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'];

  function horaDe(utc) {
    var d = new Date(utc);
    if (isNaN(d)) return '';
    return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
  }

  // Fecha larga para la cabecera del partido: "23 de agosto de 2026".
  // El historial y los enfrentamientos siguen usando fechaCorta(),
  // que no se toca porque ahi las fechas van en columna estrecha.
  var MESES_L = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
                 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];

  function fechaDe(utc) {
    var d = new Date(utc);
    if (isNaN(d)) return '';
    return d.getDate() + ' de ' + MESES_L[d.getMonth()] + ' de ' + d.getFullYear();
  }

  function textoEstado(p) {
    if (!p) return '';
    if (p.jugado) return 'finalizado';
    if (p.estado === 'IN_PLAY' || p.estado === 'PAUSED') return 'en juego';
    return 'no iniciado';
  }

  function escapar(t) {
    return String(t == null ? '' : t)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ============================================================
  //  CABECERA — escudos, nombres y cuando se juega
  // ============================================================
  function cabecera() {
    var p = partido();
    var centro;
    if (p && p.jugado) {
      centro = '<div class="pr-hora">' + (p.goles_local != null ? p.goles_local : '?') +
               ' - ' + (p.goles_visitante != null ? p.goles_visitante : '?') + '</div>' +
               '<div class="pr-fecha">' + fechaDe(p.utc) + '</div>' +
               '<div class="pr-estado">finalizado</div>';
    } else if (p) {
      centro = '<div class="pr-hora">' + horaDe(p.utc) + '</div>' +
               '<div class="pr-fecha">' + fechaDe(p.utc) + '</div>' +
               '<div class="pr-estado">' + textoEstado(p) + '</div>';
    } else {
      centro = '<div class="pr-hora">VS</div>' +
               '<div class="pr-estado">datos propios</div>';
    }

    var liga = (p && p.liga)
      ? '<div class="pr-liga">' + escapar(p.liga) +
        (p.jornada ? ' &middot; jornada ' + p.jornada : '') + '</div>'
      : '';

    return liga +
      '<div class="match-header pr-header">' +
        '<div class="match-teams">' +
          '<div class="mteam">' + escapar(names.team1) + '</div>' +
          '<div class="vs">' + centro + '</div>' +
          '<div class="mteam">' + escapar(names.team2) + '</div>' +
        '</div>' +
      '</div>';
  }

  // ============================================================
  //  TARJETA 1 — quien ganara el partido
  //  Nombre arriba, % debajo en negrita, y una sola barra partida
  //  en tres segmentos proporcionales (como la referencia).
  // ============================================================
  function tarjetaGanador(model) {
    var favorito, prob;
    if (model.pD >= model.pH && model.pD >= model.pA) {
      favorito = 'Empate'; prob = model.pD;
    } else if (model.pH >= model.pA) {
      favorito = names.team1; prob = model.pH;
    } else {
      favorito = names.team2; prob = model.pA;
    }

    // Los tres porcentajes se redondean JUNTOS, no por separado. Redondeando
    // cada uno por su cuenta salia 64+21+14 = 99%, y eso en una pantalla
    // parece un error de calculo aunque las probabilidades sean exactas.
    // Se reparte el sobrante al que tenga el decimal mas alto (metodo del
    // resto mayor, el mismo que se usa para repartir escaños).
    var crudos = [Math.max(0, model.pH) * 100, Math.max(0, model.pD) * 100,
                  Math.max(0, model.pA) * 100];
    var enteros = crudos.map(function(x) { return Math.floor(x); });
    var sobra = 100 - enteros[0] - enteros[1] - enteros[2];
    var orden = [0, 1, 2].sort(function(i, j) {
      return (crudos[j] - enteros[j]) - (crudos[i] - enteros[i]);
    });
    for (var r = 0; r < sobra; r++) enteros[orden[r % 3]]++;
    var ph = enteros[0], pd = enteros[1], pa = enteros[2];
    var ganaH = model.pH >= model.pD && model.pH >= model.pA;
    var ganaD = model.pD > model.pH && model.pD >= model.pA;

    return '<div class="pr-card">' +
      '<div class="pr-titulo">¿Quién ganará el partido?</div>' +
      '<div class="pr-grande">' + escapar(favorito) + '</div>' +
      '<div class="pr-sub">' + pct(prob) + '% de probabilidad</div>' +
      '<div class="pr-tres">' +
        '<div class="pr-tres-col">' +
          '<span class="pr-tres-eq">' + escapar(names.team1) + '</span>' +
          '<span class="pr-tres-pct' + (ganaH ? ' es-alto' : '') + '">' + ph + '%</span>' +
        '</div>' +
        '<div class="pr-tres-col pr-centro">' +
          '<span class="pr-tres-eq">Empate</span>' +
          '<span class="pr-tres-pct' + (ganaD ? ' es-alto' : '') + '">' + pd + '%</span>' +
        '</div>' +
        '<div class="pr-tres-col pr-der">' +
          '<span class="pr-tres-eq">' + escapar(names.team2) + '</span>' +
          '<span class="pr-tres-pct' + (!ganaH && !ganaD ? ' es-alto' : '') + '">' + pa + '%</span>' +
        '</div>' +
      '</div>' +
      '<div class="pr-barra3">' +
        '<div class="pr-b3-h" style="width:' + ph + '%"></div>' +
        '<div class="pr-b3-d" style="width:' + pd + '%"></div>' +
        '<div class="pr-b3-a" style="width:' + pa + '%"></div>' +
      '</div>' +
    '</div>';
  }

  // ============================================================
  //  TARJETA 2 — cuantos goles se marcaran (linea 2.5)
  // ============================================================
  function tarjetaGoles(model) {
    var mas = model.over25;
    var menos = 1 - mas;
    var gana = mas >= menos;
    return '<div class="pr-card">' +
      '<div class="pr-titulo">¿Cuántos goles se marcarán?</div>' +
      '<div class="pr-grande">' + (gana ? '+2.5 Goles' : '-2.5 Goles') + '</div>' +
      '<div class="pr-sub">' + pct(gana ? mas : menos) + '% de probabilidad</div>' +
      '<div class="pr-dos">' +
        '<span>+2.5 Goles <strong>' + pct(mas) + '%</strong></span>' +
        '<span>-2.5 Goles <strong>' + pct(menos) + '%</strong></span>' +
      '</div>' +
      '<div class="pr-barra"><div class="pr-barra-si" style="width:' + pct(mas) + '%"></div></div>' +
    '</div>';
  }

  // ============================================================
  //  TARJETA 3 — resultado mas probable + top 12 marcadores
  //  Reutiliza .scoreline-grid / .scoreline-card, que ya existen
  //  en analizador.css: mismo bloque que tenia la pestaña anterior.
  // ============================================================
  function tarjetaMarcador(model) {
    var scores = [], h, a, p;
    for (h = 0; h <= 7; h++) {
      for (a = 0; a <= 7; a++) {
        p = model.mat[h][a];
        if (p > 0.001) scores.push({ h: h, a: a, p: p });
      }
    }
    scores.sort(function(x, y) { return y.p - x.p; });
    var top = scores.slice(0, 12);
    if (!top.length) return '';
    var maxP = top[0].p;

    var tarjetas = top.map(function(s, idx) {
      var esLocal = s.h > s.a, esEmpate = s.h === s.a;
      var color = esLocal ? 'var(--home)' : esEmpate ? '#6b7280' : 'var(--away)';
      var etiqueta = esLocal ? names.team1 : esEmpate ? 'Empate' : names.team2;
      var ancho = Math.round((s.p / maxP) * 100);
      return '<div class="scoreline-card' + (idx === 0 ? ' sc-top' : '') + '">' +
        '<div class="sc-score" style="color:' + color + '">' + s.h + ' — ' + s.a + '</div>' +
        '<div class="sc-label">' + escapar(etiqueta) + '</div>' +
        '<div class="sc-bar-bg"><div class="sc-bar-fill" style="width:' + ancho + '%;background:' + color + '"></div></div>' +
        '<div class="sc-pct">' + (s.p * 100).toFixed(1) + '%</div>' +
      '</div>';
    }).join('');

    return '<div class="pr-card">' +
      '<div class="pr-titulo">Resultado más probable</div>' +
      '<div class="pr-grande">' + top[0].h + ' - ' + top[0].a + '</div>' +
      '<div class="pr-sub">con ' + pct(top[0].p) + '% de probabilidad</div>' +
      '<div class="pr-leyenda" style="margin:14px 0 8px">Top 12 marcadores &middot; Poisson + Dixon-Coles, ordenados por probabilidad</div>' +
      '<div class="scoreline-grid">' + tarjetas + '</div>' +
    '</div>';
  }

  // ============================================================
  //  TARJETA DE CUOTAS — casas de apuestas reales
  //  Las trae auto.js y las deja en window.XGOL_CUOTAS.
  //  Si no hay clave configurada o no hay partido, no se pinta.
  // ============================================================
  function tarjetaCuotas(model) {
    var c = window.XGOL_CUOTAS;
    if (!c || !c.h2h) return '';

    var filas = [
      { k: 'local',     etiqueta: names.team1, prob: model.pH },
      { k: 'empate',    etiqueta: 'Empate',    prob: model.pD },
      { k: 'visitante', etiqueta: names.team2, prob: model.pA }
    ];

    var celdas = filas.map(function(f) {
      var o = c.h2h[f.k];
      if (!o || !o.cuota) {
        return '<div class="cu-col"><div class="cu-eq">' + escapar(f.etiqueta) + '</div>' +
               '<div class="cu-cuota cu-nd">—</div></div>';
      }
      // Valor esperado: cuota x probabilidad del modelo. >1 = el modelo
      // ve mas probable el resultado de lo que paga la casa.
      var ev = o.cuota * f.prob;
      var clase = ev > 1.05 ? ' cu-valor' : '';
      return '<div class="cu-col' + clase + '">' +
        '<div class="cu-eq">' + escapar(f.etiqueta) + '</div>' +
        '<div class="cu-cuota">' + o.cuota.toFixed(2) + '</div>' +
        '<div class="cu-casa">' + escapar(o.casa) + '</div>' +
        (ev > 1.05 ? '<div class="cu-ev">valor +' + Math.round((ev - 1) * 100) + '%</div>' : '') +
      '</div>';
    }).join('');

    return '<div class="pr-card">' +
      '<div class="pr-titulo">Cuotas de las casas de apuestas</div>' +
      '<div class="cu-fila">' + celdas + '</div>' +
      '<div class="cu-nota">Mejor cuota disponible por resultado' +
        (c.actualizado ? ' &middot; actualizado ' + escapar(c.actualizado) : '') +
        '. "Valor" marca donde el modelo da más probabilidad que la casa; ' +
        'no es una recomendación de apuesta.</div>' +
    '</div>';
  }

  // ============================================================
  //  TARJETA — ENFRENTAMIENTOS DIRECTOS
  //  El backend los calcula desde el historial largo del local
  //  (60 partidos) y los manda en la respuesta como "h2h".
  // ============================================================
  function fechaCorta(iso) {
    var d = new Date(String(iso || '') + 'T00:00:00');
    if (isNaN(d)) return String(iso || '');
    return String(d.getDate()).padStart(2, '0') + '/' + MESES_C[d.getMonth()] + '/' +
           String(d.getFullYear()).slice(2);
  }

  function tarjetaEnfrentamientos() {
    var h = window.XGOL_H2H;
    if (!h || !h.total) return '';

    var t = h.total;
    var pv = Math.round((h.victorias_local / t) * 100);
    var pe = Math.round((h.empates / t) * 100);
    var pd = Math.round((h.victorias_visitante / t) * 100);

    var filas = h.partidos.map(function(p) {
      var gl = p.goles_local == null ? '?' : p.goles_local;
      var gv = p.goles_visitante == null ? '?' : p.goles_visitante;
      var ganaL = gl > gv, ganaV = gv > gl;
      return '<div class="h2h-p">' +
        '<div class="h2h-fecha">' + fechaCorta(p.fecha) + '</div>' +
        '<div class="h2h-lados">' +
          '<div class="h2h-lado' + (ganaL ? ' gano' : '') + '">' +
            '<span class="h2h-eq">' + escapar(p.local) + '</span>' +
            '<span class="h2h-g">' + gl + '</span></div>' +
          '<div class="h2h-lado' + (ganaV ? ' gano' : '') + '">' +
            '<span class="h2h-eq">' + escapar(p.visitante) + '</span>' +
            '<span class="h2h-g">' + gv + '</span></div>' +
        '</div>' +
      '</div>';
    }).join('');

    return '<div class="pr-card">' +
      '<div class="pr-titulo">Enfrentamientos</div>' +
      '<div class="h2h-cab">' +
        '<span class="h2h-eqcab">' + escapar(names.team1) + '</span>' +
        '<span class="h2h-total">' + t + (t === 1 ? ' partido' : ' partidos') +
          (h.desde ? '<span class="h2h-desde">Desde ' + fechaCorta(h.desde) + '</span>' : '') +
        '</span>' +
        '<span class="h2h-eqcab h2h-der">' + escapar(names.team2) + '</span>' +
      '</div>' +
      '<div class="h2h-res">' +
        '<span>' + h.victorias_local + (h.victorias_local === 1 ? ' victoria' : ' victorias') + '</span>' +
        '<span class="pr-centro">' + h.empates + (h.empates === 1 ? ' empate' : ' empates') + '</span>' +
        '<span class="pr-der">' + h.victorias_visitante + (h.victorias_visitante === 1 ? ' victoria' : ' victorias') + '</span>' +
      '</div>' +
      '<div class="h2h-pcts">' +
        '<span>' + pv + '%</span>' +
        '<span class="pr-centro">' + pe + '%</span>' +
        '<span class="pr-der">' + pd + '%</span>' +
      '</div>' +
      '<div class="pr-barra3">' +
        '<div class="pr-b3-h" style="width:' + pv + '%"></div>' +
        '<div class="pr-b3-d" style="width:' + pe + '%"></div>' +
        '<div class="pr-b3-a" style="width:' + pd + '%"></div>' +
      '</div>' +
      '<div class="h2h-lista">' + filas + '</div>' +
    '</div>';
  }

  // ============================================================
  //  TARJETAS — ULTIMOS RESULTADOS DE CADA EQUIPO
  //  Barras de altura proporcional y pestañas Casa / Todos / Fuera,
  //  igual que la referencia. Sale del historial que ya cargo el motor.
  // ============================================================
  var filtroForma = { team1: 'todos', team2: 'todos' };

  window.xgolForma = function(cual, filtro) {
    filtroForma[cual] = filtro;
    var caja = document.getElementById('forma-' + cual);
    if (caja) caja.innerHTML = cuerpoForma(cual);
  };

  function filasDe(cual) {
    return (cual === 'team1' ? state.team1 : state.team2) || [];
  }

  function aplicarFiltro(filas, filtro) {
    if (filtro === 'casa') {
      return filas.filter(function(r) { return String(r.sede || '').indexOf('local') === 0; });
    }
    if (filtro === 'fuera') {
      return filas.filter(function(r) { return String(r.sede || '').indexOf('visit') === 0; });
    }
    return filas;
  }

  function cuerpoForma(cual) {
    var filtro = filtroForma[cual];
    var filas = aplicarFiltro(filasDe(cual), filtro);
    var v = 0, e = 0, d = 0;
    filas.forEach(function(r) {
      var res = String(r.resultado || '').toUpperCase();
      if (res === 'W') v++; else if (res === 'D') e++; else if (res === 'L') d++;
    });
    var tope = Math.max(v, e, d, 1);

    var barras = '<div class="fm-barras">' +
      '<div class="fm-col"><div class="fm-bar-hueco">' +
        '<div class="fm-bar fm-w" style="height:' + Math.round((v / tope) * 100) + '%"></div></div>' +
        '<div class="fm-lbl">' + v + (v === 1 ? ' victoria' : ' victorias') + '</div></div>' +
      '<div class="fm-col"><div class="fm-bar-hueco">' +
        '<div class="fm-bar fm-d" style="height:' + Math.round((e / tope) * 100) + '%"></div></div>' +
        '<div class="fm-lbl">' + e + (e === 1 ? ' empate' : ' empates') + '</div></div>' +
      '<div class="fm-col"><div class="fm-bar-hueco">' +
        '<div class="fm-bar fm-l" style="height:' + Math.round((d / tope) * 100) + '%"></div></div>' +
        '<div class="fm-lbl">' + d + (d === 1 ? ' derrota' : ' derrotas') + '</div></div>' +
    '</div>';

    var pestanas = ['casa', 'todos', 'fuera'].map(function(f) {
      var texto = f === 'casa' ? 'Casa' : f === 'todos' ? 'Todos' : 'Fuera';
      return '<button class="fm-tab' + (filtro === f ? ' activa' : '') +
             '" onclick="xgolForma(\'' + cual + '\',\'' + f + '\')">' + texto + '</button>';
    }).join('');

    var lista = filas.slice(0, 6).map(function(r) {
      var res = String(r.resultado || '').toUpperCase();
      var letra = res === 'W' ? 'G' : res === 'D' ? 'E' : 'P';
      var gf = (r.goles_f === '' || r.goles_f == null) ? '?' : r.goles_f;
      var gc = (r.goles_c === '' || r.goles_c == null) ? '?' : r.goles_c;
      var enCasa = String(r.sede || '').indexOf('local') === 0;
      var yo = escapar(names[cual]), rival = escapar((r.rival || '').trim() || '—');
      var arriba = enCasa ? yo : rival, abajo = enCasa ? rival : yo;
      var gArriba = enCasa ? gf : gc, gAbajo = enCasa ? gc : gf;
      return '<div class="fm-p">' +
        '<div class="fm-fecha">' + fechaCorta(r.fecha) + '</div>' +
        '<div class="fm-lados">' +
          '<div class="fm-lado' + (gArriba > gAbajo ? ' gano' : '') + '">' +
            '<span class="fm-eq">' + arriba + '</span><span class="fm-g">' + gArriba + '</span></div>' +
          '<div class="fm-lado' + (gAbajo > gArriba ? ' gano' : '') + '">' +
            '<span class="fm-eq">' + abajo + '</span><span class="fm-g">' + gAbajo + '</span></div>' +
        '</div>' +
        '<div class="fm-badge ' + res + '">' + letra + '</div>' +
      '</div>';
    }).join('');

    if (!filas.length) {
      lista = '<div class="fm-vacio">Sin partidos ' +
              (filtro === 'casa' ? 'como local' : 'como visitante') + ' en el historial.</div>';
    }

    return barras + '<div class="fm-tabs">' + pestanas + '</div>' + lista;
  }

  function tarjetaForma(cual) {
    return '<div class="pr-card">' +
      '<div class="pr-titulo">Últimos resultados <strong>' + escapar(names[cual]) + '</strong></div>' +
      '<div id="forma-' + cual + '">' + cuerpoForma(cual) + '</div>' +
    '</div>';
  }

  // ============================================================
  //  PIE — que modelo genero estos numeros
  // ============================================================
  function pieModelo(model, s1) {
    // El texto tiene que describir el modelo que SE ESTA USANDO, no el que
    // habia antes. Si el motor esta activo, decir "sobre los ultimos 15
    // partidos" es mentira: los numeros salen de la liga completa, del Elo y
    // del mercado. Y una linea que se contradice con lo que hay arriba tumba
    // la credibilidad de toda la pantalla.
    var cabeza = 'Goles esperados: ' + escapar(names.team1) + ' <strong>' +
      fmt2(model.lam1) + '</strong> &middot; ' + escapar(names.team2) +
      ' <strong>' + fmt2(model.lam2) + '</strong><br>';

    if (model.motor) {
      var nombres = { dixon_coles: 'modelo de liga', elo: 'Elo', mercado: 'mercado' };
      var usadas = (model.motorFuentes || []).map(function(k) {
        return nombres[k] || k;
      });
      return '<div class="pr-modelo">' + cabeza +
        'Motor xGol &middot; ' +
        (usadas.length ? usadas.join(' + ') + ', ponderados' : 'sin fuentes') +
        (model.motorPartidos ? ' sobre ' + model.motorPartidos + ' partidos de la liga' : '') +
        ' &middot; Poisson + Dixon-Coles' +
        (model.neutral ? ' &middot; sede neutral' : '') +
      '</div>';
    }

    // Sin motor: se describe el calculo local, que es lo que se esta usando
    var extras = [];
    if (model.usedXG) extras.push('xG');
    if (model.usedXGOT) extras.push('xGOT');
    if (model.usedPPDA) extras.push('PPDA');
    return '<div class="pr-modelo">' + cabeza +
      'Cálculo local &middot; Poisson + Dixon-Coles sobre los últimos ' + s1.n +
      ' partidos de cada equipo' +
      (extras.length ? ' &middot; ' + extras.join(' + ') : '') +
      (model.neutral ? ' &middot; sede neutral' : '') +
    '</div>';
  }

  // ============================================================
  //  RENDER PRINCIPAL — reemplaza al original
  // ============================================================
  window.renderAll = function() {
    var destino = document.getElementById('pronostico-contenido');
    if (!destino) return;
    if (!state.team1 || !state.team2) return;

    var s1 = computeStats(state.team1);
    var s2 = computeStats(state.team2);
    var model = buildModel(s1, s2);

    destino.className = '';
    destino.innerHTML =
      cabecera() +
      tarjetaGanador(model) +
      tarjetaCuotas(model) +
      tarjetaGoles(model) +
      tarjetaMarcador(model) +
      tarjetaEnfrentamientos() +
      '<div class="pr-forma">' +
        tarjetaForma('team1') +
        tarjetaForma('team2') +
      '</div>' +
      '<details class="pr-ajustes">' +
        '<summary>Ajustes del partido</summary>' +
        '<label class="neutral-toggle" title="Actívalo para finales o partidos en sede única: no se aplica ventaja local a ningún equipo.">' +
          '<input type="checkbox" ' + (model.neutral ? 'checked' : '') + ' onchange="toggleNeutral(this.checked)">' +
          '<span class="neutral-slider"></span>' +
          '<span class="neutral-label">Cancha neutral</span>' +
        '</label>' +
        ctxControls() +
      '</details>' +
      pieModelo(model, s1);

    try { saveSession(); } catch (e) {}
  };

})();