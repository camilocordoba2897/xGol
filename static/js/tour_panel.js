// ============================================================
//  TOUR GUIADO DEL PANEL DE ADMINISTRACION
//
//  Misma mecanica que tour.js del analizador: foco sobre el
//  elemento real y globo con el mensaje al lado, paso a paso.
//
//  La diferencia es que el panel trabaja por pestanas, asi que
//  cada paso declara en que vista vive y el tour la abre solo
//  antes de resaltar. Un paso cuyo elemento no exista se salta
//  sin romper el recorrido.
// ============================================================
(function() {
  var CLAVE = 'xgol-tour-panel';
  var MARGEN = 8;        // aire entre el foco y el borde del elemento
  var SEPARACION = 14;   // distancia del globo al foco

  // ---- Pasos. selector null = mensaje centrado, sin foco ----
  var PASOS = [
    {
      vista: 'resumen', selector: null,
      titulo: 'Bienvenido al panel',
      texto: 'Te muestro en 10 pasos qué hace cada parte. Dura menos de un minuto y puedes salir cuando quieras.'
    },
    {
      vista: 'resumen', selector: '.rail',
      titulo: '1 · El menú lateral',
      texto: 'Cinco vistas <strong>independientes</strong>: Resumen, Modelo, Dinero, Usuarios y Accesos. Cada una muestra solo lo suyo. Abajo del todo están volver al sitio y cerrar sesión.'
    },
    {
      vista: 'resumen', selector: '.kpis',
      titulo: '2 · Las cuatro cifras',
      texto: 'El estado del negocio hoy. La etiqueta verde o roja compara contra el periodo anterior: verde subió, rojo bajó.'
    },
    {
      vista: 'resumen', selector: '.apilada',
      titulo: '3 · Estado de la base',
      texto: 'Reparte a todos los registrados en tres grupos. El bloque del medio (<strong>registrados sin pagar</strong>) es tu venta pendiente.'
    },
    {
      vista: 'modelo', selector: '.regla',
      titulo: '4 · Dónde cae el modelo',
      texto: 'La marca blanca es tu acierto real. Rojo = por debajo de acertar siempre al local. Azul = rango normal. Verde = sobre el mejor 1X2 documentado. Ámbar = revisar la muestra.'
    },
    {
      vista: 'modelo', selector: '.cal-fila',
      titulo: '5 · Calibración',
      texto: 'Si el modelo dijo 70%, debería acertar 7 de cada 10. La barra gris es lo que prometió y la verde lo que pasó. <strong>Optimista</strong> promete de más, <strong>Conservador</strong> se queda corto.'
    },
    {
      vista: 'modelo', selector: '.dos-columnas > .panel:last-child',
      titulo: '6 · Mercados y ROI',
      texto: 'Qué tipo de apuesta deja plata. Ojo: un mercado puede acertar mucho y aun así <strong>perder dinero</strong> si la cuota es baja. Por eso manda el ROI, no el porcentaje.'
    },
    {
      vista: 'dinero', selector: '.kpis-6',
      titulo: '7 · Ingresos por periodo',
      texto: 'Hoy, semana, mes, trimestre, año e histórico. Solo cuenta <strong>pagos aprobados</strong>: un pendiente o rechazado no es una venta.'
    },
    {
      vista: 'dinero', selector: '.filtros',
      titulo: '8 · Historial y exportación',
      texto: 'Filtra por estado, plan o fecha y busca por referencia, factura o usuario. Con <strong>CSV</strong> o <strong>Excel</strong> te llevas exactamente lo que estás viendo filtrado.'
    },
    {
      vista: 'usuarios', selector: '#buscarUsuario',
      titulo: '9 · Buscar y administrar',
      texto: 'Busca por nombre o correo. En cada fila puedes activar o cancelar la suscripción, editar, bloquear o eliminar la cuenta.'
    },
    {
      vista: 'resumen', selector: '.icono-btn',
      titulo: '10 · Guía y tema',
      texto: 'El botón <strong>?</strong> vuelve a abrir esta guía cuando quieras. El de al lado alterna entre modo claro y oscuro, y recuerda tu elección.'
    },
    {
      vista: 'resumen', selector: null,
      titulo: 'Listo',
      texto: 'Un recordatorio: las probabilidades son <strong>estimaciones estadísticas</strong>, no certezas. Y en apuestas, el ROI importa más que el porcentaje de acierto.'
    }
  ];

  var indice = 0;
  var abierto = false;
  var nodos = {};

  function el(sel) { try { return document.querySelector(sel); } catch (e) { return null; } }

  // Cambia de pestana si el paso vive en otra
  function abrirVistaDelPaso(paso) {
    if (!paso.vista) return false;
    var seccion = document.getElementById('v-' + paso.vista);
    if (!seccion || seccion.classList.contains('activa')) return false;
    if (typeof window.abrirVista === 'function') { window.abrirVista(paso.vista); return true; }
    return false;
  }

  // Un elemento sirve si existe y ocupa espacio en pantalla
  function utilizable(paso) {
    if (!paso.selector) return true;
    abrirVistaDelPaso(paso);
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
    // El velo son CUATRO paneles (arriba, abajo, izquierda, derecha) en vez
    // de uno solo que cubra la pantalla. Antes era un panel con inset:0 y su
    // blur difuminaba TAMBIEN lo que se estaba senalando; asi el hueco del
    // medio queda libre de verdad y lo resaltado se ve nitido.
    raiz.innerHTML =
      '<div class="tour-velo tour-velo-arriba"></div>' +
      '<div class="tour-velo tour-velo-abajo"></div>' +
      '<div class="tour-velo tour-velo-izq"></div>' +
      '<div class="tour-velo tour-velo-der"></div>' +
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
    nodos.velos = [
      raiz.querySelector('.tour-velo-arriba'),
      raiz.querySelector('.tour-velo-abajo'),
      raiz.querySelector('.tour-velo-izq'),
      raiz.querySelector('.tour-velo-der')
    ];
    nodos.foco = raiz.querySelector('.tour-foco');
    nodos.globo = raiz.querySelector('.tour-globo');
    nodos.titulo = raiz.querySelector('.tour-titulo');
    nodos.texto = raiz.querySelector('.tour-texto');
    nodos.puntos = raiz.querySelector('.tour-puntos');
    nodos.atras = raiz.querySelector('.tour-atras');
    nodos.siguiente = raiz.querySelector('.tour-siguiente');

    raiz.querySelector('.tour-cerrar').addEventListener('click', cerrar);
    // Tocar fuera cierra la guia: ahora "fuera" son los cuatro paneles
    for (var v = 0; v < nodos.velos.length; v++) {
      nodos.velos[v].addEventListener('click', cerrar);
    }
    nodos.atras.addEventListener('click', function() { mover(-1); });
    nodos.siguiente.addEventListener('click', function() { mover(1); });
  }

  // ============================================================
  //  POSICIONAMIENTO
  // ============================================================
  // ---- Velo en cuatro paneles ----
  // Coloca un panel. Si queda sin tamano se esconde, para que no capture
  // clicks en una franja invisible de 0px.
  function panel(nodo, x, y, ancho, alto) {
    if (ancho <= 0 || alto <= 0) { nodo.style.display = 'none'; return; }
    nodo.style.display = 'block';
    nodo.style.left = x + 'px';
    nodo.style.top = y + 'px';
    nodo.style.width = ancho + 'px';
    nodo.style.height = alto + 'px';
  }

  // Ancho y alto REALES del area visible. Se usa clientWidth y no
  // innerWidth porque innerWidth incluye la barra de scroll, y por esos
  // pixeles de mas el globo terminaba asomandose fuera de la pantalla.
  function anchoVisible() {
    return document.documentElement.clientWidth || window.innerWidth;
  }
  function altoVisible() {
    return document.documentElement.clientHeight || window.innerHeight;
  }

  // Deja un hueco limpio (sin velo ni blur) sobre lo resaltado y tapa
  // todo lo de alrededor con los otros tres paneles.
  function taparAlrededor(x, y, ancho, alto) {
    var W = anchoVisible(), H = altoVisible();
    panel(nodos.velos[0], 0, 0, W, y);                          // arriba
    panel(nodos.velos[1], 0, y + alto, W, H - (y + alto));      // abajo
    panel(nodos.velos[2], 0, y, x, alto);                       // izquierda
    panel(nodos.velos[3], x + ancho, y, W - (x + ancho), alto); // derecha
  }

  // Pasos sin elemento resaltado: se tapa la pantalla entera
  function taparTodo() {
    panel(nodos.velos[0], 0, 0, anchoVisible(), altoVisible());
    panel(nodos.velos[1], 0, 0, 0, 0);
    panel(nodos.velos[2], 0, 0, 0, 0);
    panel(nodos.velos[3], 0, 0, 0, 0);
  }

  function colocar() {
    var paso = PASOS[indice];
    var objetivo = paso.selector ? el(paso.selector) : null;
    var W = anchoVisible(), H = altoVisible();

    if (!objetivo) {
      nodos.foco.style.display = 'none';
      taparTodo();
      nodos.globo.className = 'tour-globo tour-centrado';
      nodos.globo.style.top = '';
      nodos.globo.style.left = '';
      nodos.globo.style.width = '';
      return;
    }

    var r = objetivo.getBoundingClientRect();

    // El foco se recorta contra los bordes de la pantalla. Sin esto, un
    // elemento pegado al borde (el menu lateral empieza en x=0) queda con
    // el foco en -8px por el margen: su marco verde sale cortado y el
    // panel de ese lado se queda con un tamano negativo.
    var izqFoco = Math.max(0, r.left - MARGEN);
    var arribaFoco = Math.max(0, r.top - MARGEN);
    var derFoco = Math.min(W, r.right + MARGEN);
    var abajoFoco = Math.min(H, r.bottom + MARGEN);
    var anchoFoco = Math.max(0, derFoco - izqFoco);
    var altoFoco = Math.max(0, abajoFoco - arribaFoco);

    nodos.foco.style.display = 'block';
    nodos.foco.style.top = arribaFoco + 'px';
    nodos.foco.style.left = izqFoco + 'px';
    nodos.foco.style.width = anchoFoco + 'px';
    nodos.foco.style.height = altoFoco + 'px';

    // Los cuatro paneles rodean el hueco: lo de dentro se ve nitido
    taparAlrededor(izqFoco, arribaFoco, anchoFoco, altoFoco);

    var anchoGlobo = Math.min(340, W - 32);
    nodos.globo.style.width = anchoGlobo + 'px';
    nodos.globo.className = 'tour-globo';

    // Medimos el globo ya con su contenido para decidir arriba o abajo
    var alto = nodos.globo.offsetHeight || 200;
    var abajo = r.bottom + MARGEN + SEPARACION;
    var arriba = r.top - MARGEN - SEPARACION - alto;
    var top, flecha;

    if (abajo + alto <= H - 12) {
      top = abajo; flecha = 'arriba';
    } else if (arriba >= 12) {
      top = arriba; flecha = 'abajo';
    } else {
      top = Math.max(12, (H - alto) / 2); flecha = '';
    }

    // Se mide el ancho REAL que ocupo el globo. Si su contenido lo estiro
    // (por ejemplo con muchos pasos, la fila de puntitos empuja al boton
    // Siguiente), hay que encajarlo con ese ancho y no con el pedido, o el
    // boton queda cortado contra el borde de la pantalla.
    var anchoReal = Math.max(anchoGlobo, nodos.globo.offsetWidth || anchoGlobo);
    var left = r.left + r.width / 2 - anchoReal / 2;
    left = Math.max(16, Math.min(left, W - anchoReal - 16));

    nodos.globo.style.top = top + 'px';
    nodos.globo.style.left = left + 'px';
    if (flecha) nodos.globo.classList.add('tour-flecha-' + flecha);
  }

  function acercar(objetivo, listo) {
    if (!objetivo) { listo(); return; }
    var r = objetivo.getBoundingClientRect();
    var fuera = r.top < 100 || r.bottom > window.innerHeight - 90;
    if (!fuera) { listo(); return; }
    objetivo.scrollIntoView({ behavior: 'smooth', block: 'center' });
    setTimeout(listo, 380);   // esperamos a que termine el desplazamiento
  }

  // ============================================================
  //  PINTADO DEL PASO
  // ============================================================
  function pintar() {
    var paso = PASOS[indice];
    var cambio = abrirVistaDelPaso(paso);

    nodos.titulo.textContent = paso.titulo;
    nodos.texto.innerHTML = paso.texto;

    var puntos = '';
    for (var i = 0; i < PASOS.length; i++) {
      puntos += '<span class="tour-punto' + (i === indice ? ' activo' : '') + '"></span>';
    }
    nodos.puntos.innerHTML = puntos;

    nodos.atras.style.visibility = indice === 0 ? 'hidden' : 'visible';
    nodos.siguiente.textContent = indice === PASOS.length - 1 ? 'Entendido' : 'Siguiente';

    // Si acabamos de cambiar de pestana, esperamos a que se pinte
    setTimeout(function() {
      acercar(paso.selector ? el(paso.selector) : null, colocar);
    }, cambio ? 240 : 0);
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
  function abrir() {
    construir();
    indice = 0;
    abierto = true;
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
  window.abrirGuia = function() { abrir(); };

  // ---- Arranque automatico la primera vez ----
  function quizaAbrirSolo() {
    var visto = null;
    try { visto = localStorage.getItem(CLAVE); } catch (e) { return; }
    if (visto) return;
    setTimeout(function() { if (!abierto) abrir(); }, 600);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', quizaAbrirSolo);
  } else {
    quizaAbrirSolo();
  }
})();