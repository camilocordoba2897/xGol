// ============================================================
//  MOTOR xGol — UN SOLO CEREBRO
//
//  Antes el analizador tenia dos modelos calculando lo mismo por
//  separado: buildModel() (15 partidos por equipo, sin cuotas) y el
//  motor del backend (liga completa + Elo + mercado). Daban numeros
//  distintos porque SON distintos, y eso en pantalla parece un error.
//
//  Este archivo lo resuelve de raiz: sustituye buildModel por el
//  resultado del motor. A partir de aqui TODAS las tarjetas que ya
//  pinta vista.js —ganador, goles, marcador, cuotas— salen de la
//  MISMA matriz del backend. No hay dos numeros para lo mismo en
//  ninguna parte de la pantalla, porque solo hay un calculo.
//
//  NO modifica analizador.js ni vista.js. Sigue el patron de auto.js:
//  envuelve renderAll y sustituye buildModel desde fuera.
//
//  Si el motor no responde, el analizador NO se queda en blanco:
//  vuelve al calculo local y avisa con un banner bien visible de que
//  esta en modo limitado. Nunca se muestran numeros peores sin decirlo.
// ============================================================
(function() {
  var RUTAS = window.XGOL_AUTO || {};
  if (!RUTAS.motor) {
    console.warn('[xGol motor] Falta la ruta en window.XGOL_AUTO. ¿Actualizaste analizador.html?');
    return;
  }
  if (typeof window.renderAll !== 'function' || typeof window.buildModel !== 'function') {
    console.warn('[xGol motor] Carga motor.js DESPUES de analizador.js y vista.js.');
    return;
  }

  var MOTIVOS = {
    sin_datos:         'La liga no está ajustada. Ejecuta: python manage.py ajustar_motor',
    cuota:             'Se agotó el límite de peticiones por minuto de football-data.org.',
    red:               'No se pudo conectar con el proveedor de datos.',
    faltan_parametros: 'La petición salió sin liga o sin equipos.'
  };

  var renderOriginal = window.renderAll;
  var buildOriginal  = window.buildModel;

  var datos = null;      // ultima respuesta del motor
  var clave = null;      // partido + cancha neutral que corresponden a 'datos'
  var pidiendo = false;
  var fallo = null;      // motivo del ultimo fallo, para el banner

  function escapar(t) {
    return String(t == null ? '' : t)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function pct(v) { return (v * 100).toFixed(1) + '%'; }

  function esNeutral() {
    try { return !!neutralVenue; } catch (e) { return false; }
  }

  function claveActual() {
    var p = window.XGOL_PARTIDO || {};
    if (!p.id || !p.liga_codigo) return null;
    return p.liga_codigo + '|' + p.id + '|' + (esNeutral() ? 'n' : 'c');
  }

  // ------------------------------------------------------------
  //  buildModel SUSTITUIDO
  //  Devuelve exactamente la misma forma que el original, pero con
  //  los numeros del motor. Asi vista.js no se entera de nada y
  //  pinta todo con una sola fuente de verdad.
  // ------------------------------------------------------------
  // ------------------------------------------------------------
  //  MODELO NEUTRO DE ESPERA
  //  Se usa SOLO en el instante que va entre abrir la pantalla y que
  //  responda el motor, y unicamente cuando el calculo local no puede
  //  correr por falta de partidos (un equipo con 0, 1 o 2 partidos, cosa
  //  normal al empezar la temporada). Sin esto, ahi salian NaN% por todas
  //  las tarjetas durante medio segundo. No es un pronostico: es un relleno
  //  que el motor sobrescribe enseguida.
  // ------------------------------------------------------------
  function modeloEspera() {
    var L1 = 1.35, L2 = 1.15, N = 8;
    function poisson(k, lam) {
      var f = 1, i;
      for (i = 2; i <= k; i++) f *= i;
      return Math.exp(-lam) * Math.pow(lam, k) / f;
    }
    var mat = [], h, a, suma = 0;
    for (h = 0; h < N; h++) {
      mat[h] = [];
      for (a = 0; a < N; a++) { mat[h][a] = poisson(h, L1) * poisson(a, L2); suma += mat[h][a]; }
    }
    var pH = 0, pD = 0, pA = 0, btts = 0, acum = [0, 0, 0, 0, 0], i2;
    for (h = 0; h < N; h++) {
      for (a = 0; a < N; a++) {
        mat[h][a] /= suma;
        var p = mat[h][a];
        if (h > a) pH += p; else if (h === a) pD += p; else pA += p;
        if (h >= 1 && a >= 1) btts += p;
        if (h + a <= 4) { for (i2 = h + a; i2 < 5; i2++) acum[i2] += p; }
      }
    }
    return {
      lam1: L1, lam2: L2, lamTotal: L1 + L2,
      pH: pH, pD: pD, pA: pA,
      over15: 1 - acum[1], over25: 1 - acum[2], over35: 1 - acum[3], over45: 1 - acum[4],
      btts: btts, p00: mat[0][0], mat: mat,
      rho: 0, rhoDynamic: false, rhoN: 0, neutral: esNeutral(),
      usedXG: false, usedXGOT: false, usedPPDA: false,
      trendGF1: 1, trendGF2: 1,
      wXGF1: null, wXGA1: null, wXGF2: null, wXGA2: null,
      contextUsed1: esNeutral() ? 'neutral' : 'local',
      contextUsed2: esNeutral() ? 'neutral' : 'away',
      motor: true, motorFuentes: [], motorPartidos: 0
    };
  }

  function sirve(m) {
    return m && isFinite(m.pH) && isFinite(m.pD) && isFinite(m.pA) &&
           isFinite(m.lam1) && isFinite(m.lam2) && m.mat && m.mat.length;
  }

  window.buildModel = function(s1, s2) {
    if (!datos || clave !== claveActual() || !datos.matriz) {
      // aun no llego el motor, o fallo
      var local;
      try { local = buildOriginal(s1, s2); } catch (e) { local = null; }
      return sirve(local) ? local : modeloEspera();
    }
    var modelo = modeloDesdeMatriz(datos.matriz);
    // Datos para el pie de pagina: que fuentes se usaron y sobre cuantos
    // partidos. El texto que se ve en pantalla tiene que decir la verdad
    // sobre de donde salen los numeros, no describir un modelo que ya no
    // se esta usando.
    modelo.motorFuentes = Object.keys(datos.fuentes || {});
    modelo.motorPartidos = (datos.diagnostico || {}).partidos_ajuste || 0;
    return modelo;
  };

  // ------------------------------------------------------------
  //  DE LA MATRIZ DEL MOTOR AL MODELO QUE PINTA vista.js
  //  Publica: seguimiento.js la usa para evaluar un partido con la
  //  MISMA matriz que se mostro antes del saque (las lineas de goles
  //  dependen de ella y, si no, no coincidirian con la foto).
  // ------------------------------------------------------------
  function modeloDesdeMatriz(mat) {
    // TODO se calcula desde 'mat', ni un solo numero se lee de otro sitio.
    // Es la unica forma de garantizar que dos tarjetas de la pantalla no
    // puedan decir cosas distintas sobre el mismo suceso.
    var h, a, p;
    var pH = 0, pD = 0, pA = 0, btts = 0, lam1 = 0, lam2 = 0;
    var acum = [0, 0, 0, 0, 0];   // P(total de goles <= 0,1,2,3,4)
    for (h = 0; h < mat.length; h++) {
      for (a = 0; a < mat[h].length; a++) {
        p = mat[h][a];
        if (h > a) pH += p; else if (h === a) pD += p; else pA += p;
        if (h >= 1 && a >= 1) btts += p;
        lam1 += h * p; lam2 += a * p;
        if (h + a <= 4) {
          for (var i = h + a; i < 5; i++) acum[i] += p;
        }
      }
    }
    function over(limite) { return Math.max(0, 1 - acum[limite]); }

    return {
      lam1: lam1, lam2: lam2, lamTotal: lam1 + lam2,
      pH: pH, pD: pD, pA: pA,
      over15: over(1), over25: over(2), over35: over(3), over45: over(4),
      btts: btts,
      p00: mat[0][0],
      mat: mat,
      rho: 0, rhoDynamic: false, rhoN: 0,
      neutral: esNeutral(),
      // Banderas del motor: las lee el pie de la tarjeta de vista.js.
      // Se marcan en false porque el motor no usa xG todavia; decir lo
      // contrario seria mentirle al usuario en la propia pantalla.
      usedXG: false, usedXGOT: false, usedPPDA: false,
      trendGF1: 1, trendGF2: 1,
      wXGF1: null, wXGA1: null, wXGF2: null, wXGA2: null,
      contextUsed1: esNeutral() ? 'neutral' : 'local',
      contextUsed2: esNeutral() ? 'neutral' : 'away',
      motor: true, motorFuentes: [], motorPartidos: 0
    };
  }
  window.modeloDesdeMatriz = modeloDesdeMatriz;

  // ------------------------------------------------------------
  //  TARJETA DE DIAGNOSTICO
  //  NO repite los porcentajes (esos ya salen en las tarjetas de
  //  siempre). Enseña de DONDE salen: que dice cada fuente, cuanto
  //  pesa, cuanta confianza hay y donde la casa paga de mas.
  // ------------------------------------------------------------
  function tarjetaDiagnostico(d) {
    var diag = d.diagnostico || {};
    var conf = diag.confianza || {};
    var nombreLocal = escapar(d.local), nombreVisit = escapar(d.visitante);

    var nombres = { dixon_coles: 'Modelo de liga', elo: 'Elo', mercado: 'Mercado' };
    var fuentes = d.fuentes || {}, pesos = d.pesos || {};
    var filas = Object.keys(fuentes).sort().map(function(k) {
      var f = fuentes[k];
      var peso = pesos[k] != null ? ' <span class="mx-peso">(' + Math.round(pesos[k] * 100) + '%)</span>' : '';
      return '<tr><td>' + escapar(nombres[k] || k) + peso + '</td><td>' +
        pct(f.local || 0) + '</td><td>' + pct(f.empate || 0) + '</td><td>' +
        pct(f.visitante || 0) + '</td></tr>';
    }).join('');
    var tabla = filas
      ? '<table class="mx-tabla"><thead><tr><th>Fuente</th><th>' + nombreLocal +
        '</th><th>Empate</th><th>' + nombreVisit + '</th></tr></thead><tbody>' +
        filas + '</tbody></table>'
      : '';

    // Ya NO se marcan "apuestas con valor". Medido en temporadas que el
    // motor no habia visto: apostar donde el motor veia valor sobre la cuota
    // perdio entre un 21% y un 38% de lo apostado. Anunciar valor sin nada
    // que lo respalde es inventar numeros, asi que se dice la verdad.
    var bloqueValor = '<div class="mx-nota">xGol no marca apuestas "de valor": en ' +
      'temporadas que el motor no había visto, apostar donde veía valor sobre la ' +
      'cuota perdió dinero. El mercado de apuestas es muy difícil de batir.</div>';

    var rh = d.rendimiento_historico, bloqueRend = '';
    if (rh && rh.partidos > 0 && rh.log_perdida != null) {
      bloqueRend = '<div class="mx-nota">Historial del motor: <b>' + rh.partidos +
        '</b> partidos evaluados &middot; log-pérdida <b>' + rh.log_perdida.toFixed(4) +
        '</b> (menos es mejor &middot; 1.0986 = no saber nada)' +
        (rh.acierto != null ? ' &middot; acierto <b>' + (rh.acierto * 100).toFixed(1) + '%</b>' : '') +
        '</div>';
    } else if (d.sin_medicion) {
      // La Champions no tiene historico con cuotas: no hay examen a ciegas
      // de esta competicion y hay que decirlo, no dejar que parezca igual de
      // probada que las ligas medidas.
      bloqueRend = '<div class="mx-aviso">Esta competición no tiene medición a ciegas: ' +
        'no existe un histórico con cuotas para examinar el motor en ella. Usa los pesos ' +
        'que mejor funcionaron en las 8 ligas medidas, pero su acierto aquí aún no está ' +
        'comprobado. Se medirá sola con los partidos que se vayan jugando.</div>';
    }

    var avisos = (diag.avisos || []).map(function(a) {
      return '<div class="mx-aviso">' + escapar(a) + '</div>';
    }).join('');

    var etiquetaConf = conf.puntos != null
      ? '<span class="mx-conf mx-conf-' + escapar(conf.nivel) + '">Confianza ' +
        conf.puntos + '/100 &middot; ' + escapar(conf.nivel) + '</span>' : '';

    return '<div class="pr-card mx-card">' +
      '<div class="pr-titulo">De dónde sale este pronóstico ' + etiquetaConf + '</div>' +
      tabla + bloqueValor + bloqueRend + avisos +
      '<div class="mx-nota">Todas las tarjetas de esta pantalla salen de la misma ' +
      'matriz de marcadores, por eso nunca se contradicen entre sí. ' +
      'No es una recomendación de apuesta.</div>' +
    '</div>';
  }

  function banderaFallo(motivo) {
    return '<div class="pr-card mx-card mx-degradado">' +
      '<div class="pr-titulo">Modo limitado</div>' +
      '<div class="mx-aviso">El motor no respondió, así que estos números salen del ' +
      'cálculo local (solo los últimos partidos de cada equipo, sin cuotas). ' +
      'Son menos precisos.</div>' +
      '<div class="mx-nota">Motivo: ' + escapar(motivo) + '</div>' +
    '</div>';
  }

  function insertar(html) {
    var destino = document.getElementById('pronostico-contenido');
    if (!destino) return;
    var vieja = destino.querySelector('.mx-card');
    if (vieja) { vieja.outerHTML = html; return; }
    var cards = destino.querySelectorAll('.pr-card');
    if (cards.length) cards[0].insertAdjacentHTML('afterend', html);
    else destino.insertAdjacentHTML('beforeend', html);
  }

  // ------------------------------------------------------------
  //  renderAll ENVUELTO
  //  1a llamada de un partido: pide el motor y repinta cuando llega.
  //  Siguientes: ya hay datos, se pinta directo y sin parpadeo.
  // ------------------------------------------------------------
  window.renderAll = function() {
    var k = claveActual();

    if (k && datos && clave === k) {          // ya tenemos el motor
      renderOriginal.apply(this, arguments);
      insertar(tarjetaDiagnostico(datos));
      return;
    }

    renderOriginal.apply(this, arguments);    // pinta ya, sin hacer esperar

    if (!k) {
      console.warn('[xGol motor] Falta liga_codigo o id en window.XGOL_PARTIDO. ' +
                   '¿Actualizaste auto.js?');
      insertar(banderaFallo('el partido llegó sin identificador'));
      return;
    }
    if (pidiendo) return;
    pidiendo = true;
    datos = null;
    fallo = null;
    insertar('<div class="pr-card mx-card"><div class="pr-titulo">Calculando con el motor…</div>' +
             '<div class="mx-nota">Ajustando la liga completa y consultando el mercado.</div></div>');

    var p = window.XGOL_PARTIDO || {};
    var q = 'liga=' + encodeURIComponent(p.liga_codigo) +
            '&local=' + encodeURIComponent(names.team1 || '') +
            '&visitante=' + encodeURIComponent(names.team2 || '') +
            '&id_partido=' + encodeURIComponent(p.id) +
            (esNeutral() ? '&neutral=1' : '') +
            (p.utc ? '&fecha=' + encodeURIComponent(String(p.utc).slice(0, 10)) : '');

    fetch(RUTAS.motor + '?' + q, { headers: { 'X-Requested-With': 'fetch' } })
      .then(function(r) { return r.json(); })
      .then(function(d) {
        pidiendo = false;
        if (d.error) {
          fallo = MOTIVOS[d.error] || d.error;
          console.warn('[xGol motor] ' + fallo);
          insertar(banderaFallo(fallo));
          return;
        }
        datos = d;
        clave = k;
        window.renderAll();   // repinta TODO con los numeros del motor
        // La foto del seguimiento se toma con estos numeros, que son los
        // que se ven, y solo si el usuario sigue en este mismo partido
        if (claveActual() === k && typeof window.actualizarFotoPendiente === 'function') {
          window.actualizarFotoPendiente(p.id);
        }
      })
      .catch(function() {
        pidiendo = false;
        fallo = 'falló la conexión con el backend';
        console.warn('[xGol motor] ' + fallo);
        insertar(banderaFallo(fallo));
      });
  };
})();