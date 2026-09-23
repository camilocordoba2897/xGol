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
  var MERCADOS_DEL_MOTOR = { '1X2': true, 'Goles': true, 'BTTS': true };

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

  // ------------------------------------------------------------
  //  FOTO DEL PRONOSTICO ANTES DEL PARTIDO
  //  Antes, al evaluar, las probabilidades se RECALCULABAN con el historial
  //  cargado en ese momento. Pero para evaluar habia que volver a abrir el
  //  partido despues de jugado, y el historial descargado entonces YA TRAIA
  //  ese resultado: el modelo "acertaba" algo que ya sabia y el acierto del
  //  panel se inflaba (58 % paso a 72 % sin que el motor mejorara).
  //  Ahora se guarda aqui el historial de antes del saque y las
  //  probabilidades exactas que se mostraron, y se evalua con eso.
  // ------------------------------------------------------------
  function fotoDelPronostico() {
    if (typeof state === 'undefined' || !state.team1 || !state.team2) return null;
    try {
      var s1 = computeStats(state.team1), s2 = computeStats(state.team2);
      var modelo = buildModel(s1, s2);
      var specs = buildBetSpecs(s1, s2, modelo);
      var probs = {};
      for (var i = 0; i < specs.length; i++) {
        // Solo lo que sale de la matriz del motor. Corners, tiros, tarjetas
        // y mitades los calcula otra cosa (promedios de 15 partidos o un
        // reparto fijo) y ni siquiera se muestran en el pronostico.
        if (!MERCADOS_DEL_MOTOR[specs[i].market]) continue;
        if (typeof specs[i].prob === 'number') probs[specs[i].label] = specs[i].prob;
      }
      var foto = { filas1: state.team1, filas2: state.team2, probs: probs };
      // La matriz solo cuando es la del motor de verdad (con fuentes). Con
      // ella se evalua despues, y las lineas de goles salen identicas.
      if (modelo && modelo.motorFuentes && modelo.motorFuentes.length && modelo.mat) {
        foto.mat = modelo.mat;
      }
      return foto;
    } catch (e) { return null; }
  }

  // Lo llama auto.js justo despues de cargar un enfrentamiento
  window.registrarPendiente = function(datos) {
    if (!datos || !datos.id) return;
    // Un partido que ya empezo no se apunta: su pronostico ya no es previo
    var saque = datos.utc ? new Date(datos.utc).getTime() : NaN;
    if (!isNaN(saque) && saque <= Date.now()) return;
    var foto = fotoDelPronostico();
    if (!foto) return;
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
      guardado: Date.now(),
      foto: foto
    });
    guardarPendientes(lista);
    pintarAviso();
  };

  // auto.js apunta el pendiente justo despues del primer pintado, cuando el
  // motor todavia no ha respondido: en ese instante buildModel es el calculo
  // local de 15 partidos, NO lo que el usuario ve un segundo despues. Sin
  // esto el seguimiento media un modelo que no se muestra en pantalla.
  // motor.js llama aqui en cuanto repinta con los numeros del motor.
  window.actualizarFotoPendiente = function(id) {
    if (!id) return;
    var lista = leerPendientes();
    for (var i = 0; i < lista.length; i++) {
      if (lista[i].id !== id) continue;
      var saque = lista[i].utc ? new Date(lista[i].utc).getTime() : NaN;
      if (!isNaN(saque) && saque <= Date.now()) return;   // ya no es previo
      var foto = fotoDelPronostico();
      if (!foto) return;
      if (!foto.mat) return;   // el motor no dio matriz: se queda la anterior
      foto.motor = true;
      lista[i].foto = foto;
      guardarPendientes(lista);
      return;
    }
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

  // Evalua un partido terminado con la FOTO tomada antes del saque. Ya no
  // hace falta volver a abrir el partido: se evalua solo.
  function evaluar(pendiente, resultado) {
    //Pendientes viejos, guardados sin foto: no hay forma de saber que se
    //pronostico antes del partido, asi que no entran al registro.
    if (!pendiente.foto || !pendiente.foto.probs) { quitarPendiente(pendiente.id); return 0; }
    //Fotos tomadas antes de que respondiera el motor (todas las anteriores a
    //esta correccion, y las de "modo limitado"): son del calculo local, no
    //del motor que se mide aqui. Tampoco entran.
    if (!pendiente.foto.motor) { quitarPendiente(pendiente.id); return 0; }

    var fecha = (resultado.utc || '').slice(0, 10) || new Date().toISOString().slice(0, 10);
    if (yaRegistrado(pendiente.local, pendiente.visitante, fecha)) { quitarPendiente(pendiente.id); return 0; }

    //Las etiquetas de las apuestas llevan el nombre de los equipos cargados
    //("Gana Arsenal"): se ponen los del pendiente mientras se arman.
    var antes = { team1: names.team1, team2: names.team2 };
    var specs;
    try {
      names.team1 = pendiente.local;
      names.team2 = pendiente.visitante;
      var s1 = computeStats(pendiente.foto.filas1);
      var s2 = computeStats(pendiente.foto.filas2);
      // Con la matriz que se mostro antes del saque: las lineas de goles
      // ("Mas de 2.5", "Mas de 3.5"...) dependen de ella. Con otro modelo
      // saldrian otras lineas y las de la foto se perderian sin evaluar.
      var modelo = (pendiente.foto.mat && typeof window.modeloDesdeMatriz === 'function')
        ? window.modeloDesdeMatriz(pendiente.foto.mat)
        : buildModel(s1, s2);
      specs = buildBetSpecs(s1, s2, modelo);
    } catch (e) {
      specs = [];
    } finally {
      names.team1 = antes.team1;
      names.team2 = antes.team2;
    }

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
      //Solo cuentan las lineas que de verdad se mostraron antes del partido,
      //y con la probabilidad que se mostro, no con una recalculada.
      var prob = pendiente.foto.probs[sp.label];
      if (typeof prob !== 'number') continue;
      var r;
      try { r = sp.resolve(a); } catch (e) { continue; }
      if (r === null || r === undefined) continue;
      betLog.push({
        ts: ts, date: fecha,
        team1: pendiente.local, team2: pendiente.visitante,
        league: pendiente.liga || resultado.liga || '',
        market: sp.market, icon: sp.icon, label: sp.label,
        prob: prob, hit: !!r, auto: true
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

  var esperas = 0;
  function revisar(manual) {
    if (revisando || !RUTAS.resultados) return;
    // Sin el registro cargado no se evalua: lo evaluado no se podria guardar
    // y el pendiente se perderia. Se reintenta un rato (conexion lenta).
    if (!window.XGOL_BETLOG_LISTO) {
      if (esperas++ < 10) setTimeout(function() { revisar(manual); }, 3000);
      return;
    }
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
          // Terminaron pero no se pudieron evaluar (pendientes viejos sin foto)
          avisar('Hay ' + terminados + ' partido' + (terminados > 1 ? 's' : '') +
                 ' terminado' + (terminados > 1 ? 's' : '') +
                 ' que se guardaron sin su pronóstico previo: no se cuentan.', 'aviso');
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