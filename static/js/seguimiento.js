// ============================================================
//  SEGUIMIENTO AUTOMATICO DE PREDICCIONES
//
//  Cierra el circulo del analizador:
//    1. Al analizar un partido se guarda como PENDIENTE (id + equipos).
//    2. Cada vez que se abre el analizador se consultan los marcadores
//       reales de los pendientes.
//    3. Los que ya terminaron se evaluan solos y entran al historial
//       de Rendimiento. El usuario no escribe ningun resultado.
//
//  No modifica analizador.js: reutiliza sus funciones globales
//  (buildBetSpecs, computeStats, buildModel, betLog, saveBetLog).
//
//  Los mercados sin dato en la API (corners, tarjetas, tiros) llegan
//  como null y sus specs devuelven null: NO se cuentan como fallo.
// ============================================================
(function() {
  var RUTAS = window.XGOL_AUTO || {};
  var CLAVE = 'xgol-pendientes';
  var MAX_PENDIENTES = 40;

  // ------------------------------------------------------------
  //  ALMACEN DE PENDIENTES (navegador)
  // ------------------------------------------------------------
  function leerPendientes() {
    try {
      var crudo = localStorage.getItem(CLAVE);
      var lista = crudo ? JSON.parse(crudo) : [];
      return Object.prototype.toString.call(lista) === '[object Array]' ? lista : [];
    } catch (e) { return []; }
  }

  function guardarPendientes(lista) {
    try { localStorage.setItem(CLAVE, JSON.stringify(lista.slice(-MAX_PENDIENTES))); } catch (e) {}
  }

  // Lo llama auto.js justo despues de cargar un enfrentamiento
  window.registrarPendiente = function(datos) {
    if (!datos || !datos.id) return;
    var lista = leerPendientes();
    for (var i = 0; i < lista.length; i++) {
      if (lista[i].id === datos.id) return;   // ya estaba
    }
    lista.push({
      id: datos.id,
      local: datos.local,
      visitante: datos.visitante,
      liga: datos.liga || '',
      utc: datos.utc || '',
      guardado: Date.now()
    });
    guardarPendientes(lista);
    pintarAviso();
  };

  function quitarPendiente(id) {
    var lista = leerPendientes().filter(function(p) { return p.id !== id; });
    guardarPendientes(lista);
  }

  // ------------------------------------------------------------
  //  EVALUACION
  // ------------------------------------------------------------
  // Un partido ya evaluado no se vuelve a registrar
  function yaRegistrado(local, visitante, fecha) {
    if (typeof betLog === 'undefined') return false;
    for (var i = 0; i < betLog.length; i++) {
      var r = betLog[i];
      if (r.team1 === local && r.team2 === visitante && r.date === fecha) return true;
    }
    return false;
  }

  // Evalua un partido terminado usando el modelo del historial actual
  function evaluar(pendiente, resultado) {
    if (typeof state === 'undefined' || !state.team1 || !state.team2) return 0;
    if (names.team1 !== pendiente.local || names.team2 !== pendiente.visitante) return 0;

    var fecha = (resultado.utc || '').slice(0, 10) || new Date().toISOString().slice(0, 10);
    if (yaRegistrado(pendiente.local, pendiente.visitante, fecha)) { quitarPendiente(pendiente.id); return 0; }

    var s1 = computeStats(state.team1);
    var s2 = computeStats(state.team2);
    var model = buildModel(s1, s2);
    var specs = buildBetSpecs(s1, s2, model);

    // Los null se quedan null a proposito: el spec devuelve null y se salta
    var a = {
      gf: resultado.gf, gc: resultado.gc,
      g1f: resultado.g1f, g1c: resultado.g1c,
      cf: resultado.cf, cc: resultado.cc,
      sf: resultado.sf, sc: resultado.sc,
      tf: resultado.tf, tc: resultado.tc,
      cards: resultado.cards
    };

    var ts = Date.now();
    var añadidas = 0, aciertos = 0;
    for (var i = 0; i < specs.length; i++) {
      var sp = specs[i];
      var r;
      try { r = sp.resolve(a); } catch (e) { continue; }
      if (r === null || r === undefined) continue;
      betLog.push({
        ts: ts, date: fecha,
        team1: pendiente.local, team2: pendiente.visitante,
        league: pendiente.liga || resultado.liga || '',
        market: sp.market, icon: sp.icon, label: sp.label,
        prob: sp.prob, hit: !!r, auto: true
      });
      añadidas++;
      if (r) aciertos++;
    }
    if (!añadidas) { quitarPendiente(pendiente.id); return 0; }

    betLogMeta[ts] = { a: a, league: pendiente.liga || '', date: fecha,
                       team1: pendiente.local, team2: pendiente.visitante };
    saveBetLog();
    quitarPendiente(pendiente.id);
    return { añadidas: añadidas, aciertos: aciertos, gf: resultado.gf, gc: resultado.gc };
  }

  // ------------------------------------------------------------
  //  REVISION DE PENDIENTES
  // ------------------------------------------------------------
  var revisando = false;

  function revisar(manual) {
    if (revisando || !RUTAS.resultados) return;
    var lista = leerPendientes();
    if (!lista.length) { if (manual) avisar('No hay partidos pendientes de resultado.'); return; }

    // Solo tiene sentido preguntar por los que ya deberian haber terminado
    var ahora = Date.now();
    var maduros = lista.filter(function(p) {
      if (!p.utc) return true;
      var fin = new Date(p.utc).getTime();
      return isNaN(fin) ? true : ahora > fin + 2.5 * 3600 * 1000;
    });
    if (!maduros.length) {
      if (manual) avisar('Los ' + lista.length + ' partidos pendientes aún no se han jugado.');
      pintarAviso();
      return;
    }

    revisando = true;
    if (manual) avisar('Consultando resultados…');
    var ids = maduros.slice(0, 8).map(function(p) { return p.id; }).join(',');

    fetch(RUTAS.resultados + '?ids=' + ids, { headers: { 'X-Requested-With': 'fetch' } })
      .then(function(r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function(d) {
        revisando = false;
        if (d.error === 'cuota') { if (manual) avisar('Límite de consultas alcanzado. Prueba en un minuto.'); return; }
        if (d.error) { if (manual) avisar('No se pudo consultar los resultados.'); return; }

        var res = d.resultados || {};
        var evaluados = 0, terminados = 0, detalle = '';
        for (var i = 0; i < maduros.length; i++) {
          var p = maduros[i];
          var r = res[String(p.id)];
          if (!r || !r.terminado) continue;
          terminados++;
          var salida = evaluar(p, r);
          if (salida) {
            evaluados++;
            detalle = p.local + ' ' + salida.gf + '–' + salida.gc + ' ' + p.visitante +
                      ' · ' + salida.aciertos + '/' + salida.añadidas + ' acertadas';
          }
        }

        if (evaluados) {
          avisar('✅ Evaluado automáticamente: ' + detalle, 'ok');
          if (typeof renderValidation === 'function') renderValidation();
        } else if (terminados) {
          // Terminaron pero no eran el partido cargado: se necesita su modelo
          avisar('Hay ' + terminados + ' partido' + (terminados > 1 ? 's' : '') +
                 ' terminado' + (terminados > 1 ? 's' : '') +
                 '. Cárgalo en Datos y vuelve aquí para que se evalúe.', 'aviso');
        } else if (manual) {
          avisar('Los partidos pendientes todavía no han terminado.');
        }
        pintarAviso();
      })
      .catch(function() {
        revisando = false;
        if (manual) avisar('Falló la conexión al consultar resultados.');
      });
  }

  // ------------------------------------------------------------
  //  AVISO EN LA PESTAÑA RENDIMIENTO
  // ------------------------------------------------------------
  function avisar(texto, tipo) {
    var caja = document.getElementById('seg-aviso');
    if (!caja) return;
    caja.className = 'seg-aviso ' + (tipo || '');
    caja.innerHTML = texto;
    caja.style.display = 'block';
  }

  function pintarAviso() {
    var barra = document.getElementById('seg-barra');
    if (!barra) return;
    var lista = leerPendientes();
    var txt = lista.length
      ? '<strong>' + lista.length + '</strong> partido' + (lista.length > 1 ? 's' : '') + ' esperando resultado'
      : 'Sin partidos pendientes';
    barra.querySelector('.seg-cuenta').innerHTML = txt;
  }

  window.revisarResultadosAuto = function() { revisar(true); };

  // Inserta la barra dentro de Rendimiento (se pinta cada vez que se re-renderiza)
  function montarBarra() {
    var seccion = document.getElementById('tab-validation');
    if (!seccion || document.getElementById('seg-barra')) return;
    var barra = document.createElement('div');
    barra.id = 'seg-barra';
    barra.className = 'seg-barra';
    barra.innerHTML =
      '<span class="seg-punto"></span>' +
      '<span class="seg-cuenta"></span>' +
      '<button class="seg-btn" onclick="revisarResultadosAuto()">Consultar resultados</button>';
    seccion.insertBefore(barra, seccion.firstChild);
    var aviso = document.createElement('div');
    aviso.id = 'seg-aviso';
    aviso.className = 'seg-aviso';
    seccion.insertBefore(aviso, barra.nextSibling);
    pintarAviso();
  }

  // ------------------------------------------------------------
  //  ARRANQUE
  // ------------------------------------------------------------
  function iniciar() {
    montarBarra();
    // Revision silenciosa al entrar: si algo termino, ya queda evaluado
    setTimeout(function() { revisar(false); }, 2500);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', iniciar);
  } else {
    iniciar();
  }
})();