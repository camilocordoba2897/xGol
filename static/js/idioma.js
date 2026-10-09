// ============================================================
//  SELECTOR DE IDIOMA (solo en el home)
//
//  La persona elige el idioma UNA vez aqui y cambia TODO el sitio: este
//  archivo guarda la eleccion en la cookie de idioma de Django y recarga la
//  pagina, que ya llega traducida desde el servidor (xgol/idioma.py). Las
//  traducciones estan en locale/ y se actualizan con
//  "python manage.py textos".
//
//  En computador es la capsula con la bandera de la barra; en tablet y
//  celular son los botones con bandera del menu ☰.
// ============================================================
(function() {
  var caja = document.getElementById('idioma');
  if (!caja) return;
  var boton = document.getElementById('idiomaBtn');
  var menu = document.getElementById('idiomaMenu');
  var COOKIE = caja.getAttribute('data-cookie') || 'django_language';
  var actual = caja.getAttribute('data-actual') || 'es';

  function elegir(codigo) {
    if (!codigo || codigo === actual) { cerrar(true); return; }
    var seguro = location.protocol === 'https:' ? '; Secure' : '';
    document.cookie = COOKIE + '=' + codigo + '; path=/; max-age=31536000; SameSite=Lax' + seguro;
    location.reload();
  }

  function abrir() {
    caja.classList.add('open');
    boton.setAttribute('aria-expanded', 'true');
    var sel = menu.querySelector('.sel') || menu.querySelector('[data-idioma]');
    if (sel) sel.focus({ preventScroll: true });
  }
  function cerrar(devolverFoco) {
    if (!caja.classList.contains('open')) return;
    caja.classList.remove('open');
    boton.setAttribute('aria-expanded', 'false');
    if (devolverFoco) boton.focus({ preventScroll: true });
  }

  boton.addEventListener('click', function(e) {
    e.stopPropagation();
    if (caja.classList.contains('open')) cerrar(false); else abrir();
  });

  menu.addEventListener('click', function(e) {
    var op = e.target.closest('[data-idioma]');
    if (op) elegir(op.getAttribute('data-idioma'));
  });

  // Flechas para moverse entre idiomas, Escape para cerrar
  caja.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') { cerrar(true); return; }
    if (!caja.classList.contains('open')) return;
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
    e.preventDefault();
    var ops = Array.prototype.slice.call(menu.querySelectorAll('[data-idioma]'));
    var i = ops.indexOf(document.activeElement);
    var sig = e.key === 'ArrowDown' ? (i + 1) % ops.length : (i - 1 + ops.length) % ops.length;
    ops[sig].focus();
  });

  document.addEventListener('click', function(e) {
    if (!caja.contains(e.target)) cerrar(false);
  });

  // Banderas del menu ☰ de tablet y celular (alli no cabe la capsula)
  var enMenu = document.querySelector('.nav-idiomas');
  if (enMenu) enMenu.addEventListener('click', function(e) {
    var op = e.target.closest('[data-idioma]');
    if (op) elegir(op.getAttribute('data-idioma'));
  });
})();
