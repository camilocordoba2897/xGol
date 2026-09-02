// ============================================================
//  GUIA PASO A PASO DEL ANALIZADOR
//
//  Un solo archivo con DOS recorridos independientes:
//
//    lista       -> pantalla "Elige un partido"
//    pronostico  -> pantalla del partido ya pronosticado
//
//  El recorrido que arranca lo decide la pantalla que tenga la
//  clase 'activa' en el momento de abrir. El boton "?" de la
//  cabecera sirve para las dos porque vive fuera de ambas.
//
//  NO toca el HTML, ni el CSS, ni analizador.js, auto.js o
//  vista.js: solo lee el DOM, resalta y explica.
//
//  Tres reglas que evitan los fallos de la version anterior:
//    1. Un objetivo de menos de 12px NO se resalta (asi nunca
//       vuelve a marcarse el <select> oculto de 1px).
//    2. Los pasos se arman al abrir, contando solo los que
//       existen de verdad: la numeracion nunca salta y los
//       puntitos siempre coinciden con los pasos reales.
//    3. Cada paso puede tener varios selectores de respaldo, y
//       las tarjetas del pronostico se buscan por su TITULO, no
//       por posicion, porque cuotas y enfrentamientos no siempre
//       aparecen.
// ============================================================
(function () {
  'use strict';

  if (window.XGOL_GUIA) return;   // por si el script se carga dos veces
  window.XGOL_GUIA = true;

  var CLAVES = {
    lista: 'xgol-guia-lista',
    pronostico: 'xgol-guia-pronostico'
  };

  var MARGEN = 8;        // aire entre el foco y el borde del elemento
  var SEPARACION = 14;   // distancia del globo al foco
  var MINIMO = 12;       // por debajo de esto el elemento no se resalta

  // ============================================================
  //  UTILIDADES DE BUSQUEDA
  // ============================================================
  function q(sel) {
    try { return document.querySelector(sel); } catch (e) { return null; }
  }

  function qq(sel) {
    try { return document.querySelectorAll(sel); } catch (e) { return []; }
  }

  // Un elemento sirve si existe y ocupa espacio de verdad en pantalla
  function sirve(n) {
    if (!n || !n.getBoundingClientRect) return false;
    var r = n.getBoundingClientRect();
    return r.width >= MINIMO && r.height >= MINIMO;
  }

  function normalizar(t) {
    var s = String(t == null ? '' : t).toLowerCase();
    try { s = s.normalize('NFD').replace(/[\u0300-\u036f]/g, ''); } catch (e) {}
    return s;
  }

  // Busca una tarjeta del pronostico por el texto de su titulo.
  // Es lo unico estable: el orden cambia segun haya cuotas o no.
  function tarjeta(titulo) {
    var buscado = normalizar(titulo);
    var cards = qq('#pronostico-contenido .pr-card');
    for (var i = 0; i < cards.length; i++) {
      var t = cards[i].querySelector('.pr-titulo');
      if (t && normalizar(t.textContent).indexOf(buscado) >= 0) return cards[i];
    }
    return null;
  }

  function porTitulo(titulo) {
    return function () { return tarjeta(titulo); };
  }

  // El contenedor de un elemento conocido, cuando la clase del
  // contenedor podria cambiar pero el id de dentro no.
  function padreDe(sel) {
    return function () {
      var n = q(sel);
      return n ? n.parentNode : null;
    };
  }

  // Resuelve el objetivo de un paso probando sus respaldos en orden
  function objetivo(paso) {
    if (!paso.donde) return null;
    var opciones = (typeof paso.donde === 'string' || typeof paso.donde === 'function')
      ? [paso.donde] : paso.donde;
    for (var i = 0; i < opciones.length; i++) {
      var n = null;
      if (typeof opciones[i] === 'function') {
        try { n = opciones[i](); } catch (e) { n = null; }
      } else {
        n = q(opciones[i]);
      }
      if (sirve(n)) return n;
    }
    return null;
  }

  // ============================================================
  //  RECORRIDO 1 — PANTALLA "ELIGE UN PARTIDO"
  // ============================================================
  var GUIA_LISTA = [
    {
      donde: null,
      titulo: 'Bienvenido a xGol',
      texto: 'Te explico en {n} pasos para qué sirve cada parte de esta pantalla. ' +
             'Dura menos de un minuto y puedes salir cuando quieras con la <strong>×</strong> ' +
             'o tocando fuera.'
    },
    {
      donde: ['.lab-ligas', 'nav[aria-label="Competencias"]', padreDe('.lab-liga')],
      titulo: 'Elige la competencia',
      texto: 'Cada ficha es una liga. Al tocarla se traen sus partidos al instante. ' +
             'El <strong>Brasileirão</strong> juega todo el año; las ligas europeas ' +
             'descansan de mayo a agosto y en esos meses aparecen vacías.'
    },
    {
      donde: ['#auto-fecha-btn', '.auto-fecha-btn'],
      titulo: 'Filtra por día',
      texto: 'Este botón abre el calendario: los días que tienen partido salen ' +
             'marcados. Al elegir uno, la lista se queda solo con los de ese día ' +
             'y el botón te recuerda cuál es. <strong>Borrar</strong> te devuelve ' +
             'todos los partidos de la liga.'
    },
    {
      donde: ['#lista-partidos', '.lista-partidos'],
      titulo: 'Los partidos',
      texto: 'Cada tarjeta es un encuentro. A la izquierda, la <strong>hora</strong> a la ' +
             'que empieza (o <strong>Fin</strong> con el día si ya terminó). En el centro, ' +
             'los dos equipos con su escudo; si ya se jugó, el marcador va a la derecha y ' +
             'el ganador queda resaltado.'
    },
    {
      donde: ['.fp-pronostico'],
      titulo: 'Calcula el pronóstico',
      texto: 'Los partidos que aún no se juegan traen este botón. Al tocarlo xGol descarga ' +
             'los últimos partidos de cada equipo y calcula todo. Tarda un par de segundos ' +
             'y te lleva solo a la pantalla del pronóstico.'
    },
    {
      donde: ['#session-banner'],
      titulo: 'Tu último análisis',
      texto: 'Cuando vuelves, aquí se recupera el último enfrentamiento que estabas viendo. ' +
             '<strong>Empezar de nuevo</strong> lo descarta y deja la pantalla limpia.'
    },
    {
      donde: ['#modo-manual', '.modo-manual'],
      titulo: 'Modo manual',
      texto: 'Para ligas o partidos que la API no cubre. Cargas un <strong>CSV</strong> por ' +
             'equipo con su historial y el pronóstico se calcula igual. Los equipos quedan ' +
             'guardados en la biblioteca para no volver a subirlos.'
    },
    {
      donde: ['.guia-btn', 'button[onclick*="abrirGuia"]'],
      titulo: 'Esta guía',
      texto: 'Este botón vuelve a abrirla cuando quieras. Y ojo: en la pantalla del ' +
             'pronóstico te explica <strong>otras cosas distintas</strong>, las de esa pantalla.'
    },
    {
      donde: ['.modo-btn', 'button[onclick*="alternarModo"]'],
      titulo: 'Modo claro u oscuro',
      texto: 'Alterna entre los dos temas. Tu elección se guarda para la próxima vez.'
    },
    {
      donde: null,
      titulo: 'Listo para empezar',
      texto: 'Elige una liga, toca <strong>Pronóstico</strong> en cualquier partido y ' +
             'listo.<br><br>Recuerda que las probabilidades son ' +
             '<strong>estimaciones estadísticas</strong>, no certezas: un 70% significa ' +
             'que se cumple unas 7 de cada 10 veces.'
    }
  ];

  // ============================================================
  //  RECORRIDO 2 — PANTALLA DEL PRONOSTICO
  // ============================================================
  var GUIA_PRONOSTICO = [
    {
      donde: null,
      titulo: 'Cómo leer el pronóstico',
      texto: 'Te explico en {n} pasos qué significa cada tarjeta de esta pantalla y ' +
             'de dónde sale cada número.'
    },
    {
      donde: ['.pr-header', '.match-header', '.pr-liga'],
      titulo: 'El partido',
      texto: 'Quién juega, con la <strong>hora en tu zona horaria</strong>, la fecha y el ' +
             'estado del encuentro. Arriba, la competencia y la jornada. El equipo de la ' +
             'izquierda es siempre el <strong>local</strong>.'
    },
    {
      donde: [porTitulo('quien ganara')],
      titulo: '¿Quién ganará?',
      texto: 'El resultado más probable en grande, y debajo el reparto completo: local, ' +
             'empate y visitante. La barra de colores muestra ese mismo reparto a escala, ' +
             'así ves de un vistazo si el partido está parejo o hay un favorito claro.'
    },
    {
      donde: [porTitulo('cuotas')],
      titulo: 'Cuotas reales',
      texto: 'La mejor cuota que paga cada resultado y en qué casa está. La etiqueta ' +
             '<strong>valor</strong> aparece cuando el modelo ve el resultado más probable ' +
             'de lo que paga la casa. Es información, no una recomendación de apuesta.'
    },
    {
      donde: [porTitulo('cuantos goles')],
      titulo: 'Goles del partido',
      texto: 'La línea de <strong>2.5 goles</strong>, que es la más usada: por encima ' +
             'significa 3 o más goles en total entre los dos equipos; por debajo, 2 o menos.'
    },
    {
      donde: [porTitulo('resultado mas probable')],
      titulo: 'Marcadores exactos',
      texto: 'El marcador con más probabilidad, y debajo los <strong>12 más probables</strong> ' +
             'ordenados. El color indica quién gana con ese resultado. Ninguno pasa de un ' +
             'porcentaje bajo: acertar el marcador exacto es lo más difícil que hay.'
    },
    {
      donde: [porTitulo('enfrentamientos')],
      titulo: 'Historial entre los dos',
      texto: 'Cuántas veces ganó cada uno cuando se han cruzado antes, con el detalle partido ' +
             'a partido. Sale del historial largo del local, así que a veces son pocos ' +
             'encuentros: tómalo como contexto, no como dato decisivo.'
    },
    {
      donde: ['.pr-forma', '#forma-team1'],
      titulo: 'Forma reciente',
      texto: 'Los últimos resultados de cada equipo. Las pestañas <strong>Casa</strong> y ' +
             '<strong>Fuera</strong> filtran solo esos partidos, que es donde suelen verse ' +
             'las diferencias grandes entre un equipo y otro.'
    },
    {
      donde: ['.pr-ajustes'],
      titulo: 'Ajustes del partido',
      texto: 'Ábrelo si hay algo que el historial no sabe. <strong>Cancha neutral</strong> ' +
             'quita la ventaja de local (útil en finales), y dentro puedes marcar bajas o ' +
             'contexto. Todo se <strong>recalcula al instante</strong>.'
    },
    {
      donde: ['.pr-modelo'],
      titulo: 'De dónde salen los números',
      texto: 'Los <strong>goles esperados</strong> de cada equipo y con cuántos partidos se ' +
             'calcularon. El modelo es Poisson con corrección Dixon-Coles: más partidos en ' +
             'el historial, resultado más fiable.'
    },
    {
      donde: ['.pr-volver'],
      titulo: 'Volver atrás',
      texto: 'Te devuelve a la lista sin perder nada: la liga y la fecha que tenías siguen ' +
             'puestas.'
    },
    {
      donde: null,
      titulo: 'Eso es todo',
      texto: 'Un último recordatorio: esto son <strong>probabilidades</strong>, no ' +
             'predicciones seguras. Ningún modelo acierta siempre. Apuesta responsablemente.'
    }
  ];

  // ============================================================
  //  ESTADO
  // ============================================================
  var pasos = [];        // pasos ya filtrados y numerados de la apertura actual
  var indice = 0;
  var abierto = false;
  var pantalla = 'lista';
  var nodos = {};
  var vigia = null;      // intervalo que reajusta el foco mientras esta abierto

  function pantallaActual() {
    var p = document.getElementById('pantalla-pronostico');
    if (p && p.classList.contains('activa')) return 'pronostico';
    return 'lista';
  }

  // Arma la lista real de pasos: solo los que tienen elemento visible,
  // ya numerados. Asi nunca hay saltos ni puntitos de mas.
  function prepararPasos(cual) {
    var origen = cual === 'pronostico' ? GUIA_PRONOSTICO : GUIA_LISTA;
    var utiles = [];
    var i;

    for (i = 0; i < origen.length; i++) {
      if (!origen[i].donde) { utiles.push(origen[i]); continue; }
      if (objetivo(origen[i])) utiles.push(origen[i]);
    }

    var total = 0;
    for (i = 0; i < utiles.length; i++) if (utiles[i].donde) total++;

    var numero = 0;
    var listos = [];
    for (i = 0; i < utiles.length; i++) {
      var p = utiles[i];
      var rotulo = p.titulo;
      if (p.donde) { numero++; rotulo = numero + ' · ' + p.titulo; }
      listos.push({
        donde: p.donde,
        titulo: rotulo,
        texto: String(p.texto).replace('{n}', total)
      });
    }
    return listos;
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
    // El velo son CUATRO paneles (arriba, abajo, izquierda, derecha) en
    // vez de uno solo que cubra la pantalla entera. Asi el hueco del
    // elemento resaltado queda de verdad sin tapar: antes el velo unico
    // llevaba un blur que tambien difuminaba lo que se estaba senalando.
    raiz.innerHTML =
      '<div class="tour-velo tour-velo-arriba"></div>' +
      '<div class="tour-velo tour-velo-abajo"></div>' +
      '<div class="tour-velo tour-velo-izq"></div>' +
      '<div class="tour-velo tour-velo-der"></div>' +
      '<div class="tour-foco"></div>' +
      '<div class="tour-globo">' +
        '<button class="tour-cerrar" type="button" aria-label="Cerrar guía">&times;</button>' +
        '<div class="tour-titulo"></div>' +
        '<div class="tour-texto"></div>' +
        '<div class="tour-pie">' +
          '<div class="tour-puntos"></div>' +
          '<div class="tour-botones">' +
            '<button class="tour-atras" type="button">Atrás</button>' +
            '<button class="tour-siguiente" type="button">Siguiente</button>' +
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

    raiz.querySelector('.tour-cerrar').addEventListener('click', function () { cerrar(); });
    // Tocar fuera cierra la guia: ahora "fuera" son los cuatro paneles
    for (var v = 0; v < nodos.velos.length; v++) {
      nodos.velos[v].addEventListener('click', function () { cerrar(); });
    }
    nodos.atras.addEventListener('click', function () { mover(-1); });
    nodos.siguiente.addEventListener('click', function () { mover(1); });
  }

  // ============================================================
  //  POSICIONAMIENTO
  // ============================================================
  // Coloca un panel del velo. Si queda sin tamano se esconde, para que
  // no capture clicks en una franja invisible de 0px.
  function panel(nodo, x, y, ancho, alto) {
    if (ancho <= 0 || alto <= 0) { nodo.style.display = 'none'; return; }
    nodo.style.display = 'block';
    nodo.style.left = x + 'px';
    nodo.style.top = y + 'px';
    nodo.style.width = ancho + 'px';
    nodo.style.height = alto + 'px';
  }

  // Deja un hueco limpio (sin velo y sin blur) sobre el elemento resaltado
  // y tapa todo lo de alrededor con los otros tres paneles.
  function taparAlrededor(x, y, ancho, alto) {
    var W = window.innerWidth, H = window.innerHeight;
    panel(nodos.velos[0], 0, 0, W, y);                       // arriba
    panel(nodos.velos[1], 0, y + alto, W, H - (y + alto));   // abajo
    panel(nodos.velos[2], 0, y, x, alto);                    // izquierda
    panel(nodos.velos[3], x + ancho, y, W - (x + ancho), alto); // derecha
  }

  // Pasos sin elemento resaltado: la pantalla se tapa entera
  function taparTodo() {
    panel(nodos.velos[0], 0, 0, window.innerWidth, window.innerHeight);
    panel(nodos.velos[1], 0, 0, 0, 0);
    panel(nodos.velos[2], 0, 0, 0, 0);
    panel(nodos.velos[3], 0, 0, 0, 0);
  }

  function centrarGlobo() {
    nodos.foco.style.display = 'none';
    taparTodo();
    nodos.globo.className = 'tour-globo tour-centrado';
    nodos.globo.style.top = '';
    nodos.globo.style.left = '';
    nodos.globo.style.width = '';
  }

  function colocar() {
    if (!abierto || !pasos.length) return;
    var paso = pasos[indice];
    // Se resuelve otra vez cada vez: si la tarjeta se repinto (por
    // ejemplo al llegar las cuotas), el foco sigue al elemento nuevo.
    var destino = objetivo(paso);

    if (!destino) { centrarGlobo(); return; }

    var r = destino.getBoundingClientRect();

    // El foco nunca se sale de la pantalla, aunque la tarjeta sea
    // mas alta que la ventana (marcadores, forma reciente...).
    var arribaFoco = r.top - MARGEN;
    var altoFoco = r.height + MARGEN * 2;
    if (arribaFoco < 8) { altoFoco += arribaFoco - 8; arribaFoco = 8; }
    if (arribaFoco + altoFoco > window.innerHeight - 8) {
      altoFoco = window.innerHeight - 8 - arribaFoco;
    }
    if (altoFoco < 24) altoFoco = 24;

    var izqFoco = r.left - MARGEN;
    var anchoFoco = r.width + MARGEN * 2;

    nodos.foco.style.display = 'block';
    nodos.foco.style.top = arribaFoco + 'px';
    nodos.foco.style.left = izqFoco + 'px';
    nodos.foco.style.width = anchoFoco + 'px';
    nodos.foco.style.height = altoFoco + 'px';

    // Los cuatro paneles rodean el hueco: lo de dentro se ve nitido
    taparAlrededor(izqFoco, arribaFoco, anchoFoco, altoFoco);

    var ancho = Math.min(340, window.innerWidth - 32);
    nodos.globo.style.width = ancho + 'px';
    nodos.globo.className = 'tour-globo';

    // Medimos el globo ya con su contenido para decidir arriba o abajo
    var alto = nodos.globo.offsetHeight || 200;
    var abajo = arribaFoco + altoFoco + SEPARACION;
    var arriba = arribaFoco - SEPARACION - alto;
    var top, flecha;

    if (abajo + alto <= window.innerHeight - 12) {
      top = abajo; flecha = 'arriba';
    } else if (arriba >= 12) {
      top = arriba; flecha = 'abajo';
    } else {
      top = Math.max(12, (window.innerHeight - alto) / 2); flecha = '';
    }

    var left = r.left + r.width / 2 - ancho / 2;
    left = Math.max(16, Math.min(left, window.innerWidth - ancho - 16));

    nodos.globo.style.top = top + 'px';
    nodos.globo.style.left = left + 'px';
    if (flecha) nodos.globo.classList.add('tour-flecha-' + flecha);
  }

  // Acerca el elemento y espera a que el desplazamiento termine de verdad
  function acercar(destino, listo) {
    if (!destino) { listo(); return; }

    var r = destino.getBoundingClientRect();
    var altoLibre = window.innerHeight;
    var fuera = r.top < 90 || r.bottom > altoLibre - 90;
    if (!fuera) { listo(); return; }

    var bloque = (r.height > altoLibre - 180) ? 'start' : 'center';
    try {
      destino.scrollIntoView({ behavior: 'smooth', block: bloque });
    } catch (e) {
      try { destino.scrollIntoView(); } catch (e2) {}
    }

    // En vez de un tiempo fijo, esperamos a que el scroll se quede quieto
    var ultimo = -1, intentos = 0;
    var reloj = setInterval(function () {
      var y = window.pageYOffset || document.documentElement.scrollTop || 0;
      intentos++;
      if (y === ultimo || intentos > 14) {   // ~840ms como maximo
        clearInterval(reloj);
        listo();
        return;
      }
      ultimo = y;
    }, 60);
  }

  // ============================================================
  //  PINTADO DEL PASO
  // ============================================================
  function pintar() {
    if (!pasos.length) return;
    var paso = pasos[indice];

    nodos.titulo.textContent = paso.titulo;
    nodos.texto.innerHTML = paso.texto;

    var puntos = '';
    for (var i = 0; i < pasos.length; i++) {
      puntos += '<span class="tour-punto' + (i === indice ? ' activo' : '') + '"></span>';
    }
    nodos.puntos.innerHTML = puntos;

    nodos.atras.style.visibility = indice === 0 ? 'hidden' : 'visible';
    nodos.siguiente.textContent = indice === pasos.length - 1 ? 'Entendido' : 'Siguiente';

    // Mientras se acerca el elemento, el globo va centrado: nunca se
    // queda apuntando a una posicion vieja.
    centrarGlobo();
    acercar(objetivo(paso), colocar);
  }

  function mover(salto) {
    var siguiente = indice + salto;
    if (siguiente >= pasos.length) { cerrar(); return; }
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

  var reajustar = function () { if (abierto) colocar(); };

  // ============================================================
  //  ABRIR / CERRAR
  // ============================================================
  function abrir(cual) {
    if (abierto) return;

    pantalla = cual || pantallaActual();
    pasos = prepararPasos(pantalla);

    // Red de seguridad: si por lo que sea no hubiera ni un paso,
    // mostramos un mensaje en vez de un recuadro vacio.
    if (!pasos.length) {
      pasos = [{
        donde: null,
        titulo: 'Guía no disponible',
        texto: 'Esta pantalla todavía se está cargando. Vuelve a tocar el botón ' +
               '<strong>?</strong> en un momento.'
      }];
    }

    construir();
    indice = 0;
    abierto = true;
    nodos.raiz.classList.add('abierto');

    document.addEventListener('keydown', alTeclado);
    window.addEventListener('resize', reajustar);
    window.addEventListener('scroll', reajustar, true);

    // Si el contenido de debajo se repinta (llegan las cuotas, cambias
    // una pestaña de forma), el foco se reajusta solo.
    vigia = setInterval(reajustar, 500);

    pintar();
  }

  function cerrar(sinMarcar) {
    if (!abierto) return;
    abierto = false;
    nodos.raiz.classList.remove('abierto');

    document.removeEventListener('keydown', alTeclado);
    window.removeEventListener('resize', reajustar);
    window.removeEventListener('scroll', reajustar, true);
    if (vigia) { clearInterval(vigia); vigia = null; }

    if (sinMarcar !== true) {
      try { localStorage.setItem(CLAVES[pantalla] || CLAVES.lista, 'visto'); } catch (e) {}
    }
  }

  // ============================================================
  //  API PUBLICA
  // ============================================================
  // La usa el boton "?" de la cabecera, que sirve para las dos pantallas
  window.abrirGuiaAnalizador = function (cual) {
    abrir(cual === 'lista' || cual === 'pronostico' ? cual : pantallaActual());
  };

  // Util para probar: borra el "ya la vio" de las dos guias
  window.reiniciarGuias = function () {
    try {
      localStorage.removeItem(CLAVES.lista);
      localStorage.removeItem(CLAVES.pronostico);
      localStorage.removeItem('xgol-tour-analizador');   // clave de la version vieja
    } catch (e) {}
  };

  // ============================================================
  //  APERTURA AUTOMATICA LA PRIMERA VEZ
  //  Una vez por pantalla y solo la primera vez de cada una.
  // ============================================================
  function yaVista(cual) {
    try { return !!localStorage.getItem(CLAVES[cual]); } catch (e) { return true; }
  }

  function quizaAbrirSolo(cual, espera) {
    if (yaVista(cual)) return;
    setTimeout(function () {
      if (abierto) return;
      if (pantallaActual() !== cual) return;   // cambio de pantalla mientras esperaba
      abrir(cual);
    }, espera);
  }

  // La pantalla del pronostico no existe al cargar: se activa despues.
  // Vigilamos su clase para abrir su guia la primera vez que aparezca,
  // sin tocar auto.js.
  function vigilarPantallas() {
    var p = document.getElementById('pantalla-pronostico');
    if (!p || typeof MutationObserver !== 'function') return;

    var estaba = p.classList.contains('activa');
    var observador = new MutationObserver(function () {
      var ahora = p.classList.contains('activa');
      if (ahora === estaba) return;
      estaba = ahora;

      // Al cambiar de pantalla la guia abierta ya no vale: se cierra
      // sin marcarla como vista, para que se pueda volver a ver.
      if (abierto) cerrar(true);

      if (ahora) quizaAbrirSolo('pronostico', 900);
    });
    observador.observe(p, { attributes: true, attributeFilter: ['class'] });
  }

  function iniciar() {
    vigilarPantallas();
    // El splash tarda ~1.85s en irse: esperamos a que desaparezca.
    var espera = document.getElementById('splash') ? 2100 : 400;
    quizaAbrirSolo('lista', espera);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', iniciar);
  } else {
    iniciar();
  }
})();