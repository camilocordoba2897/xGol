// ============================================================
//  BOTON SUBIR — flecha flotante para volver arriba
//
//  Aparece en la esquina inferior derecha cuando llevas un rato
//  bajando y desaparece al llegar arriba. Un clic sube del todo.
//
//  Sirve en las DOS pantallas sin hacer nada especial: el boton
//  cuelga del <body>, no de una pantalla concreta, y las dos
//  usan el scroll de la ventana.
//
//  Archivo independiente: NO toca analizador.js, auto.js,
//  vista.js ni tour.js. Su aspecto vive en analisis.css.
// ============================================================
(function () {
  'use strict';

  if (window.XGOL_SUBIR) return;   // por si el script se carga dos veces
  window.XGOL_SUBIR = true;

  var UMBRAL = 300;      // px que hay que bajar para que aparezca
  var boton = null;
  var seVe = false;
  var pedido = false;    // evita recalcular en cada pixel de scroll

  function desplazamiento() {
    return window.pageYOffset ||
           document.documentElement.scrollTop ||
           document.body.scrollTop || 0;
  }

  function sinAnimacion() {
    try {
      return window.matchMedia &&
             window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    } catch (e) { return false; }
  }

  function crear() {
    boton = document.createElement('button');
    boton.className = 'subir-btn';
    boton.type = 'button';
    boton.title = 'Volver arriba';
    boton.setAttribute('aria-label', 'Volver arriba');
    boton.innerHTML =
      '<svg viewBox="0 0 24 24" aria-hidden="true">' +
        '<line x1="12" y1="19.5" x2="12" y2="5"/>' +
        '<polyline points="5.5 11.5 12 5 18.5 11.5"/>' +
      '</svg>';

    boton.addEventListener('click', function () {
      try {
        window.scrollTo({ top: 0, behavior: sinAnimacion() ? 'auto' : 'smooth' });
      } catch (e) {
        window.scrollTo(0, 0);   // navegadores viejos sin opciones
      }
    });

    document.body.appendChild(boton);
  }

  // Solo toca el DOM cuando el estado cambia de verdad
  function actualizar() {
    pedido = false;
    if (!boton) return;
    var debeVerse = desplazamiento() > UMBRAL;
    if (debeVerse === seVe) return;
    seVe = debeVerse;
    boton.classList.toggle('se-ve', seVe);
  }

  function alDesplazar() {
    if (pedido) return;
    pedido = true;
    if (window.requestAnimationFrame) window.requestAnimationFrame(actualizar);
    else setTimeout(actualizar, 80);
  }

  function iniciar() {
    if (!document.body) return;
    crear();
    window.addEventListener('scroll', alDesplazar, { passive: true });
    window.addEventListener('resize', alDesplazar);
    actualizar();   // por si la pagina abre ya desplazada
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', iniciar);
  } else {
    iniciar();
  }
})();