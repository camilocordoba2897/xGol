// ============================================================
//  TOUR GUIADO DEL ANALIZADOR
//
//  Muestra paso a paso donde tiene que tocar el usuario, con un
//  foco sobre el elemento real y un mensaje flotante al lado.
//  Se abre solo la primera vez y desde el boton "Cómo funciona".
//
//  NO toca analizador.js ni auto.js: solo lee el DOM y resalta.
//  Si un elemento no existe (por ejemplo las pestañas de admin en
//  una cuenta normal), ese paso se salta sin romper el recorrido.
// ============================================================
(function() {
  var CLAVE = 'xgol-tour-analizador';
  var MARGEN = 8;        // aire entre el foco y el borde del elemento
  var SEPARACION = 14;   // distancia del globo al foco

  // ---- Pasos. selector null = mensaje centrado, sin foco ----
  var PASOS = [
    {
      selector: null,
      titulo: 'Bienvenido al analizador',
      texto: 'Te muestro en 6 pasos cómo predecir un partido. Dura menos de un minuto y puedes salir cuando quieras.'
    },
    {
      selector: '#auto-liga',
      titulo: '1 · Elige la liga',
      texto: 'Aquí escoges la competencia. El <strong>Brasileirão</strong> juega todo el año; las ligas europeas descansan de mayo a agosto.'
    },
    {
      selector: '#auto-lista',
      titulo: '2 · Toca un partido',
      texto: 'Aparecen los próximos partidos con sus escudos. Toca uno y se traen solos los últimos 15 encuentros de cada equipo. Justo debajo te aviso si la carga salió bien.'
    },
    {
      selector: '.tabs .tab:nth-child(2)',
      titulo: '3 · Mira el análisis',
      texto: 'Al cargar el partido saltas aquí solo. Verás los goles esperados de cada equipo, su forma reciente y la probabilidad de cada resultado.'
    },
    {
      selector: '.tabs .tab:nth-child(3)',
      titulo: '4 · Revisa las predicciones',
      texto: 'El detalle por mercado: ganador, más o menos goles, ambos anotan, marcador exacto y mitades. Cada uno con su probabilidad.'
    },
    {
      selector: '#modo-manual',
      titulo: '5 · Modo manual (opcional)',
      texto: 'Si tienes datos propios en CSV, aquí los cargas. Trae estadísticas que la API gratuita no da: córners, tarjetas, tiros y jugadores.'
    },
    {
      selector: '.modo-btn',
      titulo: '6 · Cambia el tema',
      texto: 'Alterna entre modo claro y oscuro. Tu elección se recuerda para la próxima vez.'
    },
    {
      selector: null,
      titulo: 'Listo para empezar',
      texto: 'Recuerda: las probabilidades son <strong>estimaciones estadísticas</strong>, no certezas. Un 70% significa que se cumple unas 7 de cada 10 veces.<br><br>Puedes volver a ver esta guía cuando quieras con el botón <strong>?</strong> de arriba.'
    }
  ];

  var indice = 0;
  var abierto = false;
  var nodos = {};

  function el(sel) { try { return document.querySelector(sel); } catch (e) { return null; } }

  // Un elemento sirve si existe y ocupa espacio en pantalla
  function utilizable(paso) {
    if (!paso.selector) return true;
    var n = el(paso.selector);
    if (!n) return false;
    var r = n.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }

  // ============================================================
  //  CONSTRUCCION DEL DOM (una sola vez)
  // ============================================================
  function construir() {
    if (nodos.raiz) return;

    var raiz = document.createElement('div');
    raiz.className = 'tour-raiz';
    raiz.setAttribute('role', 'dialog');
    raiz.setAttribute('aria-modal', 'true');
    raiz.innerHTML =
      '<div class="tour-velo"></div>' +
      '<div class="tour-foco"></div>' +
      '<div class="tour-globo">' +
        '<button class="tour-cerrar" aria-label="Cerrar guía">&times;</button>' +
        '<div class="tour-titulo"></div>' +
        '<div class="tour-texto"></div>' +
        '<div class="tour-pie">' +
          '<div class="tour-puntos"></div>' +
          '<div class="tour-botones">' +
            '<button class="tour-atras">Atrás</button>' +
            '<button class="tour-siguiente">Siguiente</button>' +
          '</div>' +
        '</div>' +
      '</div>';
    document.body.appendChild(raiz);

    nodos.raiz = raiz;
    nodos.velo = raiz.querySelector('.tour-velo');
    nodos.foco = raiz.querySelector('.tour-foco');
    nodos.globo = raiz.querySelector('.tour-globo');
    nodos.titulo = raiz.querySelector('.tour-titulo');
    nodos.texto = raiz.querySelector('.tour-texto');
    nodos.puntos = raiz.querySelector('.tour-puntos');
    nodos.atras = raiz.querySelector('.tour-atras');
    nodos.siguiente = raiz.querySelector('.tour-siguiente');

    raiz.querySelector('.tour-cerrar').addEventListener('click', cerrar);
    nodos.velo.addEventListener('click', cerrar);
    nodos.atras.addEventListener('click', function() { mover(-1); });
    nodos.siguiente.addEventListener('click', function() { mover(1); });
  }

  // ============================================================
  //  POSICIONAMIENTO
  // ============================================================
  function colocar() {
    var paso = PASOS[indice];
    var objetivo = paso.selector ? el(paso.selector) : null;

    if (!objetivo) {
      nodos.foco.style.display = 'none';
      nodos.globo.className = 'tour-globo tour-centrado';
      nodos.globo.style.top = '';
      nodos.globo.style.left = '';
      return;
    }

    var r = objetivo.getBoundingClientRect();
    nodos.foco.style.display = 'block';
    nodos.foco.style.top = (r.top - MARGEN) + 'px';
    nodos.foco.style.left = (r.left - MARGEN) + 'px';
    nodos.foco.style.width = (r.width + MARGEN * 2) + 'px';
    nodos.foco.style.height = (r.height + MARGEN * 2) + 'px';

    var anchoGlobo = Math.min(340, window.innerWidth - 32);
    nodos.globo.style.width = anchoGlobo + 'px';
    nodos.globo.className = 'tour-globo';

    // Medimos el globo ya con su contenido para decidir arriba o abajo
    var alto = nodos.globo.offsetHeight || 200;
    var abajo = r.bottom + MARGEN + SEPARACION;
    var arriba = r.top - MARGEN - SEPARACION - alto;
    var top, flecha;

    if (abajo + alto <= window.innerHeight - 12) {
      top = abajo; flecha = 'arriba';
    } else if (arriba >= 12) {
      top = arriba; flecha = 'abajo';
    } else {
      top = Math.max(12, (window.innerHeight - alto) / 2); flecha = '';
    }

    var left = r.left + r.width / 2 - anchoGlobo / 2;
    left = Math.max(16, Math.min(left, window.innerWidth - anchoGlobo - 16));

    nodos.globo.style.top = top + 'px';
    nodos.globo.style.left = left + 'px';
    if (flecha) nodos.globo.classList.add('tour-flecha-' + flecha);
  }

  function acercar(objetivo, listo) {
    if (!objetivo) { listo(); return; }
    var r = objetivo.getBoundingClientRect();
    var fuera = r.top < 90 || r.bottom > window.innerHeight - 90;
    if (!fuera) { listo(); return; }
    objetivo.scrollIntoView({ behavior: 'smooth', block: 'center' });
    setTimeout(listo, 380);   // esperamos a que termine el desplazamiento
  }

  // ============================================================
  //  PINTADO DEL PASO
  // ============================================================
  function pintar() {
    var paso = PASOS[indice];
    nodos.titulo.textContent = paso.titulo;
    nodos.texto.innerHTML = paso.texto;

    var puntos = '';
    for (var i = 0; i < PASOS.length; i++) {
      puntos += '<span class="tour-punto' + (i === indice ? ' activo' : '') + '"></span>';
    }
    nodos.puntos.innerHTML = puntos;

    nodos.atras.style.visibility = indice === 0 ? 'hidden' : 'visible';
    nodos.siguiente.textContent = indice === PASOS.length - 1 ? 'Entendido' : 'Siguiente';

    acercar(paso.selector ? el(paso.selector) : null, colocar);
  }

  function mover(paso) {
    var siguiente = indice + paso;
    // Saltamos los pasos cuyo elemento no esta disponible
    while (siguiente > 0 && siguiente < PASOS.length && !utilizable(PASOS[siguiente])) {
      siguiente += paso;
    }
    if (siguiente >= PASOS.length) { cerrar(); return; }
    if (siguiente < 0) siguiente = 0;
    indice = siguiente;
    pintar();
  }

  function alTeclado(e) {
    if (!abierto) return;
    if (e.key === 'Escape') cerrar();
    else if (e.key === 'ArrowRight') mover(1);
    else if (e.key === 'ArrowLeft') mover(-1);
  }

  var reposicionar = function() { if (abierto) colocar(); };

  // ============================================================
  //  ABRIR / CERRAR
  // ============================================================
  function abrir(desdeElInicio) {
    construir();
    indice = 0;
    abierto = true;
    if (desdeElInicio !== false && !utilizable(PASOS[0])) mover(1);
    nodos.raiz.classList.add('abierto');
    document.addEventListener('keydown', alTeclado);
    window.addEventListener('resize', reposicionar);
    window.addEventListener('scroll', reposicionar, true);
    pintar();
  }

  function cerrar() {
    if (!abierto) return;
    abierto = false;
    nodos.raiz.classList.remove('abierto');
    document.removeEventListener('keydown', alTeclado);
    window.removeEventListener('resize', reposicionar);
    window.removeEventListener('scroll', reposicionar, true);
    try { localStorage.setItem(CLAVE, 'visto'); } catch (e) {}
  }

  // Disponible para el boton "?" de la cabecera
  window.abrirGuiaAnalizador = function() { abrir(); };

  // ---- Arranque automatico la primera vez ----
  // El splash tarda ~1.85s en desaparecer: esperamos a que se vaya.
  function quizaAbrirSolo() {
    var visto = null;
    try { visto = localStorage.getItem(CLAVE); } catch (e) { return; }
    if (visto) return;
    var espera = document.getElementById('splash') ? 2100 : 400;
    setTimeout(function() { if (!abierto) abrir(); }, espera);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', quizaAbrirSolo);
  } else {
    quizaAbrirSolo();
  }
})();