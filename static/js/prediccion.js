// ============================================================
//  PREDICCION DESTACADA DEL HOME
//  Llena la tarjeta del hero con partidos y probabilidades REALES
//  que calcula el backend (inicio/api_partidos.py) y las va rotando.
//  La URL llega en el atributo data-url de la tarjeta.
//
//  IMPORTANTE: este script NO toca la tarjeta (#predCard). No le
//  cambia opacidad ni transform, para no interferir con la
//  animacion card-float del CSS. Solo reemplaza el contenido de
//  adentro: nombres, escudos, porcentajes, marcador y confianza.
//  La barra se desliza sola con una transicion de ancho.
//
//  Si no hay datos, la tarjeta se queda tal cual esta en el HTML.
// ============================================================
(function() {
  var card = document.getElementById('predCard');
  if (!card) return;

  var URL_PRED = card.getAttribute('data-url');
  if (!URL_PRED) return;

  var SEGUNDOS_ROTACION = 6;   // cada cuanto cambia de partido
  var VELOCIDAD_BARRA = '.55s'; // que tan suave se desliza la barra

  var lista = [];
  var indice = 0;

  function texto(id, valor) {
    var el = document.getElementById(id);
    if (el) el.textContent = valor;
  }

  function pintar(p) {
    var logoLocal = document.getElementById('pcLocalLogo');
    var logoVisit = document.getElementById('pcVisitLogo');
    if (logoLocal && p.local_escudo) { logoLocal.src = p.local_escudo; logoLocal.alt = p.local; }
    if (logoVisit && p.visitante_escudo) { logoVisit.src = p.visitante_escudo; logoVisit.alt = p.visitante; }

    texto('pcLocalNom', p.local);
    texto('pcVisitNom', p.visitante);
    texto('pcLocalRow', p.local);
    texto('pcVisitRow', p.visitante);
    texto('pcLocalPct', p.prob_local + '%');
    texto('pcVisitPct', p.prob_visitante + '%');
    texto('pcMarcador', p.marcador);
    texto('pcConfianza', p.confianza + '%');

    //La barra nunca desaparece: solo se desliza al nuevo ancho
    var barra1 = document.getElementById('pcBar1');
    var barra2 = document.getElementById('pcBar2');
    if (barra1) barra1.style.width = p.prob_local + '%';
    if (barra2) barra2.style.width = p.prob_visitante + '%';
  }

  function rotar() {
    pintar(lista[indice % lista.length]);
    indice++;
  }

  fetch(URL_PRED, { headers: { 'X-Requested-With': 'fetch' } })
    .then(function(r) { return r.json(); })
    .then(function(d) {
      lista = d.predicciones || [];
      if (!lista.length) return;   // sin datos reales: la tarjeta se queda como esta

      //Transicion solo en el ancho de la barra (la tarjeta no se toca)
      var barra1 = document.getElementById('pcBar1');
      var barra2 = document.getElementById('pcBar2');
      if (barra1) barra1.style.transition = 'width ' + VELOCIDAD_BARRA + ' ease';
      if (barra2) barra2.style.transition = 'width ' + VELOCIDAD_BARRA + ' ease';

      pintar(lista[0]);
      indice = 1;
      if (lista.length > 1) setInterval(rotar, SEGUNDOS_ROTACION * 1000);
    })
    .catch(function() { /* sin conexion: la tarjeta se queda como esta */ });
})();