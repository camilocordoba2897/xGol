// ============================================================
//  LISTA DE PARTIDOS Y NAVEGACION
//
//  Pantalla 1: elige liga y fecha, ve los partidos. Los ya jugados
//  muestran el marcador; los que faltan muestran el boton Pronostico.
//  Pantalla 2: el pronostico, que pinta vista.js.
//
//  NO modifica analizador.js. Solo:
//    1. escribe en state.team1 / state.team2 / names
//    2. llama a renderAll() (la version de vista.js)
//    3. la envuelve para pintar los escudos despues
//
//  Las rutas llegan en window.XGOL_AUTO desde la plantilla.
// ============================================================
(function() {
  var RUTAS = window.XGOL_AUTO || {};
  if (!RUTAS.partidos || !RUTAS.enfrentamiento) return;

  var escudos = { team1: '', team2: '' };
  var cargando = false;
  var ligaActual = '';
  var partidosActuales = [];   // respuesta cruda de la liga elegida
  var fechaFiltro = null;      // 'YYYY-MM-DD' o null = toda la ventana
  var calMes = new Date();
  var calDiaPendiente = null;

  function el(id) { return document.getElementById(id); }

  function ligaNombre() {
    var s = el('auto-liga');
    return (s && s.options[s.selectedIndex]) ? s.options[s.selectedIndex].text : '';
  }

  function escapar(t) {
    return String(t == null ? '' : t)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function fechaISO(d) {
    return d.getFullYear() + '-' +
           String(d.getMonth() + 1).padStart(2, '0') + '-' +
           String(d.getDate()).padStart(2, '0');
  }

  function escudoHTML(url, clase) {
    if (!url) return '<span class="' + clase + ' tp-sin-escudo"></span>';
    return '<img class="' + clase + '" src="' + escapar(url) + '" alt="" loading="lazy">';
  }

  // ============================================================
  //  CAMBIO ENTRE PANTALLAS
  // ============================================================
  function verPantalla(cual) {
    var lista = el('pantalla-lista');
    var pron = el('pantalla-pronostico');
    if (!lista || !pron) return;
    lista.classList.toggle('activa', cual === 'lista');
    pron.classList.toggle('activa', cual === 'pronostico');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
  window.volverALista = function() { verPantalla('lista'); };

  // Lo usa el modo manual: tras cargar los CSV, saltar al pronostico
  window.verPronostico = function() {
    if (!window.state || !state.team1 || !state.team2) {
      alert('Primero carga el historial de los dos equipos.');
      return;
    }
    window.XGOL_PARTIDO = null;   // sin partido de la API: cabecera sin hora
    window.XGOL_H2H = null;       // los CSV no traen enfrentamientos directos
    try { renderAll(); } catch (e) {}
    verPantalla('pronostico');
  };

  // ============================================================
  //  ESCUDOS EN LA CABECERA DEL PRONOSTICO
  //  Se envuelve renderAll en vez de tocar vista.js
  // ============================================================
  var renderAllOriginal = window.renderAll;
  if (typeof renderAllOriginal === 'function') {
    window.renderAll = function() {
      var r = renderAllOriginal.apply(this, arguments);
      try { pintarEscudos(); } catch (e) {}
      return r;
    };
  }

  function pintarEscudos() {
    var equipos = document.querySelectorAll('.pr-header .mteam');
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
  //  LISTA DE PARTIDOS
  // ============================================================
  function mensaje(texto, tipo) {
    var lista = el('lista-partidos');
    if (lista) lista.innerHTML = '<div class="lista-vacia ' + (tipo || '') + '">' + texto + '</div>';
  }

  function pedirJSON(url) {
    return fetch(url, { headers: { 'X-Requested-With': 'fetch' } })
      .then(function(r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      });
  }

  // Salta al Brasileirao si la liga elegida esta en receso
  window.irBrasileirao = function() {
    var s = el('auto-liga');
    if (!s) return;
    s.value = 'BSA';
    try { localStorage.setItem('xgol-auto-liga', 'BSA'); } catch (e) {}
    cargarPartidos('BSA');
  };

  function filtrarPorFecha(lista) {
    if (!fechaFiltro) return lista;
    return lista.filter(function(p) { return (p.utc || '').slice(0, 10) === fechaFiltro; });
  }

  // Deja marcada la ficha de la liga que se esta cargando. El puente de la
  // plantilla solo reacciona al evento 'change', asi que al restaurar la liga
  // guardada en localStorage las fichas se quedaban en Brasileirao mientras
  // se pintaban los partidos de otra liga. Marcarlo aqui lo cubre siempre.
  function marcarFicha(liga) {
    var fichas = document.querySelectorAll('.lab-liga');
    for (var i = 0; i < fichas.length; i++) {
      fichas[i].classList.toggle('activa', fichas[i].getAttribute('data-liga') === liga);
    }
  }

  function cargarPartidos(liga) {
    ligaActual = liga;
    marcarFicha(liga);
    mensaje('Buscando partidos…');
    pedirJSON(RUTAS.partidos + '?liga=' + encodeURIComponent(liga))
      .then(function(d) {
        if (d.error === 'cuota') {
          mensaje('Se alcanzó el límite de consultas por minuto.<br>' +
                  '<span class="auto-pista">Espera un momento y vuelve a elegir la liga.</span>', 'lista-error');
          return;
        }
        if (d.error) {
          mensaje('No se pudo conectar con el proveedor de datos.<br>' +
                  '<span class="auto-pista">Inténtalo de nuevo en unos segundos.</span>', 'lista-error');
          return;
        }
        partidosActuales = d.partidos || [];
        pintarLista(filtrarPorFecha(partidosActuales));
      })
      .catch(function() {
        mensaje('No se pudieron cargar los partidos.<br>' +
                '<span class="auto-pista">Revisa tu conexión e inténtalo de nuevo.</span>', 'lista-error');
      });
  }

  // Bloque de hora: es una pieza propia de la tarjeta, no una columna
  // de texto. Si el partido ya se jugo muestra "Fin" y el dia.
  var DIAS_CORTO = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb'];
  var MESES_CORTO = ['ene', 'feb', 'mar', 'abr', 'may', 'jun',
                     'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

  function bloqueHora(p) {
    var d = new Date(p.utc);
    var valida = !isNaN(d);

    if (p.jugado) {
      var dia = valida ? d.getDate() + ' ' + MESES_CORTO[d.getMonth()] : '';
      return '<div class="tp-hora es-fin">' +
               '<span class="tp-hora-num">Fin</span>' +
               (dia ? '<span class="tp-hora-dia">' + dia + '</span>' : '') +
             '</div>';
    }
    if (!valida) return '<div class="tp-hora"><span class="tp-hora-num">—</span></div>';

    var hh = String(d.getHours()).padStart(2, '0');
    var mm = String(d.getMinutes()).padStart(2, '0');
    var hoy = new Date();
    var etiqueta = (d.toDateString() === hoy.toDateString())
      ? 'hoy' : DIAS_CORTO[d.getDay()] + ' ' + d.getDate();
    return '<div class="tp-hora">' +
             '<span class="tp-hora-num">' + hh + ':' + mm + '</span>' +
             '<span class="tp-hora-dia">' + etiqueta + '</span>' +
           '</div>';
  }

  // Fila de un equipo dentro de la tarjeta: escudo, nombre y gol.
  // Va en rejilla, asi local y visitante comparten las mismas guias.
  function filaEquipo(equipo, goles, ganador) {
    var gol = (goles == null) ? '' :
      '<span class="tp-gol' + (ganador ? ' es-ganador' : '') + '">' +
        escapar(goles) + '</span>';
    return '<div class="tp-equipo">' +
             escudoHTML(equipo.escudo, 'tp-escudo') +
             '<span class="tp-nombre">' + escapar(equipo.nombre) + '</span>' +
             gol +
           '</div>';
  }

  function tarjetaPartido(p, idx) {
    var jugado = !!p.jugado;
    var gl = null, gv = null, ganaL = false, ganaV = false;

    if (jugado) {
      gl = p.goles_local != null ? p.goles_local : '?';
      gv = p.goles_visitante != null ? p.goles_visitante : '?';
      if (p.goles_local != null && p.goles_visitante != null) {
        ganaL = p.goles_local > p.goles_visitante;
        ganaV = p.goles_visitante > p.goles_local;
      }
    }

    var accion = jugado ? '' :
      '<div class="tp-accion">' +
        '<button class="fp-pronostico" data-i="' + idx + '">Pronóstico</button>' +
      '</div>';

    return '<article class="tarjeta-partido' + (jugado ? ' es-jugado' : '') + '">' +
             bloqueHora(p) +
             '<div class="tp-equipos">' +
               filaEquipo(p.local, gl, ganaL) +
               filaEquipo(p.visitante, gv, ganaV) +
             '</div>' +
             accion +
           '</article>';
  }

  function pintarLista(partidos) {
    var lista = el('lista-partidos');
    if (!lista) return;

    if (!partidos.length) {
      if (fechaFiltro) {
        mensaje('Esta liga no tiene partidos ese día.<br>' +
                '<span class="auto-pista">Prueba con otra fecha o pulsa Borrar en el calendario.</span>');
        return;
      }
      mensaje('Esta liga no tiene partidos en la ventana disponible.<br>' +
              '<span class="auto-pista">Las ligas europeas descansan de mayo a agosto. ' +
              'Mientras tanto el <strong>Brasileirão</strong> juega todo el año — ' +
              '<button class="auto-enlace" onclick="irBrasileirao()">ver sus partidos</button></span>');
      return;
    }

    // Se separan en dos grupos guardando el indice ORIGINAL de cada uno:
    // el boton Pronostico lee ese indice para saber que partido abrir, asi
    // que no puede renumerarse al partir la lista.
    var jugados = [], porJugar = [];
    for (var k = 0; k < partidos.length; k++) {
      (partidos[k].jugado ? jugados : porJugar).push({ p: partidos[k], i: k });
    }

    function grupo(items) {
      var html = '';
      for (var n = 0; n < items.length; n++) {
        html += tarjetaPartido(items[n].p, items[n].i);
      }
      return html;
    }

    function encabezado(id, rotulo, detalle, cuantos) {
      return '<div class="lp-seccion"' + (id ? ' id="' + id + '"' : '') + '>' +
               '<h2 class="lp-seccion-titulo">' + rotulo +
                 '<span class="lp-seccion-cuenta">' + cuantos + '</span>' +
               '</h2>' +
               '<p class="lp-seccion-sub">' + detalle + '</p>' +
             '</div>';
    }

    var html = '';

    if (jugados.length) {
      html += encabezado('', 'Partidos que ya se jugaron',
                         'Resultado final. Estos ya no se pueden pronosticar.',
                         jugados.length);
      html += grupo(jugados);
    }

    if (porJugar.length) {
      html += encabezado('lp-por-jugar', 'Partidos que puedes pronosticar',
                         'Toca Pronóstico y xGol calcula las probabilidades del encuentro.',
                         porJugar.length);
      html += grupo(porJugar);
    }

    lista.innerHTML = html;

    var botones = lista.querySelectorAll('.fp-pronostico');
    for (var j = 0; j < botones.length; j++) {
      botones[j].addEventListener('click', function() {
        abrirPronostico(partidos[+this.getAttribute('data-i')], this);
      });
    }

    bajarAPorJugar();
  }

  // ============================================================
  //  LLEVAR AL USUARIO A LOS PARTIDOS QUE SI PUEDE PRONOSTICAR
  //  Solo la primera vez que se pintan partidos: si luego cambia
  //  de liga o de fecha, se respeta donde este mirando.
  // ============================================================
  var yaBajamos = false;

  function bajarAPorJugar() {
    if (yaBajamos) return;

    var destino = el('lp-por-jugar');
    if (!destino) return;   // liga sin partidos por jugar: no hay a donde ir

    yaBajamos = true;

    // Si la guia paso a paso esta abierta, moverse le desordena el foco
    var guia = document.querySelector('.tour-raiz.abierto');
    if (guia) return;

    // El splash tapa la pantalla al entrar: se espera a que se vaya
    var espera = document.getElementById('splash') ? 2200 : 260;
    setTimeout(function() {
      if (document.querySelector('.tour-raiz.abierto')) return;

      // Se descuenta la altura de la barra de ligas, que queda fija arriba,
      // para que el titulo no quede escondido debajo de ella.
      var ligas = document.querySelector('.lab-ligas');
      var alto = ligas ? ligas.getBoundingClientRect().height : 0;
      var y = window.pageYOffset || document.documentElement.scrollTop || 0;
      var arriba = destino.getBoundingClientRect().top + y - alto - 14;

      try {
        window.scrollTo({ top: Math.max(0, arriba), behavior: 'smooth' });
      } catch (e) {
        window.scrollTo(0, Math.max(0, arriba));
      }
    }, espera);
  }

  // ============================================================
  //  ABRIR EL PRONOSTICO DE UN PARTIDO
  // ============================================================
  function abrirPronostico(p, boton) {
    if (cargando || !p) return;
    cargando = true;
    if (boton) { boton.disabled = true; boton.textContent = 'Cargando…'; }

    var liberar = function() {
      cargando = false;
      if (boton) { boton.disabled = false; boton.textContent = 'Pronóstico'; }
    };

    var q = 'local=' + p.local.id + '&visitante=' + p.visitante.id +
            '&nombre_local=' + encodeURIComponent(p.local.nombre) +
            '&nombre_visitante=' + encodeURIComponent(p.visitante.nombre);

    pedirJSON(RUTAS.enfrentamiento + '?' + q)
      .then(function(d) {
        liberar();
        if (d.error === 'cuota') {
          alert('Se alcanzó el límite de consultas por minuto del proveedor. Espera unos segundos y vuelve a intentarlo.');
          return;
        }
        if (d.error) {
          alert('No se pudo traer el historial. Inténtalo de nuevo en un momento.');
          return;
        }
        var fl = (d.local && d.local.filas) || [];
        var fv = (d.visitante && d.visitante.filas) || [];
        if (fl.length < 3 || fv.length < 3) {
          alert('Estos equipos no tienen historial suficiente (mínimo 3 partidos jugados por equipo). Prueba con otro partido.');
          return;
        }

        state.team1 = fl;
        state.team2 = fv;
        names.team1 = d.local.nombre;
        names.team2 = d.visitante.nombre;
        escudos.team1 = p.local.escudo;
        escudos.team2 = p.visitante.escudo;

        // Enfrentamientos directos: los calcula el backend desde el
        // historial largo del local, sin peticiones adicionales.
        window.XGOL_H2H = d.h2h || null;

        // Datos del encuentro para la cabecera (los lee vista.js)
        window.XGOL_PARTIDO = {
          id: p.id,
          liga_codigo: ligaActual,
          utc: p.utc,
          estado: p.estado,
          jugado: !!p.jugado,
          goles_local: p.goles_local,
          goles_visitante: p.goles_visitante,
          jornada: p.jornada,
          liga: ligaNombre()
        };

        try {
          renderAll();
        } catch (err) {
          alert('No se pudo calcular el pronóstico de este partido. Prueba con otro.');
          return;
        }

        // Las cuotas llegan aparte: el pronostico no espera por ellas.
        // Si el proveedor responde, se repinta para incluir la tarjeta.
        pedirCuotas(p);

        // Se apunta como pendiente para evaluarlo cuando se juegue
        if (typeof registrarPendiente === 'function') {
          registrarPendiente({
            id: p.id, local: names.team1, visitante: names.team2,
            liga: ligaNombre(), utc: p.utc
          });
        }

        verPantalla('pronostico');
      })
      .catch(function() {
        liberar();
        alert('Falló la conexión. Revisa tu internet y vuelve a intentarlo.');
      });
  }

  // ============================================================
  //  CUOTAS REALES DE CASAS DE APUESTAS
  //  Se piden despues de pintar el pronostico para no retrasarlo.
  //  Si algo falla la tarjeta no se pinta, pero SIEMPRE se explica
  //  el motivo por consola: si no, es imposible saber que pasa.
  // ============================================================
  var MOTIVOS = {
    sin_clave:   'Falta ODDS_API_KEY en .env y en settings.py. Mientras no este, no hay cuotas.',
    cuota:       'Se agotaron los creditos del plan de the-odds-api (500/mes en el gratuito).',
    red:         'No se pudo conectar con the-odds-api.',
    sin_partido: 'the-odds-api no tiene este partido. Suele ser porque aun no abrio mercado (faltan varios dias) o porque el nombre del equipo no coincide entre los dos proveedores.',
    sin_datos:   'El partido existe pero ninguna casa publica cuotas 1X2 todavia.',
    parametros:  'Faltaron parametros en la peticion.'
  };

  function pedirCuotas(p) {
    window.XGOL_CUOTAS = null;
    if (!RUTAS.cuotas) {
      console.warn('[xGol cuotas] La plantilla no envio la ruta. ¿Actualizaste analizador.html y urls.py?');
      return;
    }
    var q = 'liga=' + encodeURIComponent(ligaActual) +
            '&nombre_local=' + encodeURIComponent(p.local.nombre) +
            '&nombre_visitante=' + encodeURIComponent(p.visitante.nombre);
    pedirJSON(RUTAS.cuotas + '?' + q)
      .then(function(d) {
        if (!d || d.error) {
          var motivo = (d && MOTIVOS[d.error]) || (d && d.error) || 'respuesta vacia';
          console.warn('[xGol cuotas] Sin cuotas para ' + p.local.nombre +
                       ' vs ' + p.visitante.nombre + ' — ' + motivo);
          return;
        }
        if (!d.cuotas) { console.warn('[xGol cuotas] Respuesta sin datos.'); return; }
        console.log('[xGol cuotas] Cuotas cargadas.', d.cuotas);
        window.XGOL_CUOTAS = d.cuotas;
        try { renderAll(); } catch (e) {}
      })
      .catch(function(e) {
        console.warn('[xGol cuotas] Fallo la peticion:', e.message);
      });
  }

  // ============================================================
  //  CALENDARIO — filtra por fecha lo que ya se trajo de la liga
  // ============================================================
  var MESES = ['enero','febrero','marzo','abril','mayo','junio','julio',
               'agosto','septiembre','octubre','noviembre','diciembre'];
  var DIAS_LARGO = ['domingo','lunes','martes','miércoles','jueves','viernes','sábado'];

  window.abrirCalendario = function() {
    calMes = fechaFiltro ? new Date(fechaFiltro + 'T00:00:00') : new Date();
    calDiaPendiente = fechaFiltro;
    pintarCalendario();
    el('fecha-modal-bg').classList.add('show');
  };

  window.fechaCerrar = function() {
    el('fecha-modal-bg').classList.remove('show');
  };

  window.fechaMesAnterior = function() { calMes.setMonth(calMes.getMonth() - 1); pintarCalendario(); };
  window.fechaMesSiguiente = function() { calMes.setMonth(calMes.getMonth() + 1); pintarCalendario(); };

  window.fechaBorrar = function() {
    fechaFiltro = null;
    calDiaPendiente = null;
    actualizarEtiquetaFecha();
    el('fecha-modal-bg').classList.remove('show');
    pintarLista(partidosActuales);
  };

  window.fechaEstablecer = function() {
    fechaFiltro = calDiaPendiente;
    actualizarEtiquetaFecha();
    el('fecha-modal-bg').classList.remove('show');
    pintarLista(filtrarPorFecha(partidosActuales));
  };

  function actualizarEtiquetaFecha() {
    // El dia elegido se muestra DENTRO del boton. Antes iba en un texto
    // aparte ("Todos los partidos") que se quito por no aportar nada
    // cuando no habia filtro; la informacion util no se pierde.
    var etq = el('auto-fecha-etq');
    if (etq) {
      etq.textContent = fechaFiltro
        ? formatoLargo(new Date(fechaFiltro + 'T00:00:00'))
        : 'Fecha';
    }

    var btn = el('auto-fecha-btn');
    if (btn) btn.classList.toggle('tiene-fecha', !!fechaFiltro);
  }

  function formatoLargo(d) {
    return DIAS_LARGO[d.getDay()] + ' ' + d.getDate() + ' de ' + MESES[d.getMonth()];
  }

  function pintarCalendario() {
    el('fecha-modal-year').textContent = calMes.getFullYear();
    el('fecha-mes-nombre').textContent = MESES[calMes.getMonth()] + ' de ' + calMes.getFullYear();
    var pend = calDiaPendiente ? new Date(calDiaPendiente + 'T00:00:00') : new Date();
    el('fecha-modal-fecha').textContent = formatoLargo(pend);

    var primerDia = new Date(calMes.getFullYear(), calMes.getMonth(), 1);
    var diasEnMes = new Date(calMes.getFullYear(), calMes.getMonth() + 1, 0).getDate();
    var offset = primerDia.getDay();
    var hoyISO = fechaISO(new Date());

    // Dias que si tienen partidos en la liga elegida
    var conPartido = {};
    partidosActuales.forEach(function(p) { conPartido[(p.utc || '').slice(0, 10)] = true; });

    var html = '', v, d;
    for (v = 0; v < offset; v++) html += '<span class="fecha-dia vacio"></span>';
    for (d = 1; d <= diasEnMes; d++) {
      var iso = calMes.getFullYear() + '-' +
                String(calMes.getMonth() + 1).padStart(2, '0') + '-' +
                String(d).padStart(2, '0');
      var clases = 'fecha-dia' +
                   (iso === calDiaPendiente ? ' sel' : '') +
                   (iso === hoyISO ? ' hoy' : '') +
                   (conPartido[iso] ? ' con-partido' : '');
      html += '<button type="button" class="' + clases + '" data-iso="' + iso + '">' + d + '</button>';
    }
    el('fecha-grid').innerHTML = html;

    var botones = el('fecha-grid').querySelectorAll('.fecha-dia:not(.vacio)');
    for (var b = 0; b < botones.length; b++) {
      botones[b].addEventListener('click', function() {
        calDiaPendiente = this.getAttribute('data-iso');
        pintarCalendario();
      });
    }
  }

  // ============================================================
  //  ARRANQUE
  // ============================================================
  function iniciar() {
    var selector = el('auto-liga');
    if (!selector) return;

    actualizarEtiquetaFecha();

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