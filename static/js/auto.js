// ============================================================
//  ANALIZADOR AUTOMATICO — seleccion de partidos desde la API
//
//  Llena el motor sin CSV: elige liga, toca un partido y se cargan
//  los historiales de ambos equipos.
//
//  NO modifica analizador.js. Solo hace tres cosas:
//    1. escribe en state.team1 / state.team2 / names
//    2. llama a renderAll() (la funcion original, intacta)
//    3. envuelve renderAll para pintar los escudos despues
//
//  Las rutas llegan en window.XGOL_AUTO desde el template.
// ============================================================
(function() {
  var RUTAS = window.XGOL_AUTO || {};
  if (!RUTAS.partidos || !RUTAS.enfrentamiento) return;

  var escudos = { team1: '', team2: '' };
  var cargando = false;
  var partidoActual = null;
  var ligaActual = '';

  // El ranking FIFA solo tiene sentido con selecciones. En ligas de clubes
  // ningun rival aparece en la lista, asi que el motor no aplica ajuste
  // (rivalKnown = false -> factor 1) pero la interfaz igual pinta avisos y
  // "#130" en todos lados. Con clubes esos bloques se quitan del DOM.
  var LIGAS_SELECCIONES = ['EC', 'WC'];
  function usaFIFA() { return LIGAS_SELECCIONES.indexOf(ligaActual) !== -1; }

  function el(id) { return document.getElementById(id); }

  function ligaNombre() {
    var s = el('auto-liga');
    return (s && s.options[s.selectedIndex]) ? s.options[s.selectedIndex].text : '';
  }

  // ---- Fecha y hora del partido en formato corto ----
  function cuando(utc) {
    if (!utc) return '';
    var d = new Date(utc);
    if (isNaN(d)) return '';
    var dias = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb'];
    var hh = String(d.getHours()).padStart(2, '0');
    var mm = String(d.getMinutes()).padStart(2, '0');
    var hoy = new Date();
    var mismoDia = d.toDateString() === hoy.toDateString();
    if (mismoDia) return 'Hoy · ' + hh + ':' + mm;
    return dias[d.getDay()] + ' ' + d.getDate() + ' · ' + hh + ':' + mm;
  }

  function escudoHTML(url, clase) {
    if (!url) return '<span class="' + clase + ' auto-sin-escudo"></span>';
    return '<img class="' + clase + '" src="' + url + '" alt="" loading="lazy">';
  }

  // ============================================================
  //  ESCUDOS EN LA CABECERA DEL ANALISIS
  //  Se envuelve renderAll en vez de tocar analizador.js
  // ============================================================
  var renderAllOriginal = window.renderAll;
  if (typeof renderAllOriginal === 'function') {
    window.renderAll = function() {
      var r = renderAllOriginal.apply(this, arguments);
      try { pintarEscudos(); } catch (e) {}
      try { if (!usaFIFA()) limpiarFIFA(); } catch (e) {}
      return r;
    };
  }

  function pintarEscudos() {
    var equipos = document.querySelectorAll('.match-header .mteam');
    if (equipos.length < 2) return;
    ponerEscudo(equipos[0], escudos.team1);
    ponerEscudo(equipos[1], escudos.team2);
  }

  function ponerEscudo(nodo, url) {
    if (!url) return;
    var previo = nodo.querySelector('.mteam-escudo');
    if (previo) { if (previo.src === url) return; previo.remove(); }
    var img = document.createElement('img');
    img.className = 'mteam-escudo';
    img.src = url;
    img.alt = '';
    nodo.insertBefore(img, nodo.firstChild);
  }

  // ============================================================
  //  LIMPIEZA DE BLOQUES FIFA (solo en ligas de clubes)
  //  No se toca analizador.js: se quitan del DOM despues de pintar.
  // ============================================================
  function limpiarFIFA() {
    // Avisos "Rivales no encontrados en ranking FIFA"
    var avisos = document.querySelectorAll('.warning-box');
    for (var i = 0; i < avisos.length; i++) {
      if (avisos[i].textContent.indexOf('ranking FIFA') !== -1) avisos[i].remove();
    }
    // Bloque "Ultimos rivales (ranking FIFA)" y sus etiquetas
    var bloques = document.querySelectorAll('.team-card div');
    for (var j = 0; j < bloques.length; j++) {
      if (bloques[j].textContent.trim().indexOf('Últimos rivales') === 0) {
        var etiquetas = bloques[j].nextElementSibling;
        if (etiquetas) etiquetas.remove();
        bloques[j].remove();
      }
    }
    // Fila "Dificultad calendario" (con clubes siempre daria 0% = "Baja")
    var filas = document.querySelectorAll('.team-card .stat-row');
    for (var k = 0; k < filas.length; k++) {
      var etiqueta = filas[k].querySelector('.stat-label');
      if (etiqueta && etiqueta.textContent.trim() === 'Dificultad calendario') filas[k].remove();
    }
  }

  // ============================================================
  //  LISTA DE PARTIDOS
  // ============================================================
  function mensaje(texto, tipo) {
    var lista = el('auto-lista');
    if (lista) lista.innerHTML = '<div class="auto-vacio ' + (tipo || '') + '">' + texto + '</div>';
  }

  // Salta directo al Brasileirao si la liga elegida esta en receso
  window.autoIrBrasileirao = function() {
    var s = el('auto-liga');
    if (!s) return;
    s.value = 'BSA';
    try { localStorage.setItem('xgol-auto-liga', 'BSA'); } catch (e) {}
    cargarPartidos('BSA');
  };

  function pedirJSON(url) {
    return fetch(url, { headers: { 'X-Requested-With': 'fetch' } })
      .then(function(r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      });
  }

  function cargarPartidos(liga) {
    ligaActual = liga;
    mensaje('Buscando partidos…');
    pedirJSON(RUTAS.partidos + '?liga=' + encodeURIComponent(liga))
      .then(function(d) {
        if (d.error === 'cuota') {
          mensaje('Se alcanzó el límite de consultas por minuto.<br>' +
                  '<span class="auto-pista">Espera un momento y vuelve a elegir la liga.</span>', 'auto-error');
          return;
        }
        if (d.error) {
          mensaje('No se pudo conectar con el proveedor de datos.<br>' +
                  '<span class="auto-pista">Inténtalo de nuevo en unos segundos.</span>', 'auto-error');
          return;
        }
        pintarLista(d.partidos || []);
      })
      .catch(function() {
        mensaje('No se pudieron cargar los partidos.<br>' +
                '<span class="auto-pista">Revisa tu conexión e inténtalo de nuevo.</span>', 'auto-error');
      });
  }

  function pintarLista(partidos) {
    var lista = el('auto-lista');
    if (!lista) return;
    if (!partidos.length) {
      mensaje('Esta liga no tiene partidos programados en los próximos 45 días.<br>' +
              '<span class="auto-pista">Las ligas europeas descansan de mayo a agosto. ' +
              'Mientras tanto el <strong>Brasileirão</strong> juega todo el año — ' +
              '<button class="auto-enlace" onclick="autoIrBrasileirao()">ver sus partidos</button></span>');
      return;
    }
    var html = '';
    for (var i = 0; i < partidos.length; i++) {
      var p = partidos[i];
      html += '<button class="auto-partido" data-i="' + i + '">' +
        '<span class="auto-lado">' + escudoHTML(p.local.escudo, 'auto-escudo') +
          '<span class="auto-nombre">' + p.local.nombre + '</span></span>' +
        '<span class="auto-vs">vs</span>' +
        '<span class="auto-lado auto-lado-der"><span class="auto-nombre">' + p.visitante.nombre + '</span>' +
          escudoHTML(p.visitante.escudo, 'auto-escudo') + '</span>' +
        '<span class="auto-cuando">' + cuando(p.utc) + '</span>' +
      '</button>';
    }
    lista.innerHTML = html;
    var botones = lista.querySelectorAll('.auto-partido');
    for (var j = 0; j < botones.length; j++) {
      botones[j].addEventListener('click', function() {
        cargarEnfrentamiento(partidos[+this.getAttribute('data-i')], this);
      });
    }
  }

  // ============================================================
  //  CARGA DEL ENFRENTAMIENTO EN EL MOTOR
  // ============================================================
  function cargarEnfrentamiento(p, boton) {
    if (cargando) return;
    cargando = true;
    partidoActual = p;

    var lista = el('auto-lista');
    if (lista) {
      var otros = lista.querySelectorAll('.auto-partido');
      for (var k = 0; k < otros.length; k++) otros[k].classList.remove('activo');
    }
    if (boton) { boton.classList.add('activo'); boton.classList.add('cargando'); }
    estado('<span class="auto-spinner"></span>Analizando ' + p.local.nombre + ' vs ' + p.visitante.nombre + '…');

    // Pase lo que pase, el selector vuelve a quedar utilizable
    var liberar = function() {
      cargando = false;
      if (boton) boton.classList.remove('cargando');
    };

    var q = 'local=' + p.local.id + '&visitante=' + p.visitante.id +
            '&nombre_local=' + encodeURIComponent(p.local.nombre) +
            '&nombre_visitante=' + encodeURIComponent(p.visitante.nombre);

    pedirJSON(RUTAS.enfrentamiento + '?' + q)
      .then(function(d) {
        liberar();
        if (d.error === 'cuota') {
          estado('Se alcanzó el límite de consultas por minuto del proveedor. Espera unos segundos y vuelve a tocar el partido.', 'auto-error');
          return;
        }
        if (d.error) {
          estado('No se pudo traer el historial. Inténtalo de nuevo en un momento.', 'auto-error');
          return;
        }
        var fl = (d.local && d.local.filas) || [];
        var fv = (d.visitante && d.visitante.filas) || [];
        if (fl.length < 3 || fv.length < 3) {
          estado('Estos equipos no tienen historial suficiente (se necesitan al menos 3 partidos jugados por equipo). Prueba con otro partido.', 'auto-error');
          return;
        }

        state.team1 = fl;
        state.team2 = fv;
        names.team1 = d.local.nombre;
        names.team2 = d.visitante.nombre;
        escudos.team1 = p.local.escudo;
        escudos.team2 = p.visitante.escudo;

        // El motor puede fallar con datos raros: si revienta, el usuario debe enterarse
        try {
          renderAll();
        } catch (err) {
          estado('No se pudo calcular la predicción de este partido. Prueba con otro.', 'auto-error');
          return;
        }

        // Se apunta como pendiente para evaluarlo solo cuando se juegue
        if (typeof registrarPendiente === 'function') {
          registrarPendiente({
            id: p.id, local: names.team1, visitante: names.team2,
            liga: ligaNombre(), utc: p.utc
          });
        }

        estado('✅ ' + names.team1 + ' (' + fl.length + ' partidos) · ' + names.team2 + ' (' + fv.length + ' partidos) — predicción lista', 'auto-ok');
        if (typeof showTab === 'function') showTab('analysis');
        window.scrollTo({ top: 0, behavior: 'smooth' });
      })
      .catch(function() {
        liberar();
        estado('Falló la conexión. Revisa tu internet y vuelve a tocar el partido.', 'auto-error');
      });
  }

  function estado(texto, tipo) {
    var e = el('auto-estado');
    if (!e) return;
    e.className = 'auto-estado ' + (tipo || '');
    e.innerHTML = texto;
    e.style.display = 'block';
  }

  // ============================================================
  //  ARRANQUE
  // ============================================================
  function iniciar() {
    var selector = el('auto-liga');
    if (!selector) return;

    // El banner de sesion vive dentro del modo manual: lo subimos al selector
    var banner = el('session-banner');
    var caja = el('auto-box');
    if (banner && caja) caja.appendChild(banner);

    var guardada = null;
    try { guardada = localStorage.getItem('xgol-auto-liga'); } catch (e) {}
    if (guardada) {
      for (var i = 0; i < selector.options.length; i++) {
        if (selector.options[i].value === guardada) { selector.value = guardada; break; }
      }
    }

    selector.addEventListener('change', function() {
      try { localStorage.setItem('xgol-auto-liga', this.value); } catch (e) {}
      cargarPartidos(this.value);
    });

    cargarPartidos(selector.value);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', iniciar);
  } else {
    iniciar();
  }
})();