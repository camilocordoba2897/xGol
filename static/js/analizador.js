// ============================================================
//  CONEXIÓN CON EL SERVIDOR (Django + MySQL)
//  La biblioteca de equipos y el registro de apuestas ahora se
//  guardan en la base de datos por usuario (antes: localStorage).
//  Las URLs llegan desde el template en window.XGOL_API.
// ============================================================
const API = window.XGOL_API || {};
function getCsrf() {
  const el = document.querySelector('[name=csrfmiddlewaretoken]');
  return el ? el.value : '';
}

// ============================================================
//  ESTADO GLOBAL
// ============================================================
let state = { team1: null, team2: null };
let names = { team1: 'Local', team2: 'Visitante' };
let players = { team1: null, team2: null };
let fifaRankings = {}; // { 'pais': ranking_number }
let currentTab = 'data'; // pestaña activa (se persiste)

// ============================================================
//  PERSISTENCIA DE SESIÓN
//  Guarda el último enfrentamiento, la pestaña y el modo neutral
//  para no recargar CSVs al volver a abrir el archivo localmente.
// ============================================================
const SESSION_KEY = 'fba_session_v1';

function saveSession() {
  if (!libAvailable()) return;
  try {
    const payload = {
      team1: state.team1, team2: state.team2,
      names, players, neutralVenue, currentTab,
      refAvgCards, isClasico, isKnockout, mustWin1, mustWin2,
      accordionOpen, savedAt: new Date().toISOString()
    };
    localStorage.setItem(SESSION_KEY, JSON.stringify(payload));
  } catch (e) { /* cuota llena u otro: ignorar silenciosamente */ }
}

function restoreSession() {
  if (!libAvailable()) return false;
  let raw;
  try { raw = localStorage.getItem(SESSION_KEY); } catch (e) { return false; }
  if (!raw) return false;
  try {
    const p = JSON.parse(raw);
    if (!p || !p.team1 || !p.team2) return false;
    state.team1 = p.team1; state.team2 = p.team2;
    if (p.names) names = p.names;
    if (p.players) players = p.players;
    neutralVenue = !!p.neutralVenue;
    refAvgCards = (typeof p.refAvgCards === 'number' && p.refAvgCards > 0) ? p.refAvgCards : 0;
    isClasico  = !!p.isClasico;
    isKnockout = !!p.isKnockout;
    mustWin1   = !!p.mustWin1;
    mustWin2   = !!p.mustWin2;
    if (p.accordionOpen && typeof p.accordionOpen === 'object') accordionOpen = p.accordionOpen;
    // Marcar archivos como cargados en la UI
    const f1 = document.getElementById('file1-name');
    const f2 = document.getElementById('file2-name');
    if (f1) f1.textContent = '✅ ' + names.team1;
    if (f2) f2.textContent = '✅ ' + names.team2;
    renderAll();
    if (players.team1 || players.team2) renderPlayers();
    // Restaurar pestaña (si no es la de datos)
    if (p.currentTab && p.currentTab !== 'data') showTab(p.currentTab);
    showSessionBanner(p.savedAt);
    return true;
  } catch (e) { return false; }
}

function showSessionBanner(savedAt) {
  const el = document.getElementById('session-banner');
  if (!el) return;
  let when = '';
  if (savedAt) {
    try {
      const d = new Date(savedAt);
      when = ` · guardado ${d.toLocaleDateString('es', {day:'2-digit',month:'short'})} ${d.toLocaleTimeString('es',{hour:'2-digit',minute:'2-digit'})}`;
    } catch(_) {}
  }
  el.style.display = '';
  el.innerHTML = `<div class="session-banner">
    <span>♻️ Se recuperó tu último enfrentamiento: <strong>${names.team1}</strong> vs <strong>${names.team2}</strong>${when}</span>
    <button onclick="clearSession()" title="Empezar de cero">Empezar de nuevo</button>
  </div>`;
}

function clearSession() {
  try { localStorage.removeItem(SESSION_KEY); } catch(e) {}
  // Recargar limpio
  location.reload();
}

// ---- Estado de VALIDACIÓN (backtest manual) ----
// Partidos añadidos a mano para comprobar la calibración del modelo.
// Cada equipo guarda su propia lista (máx 8). El más reciente va primero.
let valMatches = { team1: [], team2: [] };
let valActiveTeam = 1; // 1 = local, 2 = visitante
const VAL_MAX = 8;

// ¿El partido a predecir es en cancha neutral? (final, Mundial, sede única)
// Si es true, no se aplica ventaja local y se usan stats neutrales/promedio.
let neutralVenue = false;

// #8 Contexto del partido (afecta sobre todo a TARJETAS, y la obligación de
// ganar también empuja córners/tiros del equipo presionado). Se editan desde el
// encabezado del enfrentamiento. 0/false = sin efecto.
let refAvgCards = 0;   // promedio de tarjetas del árbitro designado (0 = sin dato)
let isClasico   = false; // clásico / derbi
let isKnockout  = false; // partido de eliminatoria
let mustWin1    = false; // equipo 1 necesita ganar sí o sí (o queda eliminado)
let mustWin2    = false; // equipo 2 necesita ganar sí o sí

let historyActiveTeam = 1; // equipo mostrado en la pestaña Historial

// ============================================================
//  BIBLIOTECA DE EQUIPOS (localStorage)
//  Guarda la base de partidos de cada equipo en el navegador
//  para no tener que recargar CSVs. Persiste solo al abrir el
//  archivo localmente (no dentro de la vista previa del chat).
// ============================================================
const LIB_KEY = 'fba_team_library_v1';
let teamLibrary = {}; // { nombreEquipo: { rows: [...], savedAt: ISO } }
let pendingLibSave = null; // { name, rows } esperando resolución de conflicto

function libAvailable() {
  // Con almacenamiento en servidor siempre se puede guardar (si hay sesión).
  return true;
}

async function loadLibrary() {
  try {
    const resp = await fetch(API.cargarBiblioteca, { headers:{'X-Requested-With':'fetch'} });
    const data = await resp.json();
    teamLibrary = data.teamLibrary || {};
  } catch (e) { teamLibrary = {}; }
}

function persistLibrary() {
  // Guarda la biblioteca en MySQL. Envío en segundo plano: la copia en
  // memoria ya está actualizada, así el render no espera a la red.
  try {
    fetch(API.guardarBiblioteca, {
      method:'POST',
      headers:{'Content-Type':'application/json','X-CSRFToken':getCsrf()},
      body: JSON.stringify({ teamLibrary })
    });
    return true;
  } catch (e) { return false; }
}

function libStatus(msg, warn) {
  const el = document.getElementById('lib-status');
  if (!el) return;
  el.textContent = msg || '';
  el.className = 'lib-status' + (warn ? ' warn' : '');
  if (msg) setTimeout(() => { if (el.textContent === msg) { el.textContent=''; } }, 4000);
}

// Guarda un equipo. Si ya existe, dispara el modal de conflicto.
function saveTeamToLibrary(name, rows, forceMode) {
  if (!name || !rows || !rows.length) return;
  if (!libAvailable()) {
    libStatus('⚠️ Este navegador no permite guardar (modo privado o vista previa). Usa Exportar como respaldo.', true);
    return;
  }
  const exists = teamLibrary[name] !== undefined;
  if (exists && !forceMode) {
    // Abrir modal de conflicto
    pendingLibSave = { name, rows };
    document.getElementById('lib-modal-name').textContent = name;
    document.getElementById('lib-modal-bg').classList.add('show');
    return;
  }
  let finalName = name;
  if (forceMode === 'copy') {
    let i = 2;
    while (teamLibrary[`${name} (${i})`] !== undefined) i++;
    finalName = `${name} (${i})`;
  }
  teamLibrary[finalName] = { rows, savedAt: new Date().toISOString() };
  persistLibrary();
  renderLibrary();
  libStatus(`✅ "${finalName}" guardado en la biblioteca`);
}

function resolveLibConflict(mode) {
  document.getElementById('lib-modal-bg').classList.remove('show');
  if (!pendingLibSave) return;
  const { name, rows } = pendingLibSave;
  pendingLibSave = null;
  if (mode === 'cancel') { libStatus('No se guardó. El equipo está cargado solo para esta sesión.'); return; }
  saveTeamToLibrary(name, rows, mode); // 'overwrite' o 'copy'
}

function deleteTeamFromLibrary(name) {
  if (teamLibrary[name] === undefined) return;
  delete teamLibrary[name];
  persistLibrary();
  renderLibrary();
  libStatus(`🗑 "${name}" eliminado`);
}

function clearLibrary() {
  const count = Object.keys(teamLibrary).length;
  if (!count) return;
  if (!confirm(`¿Vaciar la biblioteca completa? Se eliminarán ${count} equipo(s). Esto no se puede deshacer.`)) return;
  teamLibrary = {};
  persistLibrary();
  renderLibrary();
  libStatus('Biblioteca vaciada');
}

// Cargar un enfrentamiento desde los dos selectores
// Resuelve lo escrito en el input a un equipo de la biblioteca:
// acepta match exacto o, si no, ignorando mayúsculas/espacios.
function resolveLibTeam(input) {
  if (input == null) return '';
  const v = String(input).trim();
  if (v === '') return '';
  if (teamLibrary[v] !== undefined) return v;
  const lower = v.toLowerCase();
  const hit = Object.keys(teamLibrary).find(k => k.toLowerCase() === lower);
  return hit || v; // si no existe, devuelve lo escrito (dará "no encontrado")
}

function loadMatchupFromLibrary() {
  const sel1 = resolveLibTeam(document.getElementById('lib-select-1').value);
  const sel2 = resolveLibTeam(document.getElementById('lib-select-2').value);
  if (!sel1 || !sel2) { libStatus('Elige ambos equipos primero', true); return; }
  if (sel1 === sel2) { libStatus('⚠️ Elige dos equipos distintos', true); return; }
  const t1 = teamLibrary[sel1], t2 = teamLibrary[sel2];
  if (!t1 || !t2) { libStatus('Equipo no encontrado', true); return; }

  // Reflejar el nombre canónico en los inputs (por si se escribió en minúsculas)
  document.getElementById('lib-select-1').value = sel1;
  document.getElementById('lib-select-2').value = sel2;

  state.team1 = t1.rows.slice();
  state.team2 = t2.rows.slice();
  names.team1 = sel1; names.team2 = sel2;
  // Limpiar validación al cambiar de equipos (banco de pruebas pertenece a otro matchup)
  valMatches = { team1: [], team2: [] };
  players = { team1: null, team2: null };

  document.getElementById('file1-name').textContent = sel1 + ' (biblioteca)';
  document.getElementById('file2-name').textContent = sel2 + ' (biblioteca)';
  document.getElementById('drop1').style.borderColor = 'var(--accent)';
  document.getElementById('drop2').style.borderColor = 'var(--accent)';
  renderAll();
  libStatus(`⚡ ${sel1} vs ${sel2} cargado`);
}

function renderLibrary() {
  const box = document.getElementById('library-box');
  if (!box) return;
  const names_ = Object.keys(teamLibrary).sort((a,b) => a.localeCompare(b));

  // Mostrar el panel solo si hay equipos o si localStorage funciona
  if (names_.length === 0 && !libAvailable()) { box.style.display = 'none'; return; }
  box.style.display = '';

  // Listas de autocompletado: el usuario escribe para buscar y, al enfocar,
  // igual aparecen todas las opciones para elegir (input + datalist).
  const opts = names_.map(n => `<option value="${n.replace(/"/g,'&quot;')}"></option>`).join('');
  const dl1 = document.getElementById('lib-list-1');
  const dl2 = document.getElementById('lib-list-2');
  if (dl1) dl1.innerHTML = opts;
  if (dl2) dl2.innerHTML = opts;

  const loadBtn = document.getElementById('lib-load-btn');
  if (loadBtn) loadBtn.disabled = names_.length < 2;

  // Lista de chips
  const listEl = document.getElementById('lib-saved-list');
  if (names_.length === 0) {
    listEl.innerHTML = '<span class="lib-empty-note">Aún no hay equipos guardados. Carga un CSV abajo y elige guardarlo.</span>';
  } else {
    listEl.innerHTML = names_.map(n => {
      const count = teamLibrary[n].rows.length;
      return `<span class="lib-chip">${n} <span class="lib-chip-count">${count}p</span>
        <button onclick="deleteTeamFromLibrary('${n.replace(/'/g,"\\'")}')" title="Eliminar">✕</button></span>`;
    }).join('');
  }
}

// Exportar / importar biblioteca completa (respaldo, portable entre dispositivos)
function exportLibrary() {
  const names_ = Object.keys(teamLibrary);
  if (!names_.length) { libStatus('No hay nada que exportar', true); return; }
  const blob = new Blob([JSON.stringify(teamLibrary, null, 2)], {type:'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'biblioteca_equipos.json';
  a.click();
  libStatus('⬇ Biblioteca exportada');
}

function importLibrary(e) {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = function(ev) {
    try {
      const imported = JSON.parse(ev.target.result);
      let added = 0;
      Object.entries(imported).forEach(([name, data]) => {
        if (data && Array.isArray(data.rows) && data.rows.length) {
          teamLibrary[name] = { rows: data.rows, savedAt: data.savedAt || new Date().toISOString() };
          added++;
        }
      });
      persistLibrary();
      renderLibrary();
      libStatus(`⬆ ${added} equipo(s) importado(s)`);
    } catch (err) {
      libStatus('⚠️ Archivo inválido', true);
    }
  };
  reader.readAsText(file, 'UTF-8');
  e.target.value = '';
}


// Rankings FIFA top 120 — actualizados
const DEFAULT_FIFA_RANKINGS = {
  'Argentina':1,'España':2,'Francia':3,'Inglaterra':4,'Portugal':5,
  'Brasil':6,'Marruecos':7,'Países Bajos':8,'Bélgica':9,'Alemania':10,
  'Croacia':11,'Italia':12,'Colombia':13,'México':14,'Senegal':15,
  'Uruguay':16,'Estados Unidos':17,'Japón':18,'Suiza':19,'Irán':20,
  'Dinamarca':21,'Turquía':22,'Ecuador':23,'Austria':24,'Corea del Sur':25,
  'Nigeria':26,'Australia':27,'Argelia':28,'Egipto':29,'Canadá':30,
  'Noruega':31,'Ucrania':32,'Costa de Marfil':33,'Panamá':34,'Rusia':35,
  'Polonia':36,'Gales':37,'Suecia':38,'Hungría':39,'República Checa':40,
  'Paraguay':41,'Escocia':42,'Serbia':43,'Camerún':44,'Túnez':45,
  'República Democrática del Congo':46,'Eslovaquia':47,'Grecia':48,
  'Venezuela':49,'Uzbekistán':50,'Chile':51,'Perú':52,'Costa Rica':53,
  'Rumanía':54,'Malí':55,'Catar':56,'Irak':57,'Irlanda':58,
  'Eslovenia':59,'Sudáfrica':60,'Arabia Saudita':61,'Burkina Faso':62,
  'Jordania':63,'Bosnia y Herzegovina':64,'Honduras':65,'Albania':66,
  'Cabo Verde':67,'Emiratos Árabes Unidos':68,'Macedonia del Norte':69,
  'Irlanda del Norte':70,'Jamaica':71,'Georgia':72,'Ghana':73,
  'Islandia':74,'Finlandia':75,'Israel':76,'Bolivia':77,'Kosovo':78,
  'Omán':79,'Montenegro':80,'Guinea':81,'Curazao':82,'Haití':83,
  'Siria':84,'Nueva Zelanda':85,'Gabón':86,'Bulgaria':87,'Angola':88,
  'Uganda':89,'Zambia':90,'China':91,'Baréin':92,'Benín':93,
  'Tailandia':94,'Palestina':95,'Bielorrusia':96,'Guatemala':97,
  'Luxemburgo':98,'Vietnam':99,'El Salvador':100,'Tayikistán':101,
  'Trinidad y Tobago':102,'Mozambique':103,'Madagascar':104,
  'Guinea Ecuatorial':105,'Kirguistán':106,'Armenia':107,'Comoras':108,
  'Kenia':109,'Libia':110,'Kazajistán':111,'Tanzania':112,
  'Mauritania':113,'Níger':114,'Líbano':115,'Gambia':116,'Sudán':117,
  'Indonesia':118,'Togo':119,'Corea del Norte':120
};
// Umbral: rivales fuera del top 120 se tratan como ranking 130 (equipo débil)
const FIFA_UNKNOWN_RANK = 130;
const FIFA_MAX_RANK = 130;

// ---- NORMALIZACIÓN DE NOMBRES ----
// Elimina tildes, convierte a minúsculas, quita espacios extra
function normalizeName(str) {
  return (str || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '') // quita diacríticos (tildes, etc.)
    .replace(/[^a-z0-9\s]/g, '')     // quita caracteres especiales
    .replace(/\s+/g, ' ')
    .trim();
}

// Mapa normalizado del ranking FIFA (se construye una vez)
const FIFA_NORMALIZED = {};
Object.entries(DEFAULT_FIFA_RANKINGS).forEach(([pais, rank]) => {
  FIFA_NORMALIZED[normalizeName(pais)] = { pais, rank };
});

// Alias de nombres alternativos comunes → nombre oficial en el ranking
const FIFA_ALIASES = {
  'holanda':              'Países Bajos',
  'netherlands':          'Países Bajos',
  'holland':              'Países Bajos',
  'paises bajos':         'Países Bajos',
  'usa':                  'Estados Unidos',
  'united states':        'Estados Unidos',
  'estados unidos':       'Estados Unidos',
  'ee uu':                'Estados Unidos',
  'eeuu':                 'Estados Unidos',
  'us':                   'Estados Unidos',
  'korea':                'Corea del Sur',
  'south korea':          'Corea del Sur',
  'korea del sur':        'Corea del Sur',
  'corea':                'Corea del Sur',
  'republic of korea':    'Corea del Sur',
  'england':              'Inglaterra',
  'germany':              'Alemania',
  'spain':                'España',
  'france':               'Francia',
  'brazil':               'Brasil',
  'brasil':               'Brasil',
  'japan':                'Japón',
  'japon':                'Japón',
  'iran':                 'Irán',
  'switzerland':          'Suiza',
  'sweden':               'Suecia',
  'norway':               'Noruega',
  'turkey':               'Turquía,',
  'turquia':              'Turquía',
  'belgium':              'Bélgica',
  'belgica':              'Bélgica',
  'croatia':              'Croacia',
  'morocco':              'Marruecos',
  'marruecos':            'Marruecos',
  'senegal':              'Senegal',
  'mexico':               'México',
  'panama':               'Panamá',
  'czech republic':       'Chequia',
  'czechia':              'Chequia',
  'republica checa':      'Chequia',
  'ivory coast':          'Costa de Marfil',
  'cote d ivoire':        'Costa de Marfil',
  'new zealand':          'Nueva Zelanda',
  'democratic republic of congo': 'República Democrática del Congo',
  'dr congo':             'República Democrática del Congo',
  'rd congo':             'República Democrática del Congo',
  'congo dr':             'República Democrática del Congo',
  'bosnia':               'Bosnia y Herzegovina',
  'bosnia herzegovina':   'Bosnia y Herzegovina',
  'north macedonia':      'Macedonia del Norte',
  'macedonia':            'Macedonia del Norte',
  'northern ireland':     'Irlanda del Norte',
  'saudi arabia':         'Arabia Saudita',
  'arabia saudi':         'Arabia Saudita',
  'emirates':             'Emiratos Árabes Unidos',
  'uae':                  'Emiratos Árabes Unidos',
  'emiratos arabes':      'Emiratos Árabes Unidos',
  'republic of ireland':  'Irlanda',
  'south africa':         'Sudáfrica',
  'sudafrica':            'Sudáfrica',
  'egypt':                'Egipto',
  'ghana':                'Ghana',
  'cameroon':             'Camerún',
  'camerun':              'Camerún',
  'algeria':              'Argelia',
  'scotland':             'Escocia',
  'wales':                'Gales',
  'greece':               'Grecia',
  'romania':              'Rumania',
  'rumania':              'Rumania',
  'venezuela':            'Venezuela',
  'bolivia':              'Bolivia',
  'paraguay':             'Paraguay',
  'ecuador':              'Ecuador',
  'uruguay':              'Uruguay',
  'colombia':             'Colombia',
  'argentina':            'Argentina',
  'portugal':             'Portugal',
  'canada':               'Canadá',
  'australia':            'Australia',
  'qatar':                'Catar',
  'katar':                'Catar',
  'iraq':                 'Irak',
  'israel':               'Israel',
  'india':                'India',
  'china':                'China',
  'thailand':             'Tailandia',
  'tailandia':            'Tailandia',
  'vietnam':              'Vietnam',
  'lebanon':              'Líbano',
  'libano':               'Líbano',
  'syria':                'Siria',
  'palestine':            'Palestina',
  'jordan':               'Jordania',
  'uzbekistan':           'Uzbekistán',
  'kyrgyzstan':           'Kirguistán',
  'kirguistan':           'Kirguistán',
  'tajikistan':           'Tayikistán',
  'tayikistan':           'Tayikistán',
  'kazakhstan':           'Kazajistán',
  'kazajstan':            'Kazajistán',
  'bahrain':              'Bahréin',
  'bahrein':              'Bahréin',
  'oman':                 'Omán',
  'luxembourg':           'Luxemburgo',
  'zimbabwe':             'Zimbabue',
  'zimbabue':             'Zimbabue',
  'namibia':              'Namibia',
  'botswana':             'Botsuana',
  'botsuana':             'Botsuana',
  'malawi':               'Malaui',
  'malaui':               'Malaui',
  'ethiopia':             'Etiopía',
  'etiopia':              'Etiopía',
  'rwanda':               'Ruanda',
  'ruanda':               'Ruanda',
  'sudan':                'Sudán',
  'mauritania':           'Mauritania',
  'libya':                'Libia',
  'niger':                'Níger',
  'togo':                 'Togo',
  'comoros':              'Comoras',
  'south sudan':          'Sudán del Sur',
  'sudan del sur':        'Sudán del Sur',
  'gabon':                'Gabón',
  'guinea':               'Guinea',
  'jamaica':              'Jamaica',
  'honduras':             'Honduras',
  'el salvador':          'El Salvador',
  'guatemala':            'Guatemala',
  'haiti':                'Haití',
  'curacao':              'Curazao',
  'cape verde':           'Cabo Verde',
  'cabo verde':           'Cabo Verde',
  'ukraine':              'Ucrania',
  'ucrania':              'Ucrania',
  'poland':               'Polonia',
  'serbia':               'Serbia',
  'slovakia':             'Eslovaquia',
  'eslovaquia':           'Eslovaquia',
  'slovenia':             'Eslovenia',
  'eslovenia':            'Eslovenia',
  'mali':                 'Malí',
  'burkina faso':         'Burkina Faso',
  'georgia':              'Georgia',
  'finland':              'Finlandia',
  'albania':              'Albania',
  'iceland':              'Islandia',
  'islandia':             'Islandia',
  'montenegro':           'Montenegro',
  'kosovo':               'Kosovo',
  'armenia':              'Armenia',
  'azerbaijan':           'Azerbaiyán',
  'azerbaiyan':           'Azerbaiyán',
  'belarus':              'Bielorrusia',
  'bielorrusia':          'Bielorrusia',
  'belarús':              'Bielorrusia',
  'cyprus':               'Chipre',
  'estonia':              'Estonia',
  'latvia':               'Letonia',
  'letonia':              'Letonia',
  'lithuania':            'Lituania',
  'lituania':             'Lituania',
  'moldova':              'Moldavia',
  'tanzania':             'Tanzania',
  'uganda':               'Uganda',
  'kenya':                'Kenia',
  'kenia':                'Kenia',
  'benin':                'Benín',
  'zambia':               'Zambia',
  'angola':               'Angola',
  'mozambique':           'Mozambique',
  'madagascar':           'Madagascar',
  // Nuevos en ranking v2
  'italia':               'Italia',
  'italy':                'Italia',
  'dinamarca':            'Dinamarca',
  'denmark':              'Dinamarca',
  'nigeria':              'Nigeria',
  'hungria':              'Hungría',
  'hungary':              'Hungría',
  'republica checa':      'República Checa',
  'czech republic':       'República Checa',
  'czechia':              'República Checa',
  'chequia':              'República Checa',
  'rusia':                'Rusia',
  'russia':               'Rusia',
  'chile':                'Chile',
  'peru':                 'Perú',
  'costa rica':           'Costa Rica',
  'rumania':              'Rumanía',
  'romania':              'Rumanía',
  'bahrein':              'Baréin',
  'bahrain':              'Baréin',
  'bahréin':              'Baréin',
  'trinidad tobago':      'Trinidad y Tobago',
  'trinidad and tobago':  'Trinidad y Tobago',
  'guinea ecuatorial':    'Guinea Ecuatorial',
  'equatorial guinea':    'Guinea Ecuatorial',
  'gambia':               'Gambia',
  'indonesia':            'Indonesia',
  'corea del norte':      'Corea del Norte',
  'north korea':          'Corea del Norte',
  'dprk':                 'Corea del Norte',
  'bulgaria':             'Bulgaria',
};

// Función principal de búsqueda: intenta match exacto → normalizado → alias
function lookupFIFA(name) {
  if (!name) return null;
  // 1. Match exacto
  if (DEFAULT_FIFA_RANKINGS[name]) return { pais: name, rank: DEFAULT_FIFA_RANKINGS[name] };
  // 2. Match normalizado (sin tildes, minúsculas)
  const norm = normalizeName(name);
  if (FIFA_NORMALIZED[norm]) return FIFA_NORMALIZED[norm];
  // 3. Match por alias
  const aliasTarget = FIFA_ALIASES[norm];
  if (aliasTarget && DEFAULT_FIFA_RANKINGS[aliasTarget]) {
    return { pais: aliasTarget, rank: DEFAULT_FIFA_RANKINGS[aliasTarget] };
  }
  return null;
}
// Start with defaults loaded
fifaRankings = {...DEFAULT_FIFA_RANKINGS};

// ============================================================
//  UI HELPERS
// ============================================================
function showTab(id) {
  const seccion = document.getElementById('tab-' + id);
  if (!seccion) return; // pestaña no disponible para este usuario (ej. secciones solo-admin)
  const keys = ['data','analysis','bets','players','history','validation'];
  document.querySelectorAll('.tab').forEach((t,i) => t.classList.toggle('active', keys[i] === id));
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  seccion.classList.add('active');
  currentTab = id;
  saveSession();
}
function drag(e,n){ e.preventDefault(); document.getElementById('drop'+n).classList.add('drag'); }
function undrag(n){ document.getElementById('drop'+n).classList.remove('drag'); }
function drop(e,n){ e.preventDefault(); undrag(n); handleFileObj(e.dataTransfer.files[0], n); }
function handleFile(e,n){ handleFileObj(e.target.files[0], n); }
function handleFileObj(file, n) {
  if (!file) return;
  const reader = new FileReader();
  reader.onload = function(e) {
    const parsed = parseCSV(e.target.result);
    if (parsed && parsed.rows.length > 0) {
      const teamName = parsed.teamName || 'Equipo ' + n;
      state['team'+n] = parsed.rows;
      names['team'+n] = teamName;
      document.getElementById('file'+n+'-name').textContent = file.name;
      document.getElementById('drop'+n).style.borderColor = 'var(--accent)';
      if (state.team1 && state.team2) renderAll();
      // Ofrecer guardar en la biblioteca (abre modal si ya existe)
      saveTeamToLibrary(teamName, parsed.rows.slice());
    }
  };
  reader.readAsText(file, 'UTF-8');
}

// ---- FIFA RANKING FILE HANDLER ----
function handleFileFIFA(e) {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = function(ev) {
    const parsed = parseCSV(ev.target.result);
    if (!parsed) return;
    const newRankings = {...DEFAULT_FIFA_RANKINGS}; // start from defaults
    parsed.rows.forEach(r => {
      const pais = (r.pais || r.país || r.country || r.team || '').trim();
      const rank = +(r.ranking || r.rank || r.posicion || 0);
      if (pais && rank > 0) newRankings[pais] = rank;
    });
    fifaRankings = newRankings;
    const count = parsed.rows.length;
    document.getElementById('fileFIFA-name').textContent = file.name;
    document.getElementById('fifa-status').textContent = `✅ ${count} países cargados · ranking activo`;
    document.getElementById('dropFIFA').style.borderColor = 'var(--accent)';
    // Re-render if teams already loaded
    if (state.team1 && state.team2) renderAll();
  };
  reader.readAsText(file, 'UTF-8');
}

// ---- PLAYER FILE HANDLERS ----
function handleFileP(e, n) { handleFilePObj(e.target.files[0], n); }
function handleFilePObj(file, n) {
  if (!file) return;
  const reader = new FileReader();
  reader.onload = function(ev) {
    const parsed = parseCSV(ev.target.result);
    if (parsed && parsed.rows.length > 0) {
      players['team'+n] = parsed.rows;
      document.getElementById('fileP'+n+'-name').textContent = file.name;
      document.getElementById('dropP'+n).style.borderColor = 'var(--accent)';
      if (players.team1 || players.team2) renderPlayers();
    }
  };
  reader.readAsText(file, 'UTF-8');
}

// ============================================================
//  CSV PARSER — soporta , y ;
// ============================================================
function parseCSV(text) {
  const lines = text.trim().split(/\r?\n/);
  if (lines.length < 2) return null;
  const sep = lines[0].includes(';') ? ';' : ',';
  const headers = lines[0].split(sep).map(h => h.trim().toLowerCase().replace(/[^a-z0-9_]/g,''));
  const rows = [];
  let teamName = '';
  for (let i = 1; i < lines.length; i++) {
    if (!lines[i].trim()) continue;
    const vals = lines[i].split(sep).map(v => v.trim().replace(/^"|"$/g,''));
    const row = {};
    headers.forEach((h, j) => row[h] = vals[j] || '');
    if (!teamName && row.equipo) teamName = row.equipo;
    rows.push(row);
  }
  return { rows, teamName };
}

// ============================================================
//  DEMO DATA
// ============================================================
function loadDemo() {
  const makeTeam = (name, offStr, defStr, n) => {
    const rows = [];
    const resultSets = {
      'México':    ['W','W','D','W','W','L','W','D','W','W','W','D','W','W','L'],
      'Sudáfrica': ['D','W','L','D','W','W','L','D','W','L','D','W','W','L','D']
    };
    const res = resultSets[name] || resultSets['México'];
    for (let i = 0; i < n; i++) {
      const r = res[i] || 'D';
      const gf = Math.max(0, Math.round(offStr + (Math.random()-.4)*1.8));
      const gc = Math.max(0, Math.round(defStr + (Math.random()-.5)*1.8));
      const g1f = Math.max(0, Math.min(gf, Math.round(gf * 0.44 + (Math.random()-.5))));
      const g1c = Math.max(0, Math.min(gc, Math.round(gc * 0.44 + (Math.random()-.5))));
      rows.push({
        equipo: name, resultado: r, sede: i%2===0?'local':'visitante',
        goles_f: gf, goles_c: gc,
        goles_1t_f: g1f, goles_1t_c: g1c,
        goles_2t_f: Math.max(0, gf-g1f), goles_2t_c: Math.max(0, gc-g1c),
        tiros: Math.max(5, Math.round((offStr*4.5) + (Math.random()-.4)*3)),
        tiros_rival: Math.max(3, Math.round((defStr*4.5) + (Math.random()-.5)*3)),
        tiros_puerta: Math.max(2, Math.round((offStr*1.9) + (Math.random()-.4)*2)),
        tiros_puerta_rival: Math.max(1, Math.round((defStr*1.9) + (Math.random()-.5)*2)),
        corners: Math.max(2, Math.round(6 + (Math.random()-.4)*3)),
        corners_rival: Math.max(1, Math.round(4.5 + (Math.random()-.5)*3)),
        tarjetas_a: Math.max(0, Math.round(1.5 + (Math.random()-.5))),
        tarjetas_r: Math.random() > .88 ? 1 : 0,
        asistencias: Math.max(0, Math.round(gf * .7)),
        fecha: new Date(Date.now() - i * 7 * 86400000).toISOString().slice(0,10)
      });
    }
    return rows;
  };
  state.team1 = makeTeam('México', 2.3, 1.0, 15);
  state.team2 = makeTeam('Sudáfrica', 1.4, 1.5, 15);
  names.team1 = 'México'; names.team2 = 'Sudáfrica';
  document.getElementById('file1-name').textContent = 'mexico_demo.csv';
  document.getElementById('file2-name').textContent = 'sudafrica_demo.csv';
  document.getElementById('drop1').style.borderColor = 'var(--accent)';
  document.getElementById('drop2').style.borderColor = 'var(--accent)';

  // Generate demo player data
  const makePlayers = (teamName, roster) => {
    const rows = [];
    const nGames = 12;
    roster.forEach(p => {
      for (let i = 0; i < nGames; i++) {
        const played = p.pos === 'GK' ? 1 : Math.random() > 0.15 ? 1 : 0;
        if (!played) continue;
        const mins = p.pos === 'GK' ? 90 : Math.round(60 + Math.random()*30);
        const shots = p.pos === 'FW' ? Math.round(Math.random()*3.5)
                    : p.pos === 'MF' ? Math.round(Math.random()*2)
                    : Math.round(Math.random()*0.8);
        const onTarget = Math.min(shots, Math.round(shots * (0.35 + Math.random()*0.3)));
        const goals = Math.random() < p.goalRate ? 1 : 0;
        const assists = goals === 0 && Math.random() < p.assistRate ? 1 : 0;
        const yellowCard = Math.random() < p.yellowRate ? 1 : 0;
        const redCard = yellowCard && Math.random() < 0.05 ? 1 : 0;
        rows.push({
          jugador: p.name, equipo: teamName, posicion: p.pos,
          partido: i + 1, minutos: mins,
          goles: goals, asistencias: assists,
          tiros: shots, tiros_puerta: onTarget,
          tarjetas_a: yellowCard, tarjetas_r: redCard
        });
      }
    });
    return rows;
  };

  const mxRoster = [
    {name:'G. Ochoa',   pos:'GK', goalRate:0.00, assistRate:0.00, yellowRate:0.05},
    {name:'J. Sánchez', pos:'DF', goalRate:0.03, assistRate:0.05, yellowRate:0.18},
    {name:'C. Montes',  pos:'DF', goalRate:0.04, assistRate:0.03, yellowRate:0.20},
    {name:'H. Moreno',  pos:'DF', goalRate:0.05, assistRate:0.04, yellowRate:0.22},
    {name:'L. Rodríguez',pos:'MF',goalRate:0.08, assistRate:0.14, yellowRate:0.15},
    {name:'E. Herrera', pos:'MF', goalRate:0.10, assistRate:0.16, yellowRate:0.12},
    {name:'A. Guardado',pos:'MF', goalRate:0.09, assistRate:0.18, yellowRate:0.10},
    {name:'H. Lozano',  pos:'FW', goalRate:0.28, assistRate:0.14, yellowRate:0.08},
    {name:'R. Jiménez', pos:'FW', goalRate:0.32, assistRate:0.12, yellowRate:0.07},
    {name:'A. Vega',    pos:'FW', goalRate:0.20, assistRate:0.16, yellowRate:0.09},
    {name:'J. Corona',  pos:'MF', goalRate:0.12, assistRate:0.20, yellowRate:0.10},
  ];
  const saRoster = [
    {name:'R. Williams', pos:'GK', goalRate:0.00, assistRate:0.00, yellowRate:0.04},
    {name:'T. Khumalo',  pos:'DF', goalRate:0.03, assistRate:0.04, yellowRate:0.22},
    {name:'S. Mokoena',  pos:'DF', goalRate:0.04, assistRate:0.03, yellowRate:0.24},
    {name:'L. Ntuli',    pos:'DF', goalRate:0.03, assistRate:0.05, yellowRate:0.20},
    {name:'B. Zwane',    pos:'MF', goalRate:0.10, assistRate:0.18, yellowRate:0.14},
    {name:'T. Dolly',    pos:'MF', goalRate:0.12, assistRate:0.15, yellowRate:0.11},
    {name:'P. Cele',     pos:'MF', goalRate:0.08, assistRate:0.12, yellowRate:0.16},
    {name:'V. Mkhize',   pos:'FW', goalRate:0.25, assistRate:0.10, yellowRate:0.08},
    {name:'T. Ndlovu',   pos:'FW', goalRate:0.22, assistRate:0.12, yellowRate:0.09},
    {name:'K. Sithole',  pos:'FW', goalRate:0.18, assistRate:0.14, yellowRate:0.10},
    {name:'M. Mabunda',  pos:'MF', goalRate:0.09, assistRate:0.16, yellowRate:0.12},
  ];

  players.team1 = makePlayers('México', mxRoster);
  players.team2 = makePlayers('Sudáfrica', saRoster);
  document.getElementById('fileP1-name').textContent = 'jugadores_mexico_demo.csv';
  document.getElementById('fileP2-name').textContent = 'jugadores_sudafrica_demo.csv';
  document.getElementById('dropP1').style.borderColor = 'var(--accent)';
  document.getElementById('dropP2').style.borderColor = 'var(--accent)';

  renderAll();
  renderPlayers();
}

// ============================================================
//  PONDERACIÓN TEMPORAL
//  Los partidos más recientes pesan más (decaimiento exponencial)
//  peso[i] = exp(-i * DECAY), i=0 es el más reciente
// ============================================================
const DECAY = 0.23; // últimos 5 partidos = ~70% del peso total
// ---- Decay por FECHA (si el CSV la trae) ----
// El decay por índice asume partidos equiespaciados: uno de hace 8 días y uno
// de hace 4 meses pueden pesar casi igual. Si TODAS las filas traen fecha
// parseable, se pondera por días transcurridos: w = exp(-DECAY_DAY · días),
// con DECAY_DAY = DECAY/7 (equivale al decay por índice con partidos semanales).
// Si alguna fila no trae fecha → fallback al decay por índice (comportamiento previo).
const DECAY_DAY = DECAY / 7;
let _curW = null; // pesos crudos por fecha del computeStats en curso (o null)
function dateWeights(rows) {
  if (!rows || rows.length < 2) return null;
  const ts = rows.map(r => Date.parse(r && r.fecha ? r.fecha : ''));
  if (ts.some(t => isNaN(t))) return null;
  const newest = Math.max(...ts);
  return ts.map(t => Math.exp(-DECAY_DAY * (newest - t) / 86400000));
}
function weights(n) {
  if (_curW && _curW.length === n) {
    const sum = _curW.reduce((a,b) => a+b, 0);
    if (sum > 0) return _curW.map(v => v / sum);
  }
  const w = Array.from({length: n}, (_, i) => Math.exp(-i * DECAY));
  const sum = w.reduce((a,b) => a+b, 0);
  return w.map(v => v / sum);
}
function wavg(arr) {
  const w = weights(arr.length);
  return arr.reduce((s, v, i) => s + w[i] * (+v || 0), 0);
}
// Varianza ponderada (para binomial negativa): E[X²] - E[X]²
function wvar(arr) {
  const w = weights(arr.length);
  let m = 0, m2 = 0;
  for (let i = 0; i < arr.length; i++) { const v = +arr[i] || 0; m += w[i]*v; m2 += w[i]*v*v; }
  return Math.max(0, m2 - m*m);
}
function wpct(arr, fn) {
  const w = weights(arr.length);
  return arr.reduce((s, v, i) => s + w[i] * (fn(v) ? 1 : 0), 0);
}
// Promedio ponderado SOLO sobre las filas que tienen dato (renormaliza los
// pesos a esas filas). Si NINGUNA fila tiene dato devuelve null → el modelo
// lo interpreta como "sin información" y no influye en los cálculos.
function wavgMasked(arr, hasArr) {
  const w = weights(arr.length);
  let num = 0, den = 0;
  for (let i = 0; i < arr.length; i++) {
    if (!hasArr[i]) continue;
    num += w[i] * (+arr[i] || 0);
    den += w[i];
  }
  return den > 0 ? num / den : null;
}
// #8 Multiplicador de presión a partir del PPDA (passes per defensive action).
// PPDA bajo = el equipo presiona mucho → fuerza más córners y tiros.
// Se compara contra la media de liga y se acota a ±PPDA_MAX_BOOST.
// Si no hay PPDA (null/0) devuelve 1 → no influye.
function pressMult(ppda) {
  if (ppda == null || !(ppda > 0)) return 1;
  const raw = PPDA_LEAGUE / ppda;
  return Math.min(1 + PPDA_MAX_BOOST, Math.max(1 - PPDA_MAX_BOOST, raw));
}
// #Pendiente v7.6 resuelto: SHRINKAGE del PPDA por tamaño de muestra.
// Con 1 partido con dato el multiplicador aplicaba completo (±15%); ahora se
// atenúa hacia 1 con peso = n/(n+K), K=3: 1 partido→25%, 3→50%, 10→77%.
const PPDA_SHRINK_K = 3;
function pressMultShrunk(ppda, n) {
  const m = pressMult(ppda);
  if (m === 1 || !(n > 0)) return 1;
  const w = n / (n + PPDA_SHRINK_K);
  return 1 + (m - 1) * w;
}
// Cruce de presión: PPDA propio (cuánto presiono) + PPDA_c del rival (cuánta
// presión sufre habitualmente). Se promedian los valores disponibles y se aplica
// UN multiplicador con shrinkage por la muestra combinada. Sin datos → 1.
function pressCross(myPpdaF, myN, rivPpdaC, rivN) {
  const vals = [], ns = [];
  if (myPpdaF != null && myPpdaF > 0 && myN > 0) { vals.push(myPpdaF); ns.push(myN); }
  if (rivPpdaC != null && rivPpdaC > 0 && rivN > 0) { vals.push(rivPpdaC); ns.push(rivN); }
  if (!vals.length) return 1;
  const avgPpda = vals.reduce((a,b)=>a+b,0) / vals.length;
  const totalN  = ns.reduce((a,b)=>a+b,0);
  return pressMultShrunk(avgPpda, totalN);
}

// ============================================================
//  POISSON
//  P(X = k) = e^(-λ) * λ^k / k!
// ============================================================
function poissonP(lambda, k) {
  if (lambda <= 0) return k === 0 ? 1 : 0;
  let p = Math.exp(-lambda);
  for (let i = 0; i < k; i++) p *= lambda / (i + 1);
  return p;
}
// P(X > threshold) usando distribución Poisson
function poissonOver(lambda, threshold) {
  let cum = 0;
  for (let k = 0; k <= threshold; k++) cum += poissonP(lambda, k);
  return Math.max(0, Math.min(1, 1 - cum));
}
// ---- Binomial negativa: P(X > k) con sobredispersión ----
// Córners, tiros y tarjetas tienen varianza > media en la realidad; Poisson les
// pone colas demasiado finas. Si la varianza empírica supera a la media, se usa
// NB parametrizada por (mu, var): r = mu²/(var-mu), p = r/(r+mu).
// Recurrencia: P(0)=p^r; P(j)=P(j-1)·(r+j-1)/j·(1-p). Si var≤mu → cae a Poisson.
function nbOver(mu, varr, threshold) {
  if (!(varr > mu * 1.02) || mu <= 0) return poissonOver(mu, threshold);
  const r = mu * mu / (varr - mu);
  const p = r / (r + mu);
  let pj = Math.pow(p, r), cum = pj;
  for (let j = 1; j <= threshold; j++) { pj *= (r + j - 1) / j * (1 - p); cum += pj; }
  return Math.max(0, Math.min(1, 1 - cum));
}

// ============================================================
//  #5 CORRELACIÓN ENTRE MERCADOS — utilidades numéricas
//  Dos niveles de combinadas (mismo partido):
//   (A) EXACTAS: cualquier par de eventos basados en el MARCADOR
//       (1X2, goles, BTTS) sale directo de la matriz Dixon-Coles.
//       Sin supuestos: la correlación está implícita en que ambos
//       eventos comparten el mismo marcador.
//   (B) ENTRE MERCADOS (goles↔corners↔tiros): cada uno es un Poisson
//       independiente en el modelo. Para unirlos SIN tocar sus
//       distribuciones marginales usamos una CÓPULA GAUSSIANA con
//       correlaciones FIJAS (no estimadas de los datos: con ~15
//       partidos estimarlas sería sobreajuste, el mismo motivo por el
//       que se aplazó el Poisson bivariado #7). Tuneables, y la UI
//       muestra siempre el número "independiente" al lado.
// ============================================================

// Correlaciones asumidas entre mercados (informadas por la literatura
// de fútbol, NO por los datos del usuario). Tuneables.
const MKT_CORR = {
  goals_corners: 0.30,  // partidos abiertos → más goles y más corners
  goals_shots:   0.55,  // goles muy ligados a tiros a puerta
  corners_shots: 0.45,
};

// #9 Banda de líneas "de casa de apuestas". lineSet generaba líneas bajando hasta
// ~90% de probabilidad; esas líneas demasiado SEGURAS (p.ej. "+0.5" al 98%) no las
// ofrecen las casas y estorban al leer los porcentajes. Las casas centran sus
// líneas en el valor esperado, no en los extremos. Ocultamos lo que quede fuera de
// la banda, garantizando que nunca se vacíe un mercado (mínimo las líneas centrales).
const LINE_PMAX = 0.88;  // por encima → demasiado segura, se oculta
const LINE_PMIN = 0.08;  // por debajo → demasiado improbable, se oculta

// #6 xG: peso de los Expected Goals al construir λ cuando el CSV los trae.
// Mezcla por partido: eff = XG_WEIGHT*xG + (1-XG_WEIGHT)*goles_reales.
// xG es mejor predictor del futuro (menos ruido que el gol bruto), pero el
// gol real captura la definición/efectividad. 0 = puro goles (como antes),
// 1 = puro xG. Si el CSV no trae xG, este peso no se usa (cae a goles).
const XG_WEIGHT = 0.7;

// #8 PPDA (passes per defensive action): mide la PRESIÓN del equipo. MENOR PPDA
// = presiona más arriba → fuerza más pérdidas, más córners y más tiros. Es señal
// nueva (no sale de los goles), así que mejora córners/tiros sin sobreajustar.
// Opcional por fila: si el CSV no trae PPDA, no influye.
const PPDA_LEAGUE   = 11;    // PPDA de referencia (media típica de ligas top)
const PPDA_MAX_BOOST = 0.15; // tope del efecto presión sobre córners/tiros: ±15%

// #8 xGOT (xG on target): xG contando SOLO los tiros a puerta. Es mejor predictor
// de goles que el xG normal (descarta los disparos desviados). Cuando el CSV trae
// xGOT, pesa XGOT_WEIGHT frente al xG dentro de la señal de calidad que alimenta λ.
const XGOT_WEIGHT = 0.6;     // peso de xGOT vs xG cuando ambos están presentes

// #8 Factores de CONTEXTO para tarjetas (no salen del histórico del equipo;
// dependen del árbitro y de la naturaleza del partido). Todos opcionales/togglables.
const REF_WEIGHT        = 0.40; // peso del promedio del árbitro frente al histórico
const CLASICO_CARD_MULT = 1.25; // clásico/derbi → +25% tarjetas
const KNOCKOUT_CARD_MULT= 1.10; // eliminatoria → +10% tarjetas (más tensión)
const MUSTWIN_CARD_MULT = 1.08; // por cada equipo obligado a ganar → +8% tarjetas
const MUSTWIN_ATTACK_MULT=1.08; // equipo obligado a ganar ataca más → +8% córners/tiros

// erf y normal estándar (Abramowitz-Stegun 7.1.26, error ~1e-7)
function erf(x) {
  const t = 1 / (1 + 0.3275911 * Math.abs(x));
  const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x);
  return x >= 0 ? y : -y;
}
function normCDF(x) { return 0.5 * (1 + erf(x / Math.SQRT2)); }

// Inversa de la normal estándar (Acklam, error ~1e-9)
function normInv(p) {
  if (p <= 0) return -Infinity;
  if (p >= 1) return Infinity;
  const a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00];
  const b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01, -1.328068155288572e+01];
  const c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00];
  const d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00];
  const plow = 0.02425, phigh = 1 - plow;
  let q, r;
  if (p < plow) { q = Math.sqrt(-2 * Math.log(p)); return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1); }
  if (p <= phigh) { q = p - 0.5; r = q * q; return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1); }
  q = Math.sqrt(-2 * Math.log(1 - p)); return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
}

// CDF normal bivariada Φ₂(h,k;ρ) por la identidad de Plackett:
//   Φ₂(h,k;ρ) = Φ(h)Φ(k) + ∫₀^ρ φ₂(h,k;t) dt   (Simpson, 64 nodos)
// Verificable: Φ₂(0,0;ρ) = 1/4 + asin(ρ)/(2π).
function biNormPdf(h, k, t) {
  const t2 = 1 - t * t;
  if (t2 <= 1e-12) return 0;
  return Math.exp(-(h * h - 2 * t * h * k + k * k) / (2 * t2)) / (2 * Math.PI * Math.sqrt(t2));
}
function biNormCDF(h, k, r) {
  if (h === Infinity) return normCDF(k);
  if (k === Infinity) return normCDF(h);
  if (h === -Infinity || k === -Infinity) return 0;
  const base = normCDF(h) * normCDF(k);
  if (Math.abs(r) < 1e-9) return base;
  const N = 64, dx = r / N;
  let s = biNormPdf(h, k, 0) + biNormPdf(h, k, r);
  for (let i = 1; i < N; i++) s += (i % 2 ? 4 : 2) * biNormPdf(h, k, i * dx);
  return Math.max(0, Math.min(1, base + (dx / 3) * s));
}

// P(X>thrX, Y>thrY) vía cópula gaussiana. Fx, Fy = CDF marginal en el
// umbral (P(X≤thr)); las marginales NO se modifican, solo se acoplan.
function jointOverOver(Fx, Fy, rho) {
  const clamp = v => Math.min(1 - 1e-9, Math.max(1e-9, v));
  const fx = clamp(Fx), fy = clamp(Fy);
  const both = 1 - fx - fy + biNormCDF(normInv(fx), normInv(fy), rho);
  return Math.max(0, Math.min(1, both));
}

// Genera matriz de probabilidades de marcadores (hasta maxG goles cada)
function scoreMatrix(lam1, lam2, maxG = 7) {
  const mat = [];
  for (let h = 0; h <= maxG; h++) {
    mat[h] = [];
    for (let a = 0; a <= maxG; a++) {
      mat[h][a] = poissonP(lam1, h) * poissonP(lam2, a);
    }
  }
  return mat;
}

// ---- Dixon-Coles correction ----
// Corrige la sobreestimación de Poisson en marcadores bajos (0-0, 1-0, 0-1, 1-1)
// ρ = -0.13 es el valor empírico calibrado en miles de partidos de fútbol profesional.
// Se usa como fallback cuando no hay suficientes datos para estimar ρ dinámicamente.
const DC_RHO = -0.13;
function dcTau(h, a, lam1, lam2, rho) {
  if (h === 0 && a === 0) return 1 - lam1 * lam2 * rho;
  if (h === 1 && a === 0) return 1 + lam2 * rho;
  if (h === 0 && a === 1) return 1 + lam1 * rho;
  if (h === 1 && a === 1) return 1 - rho;
  return 1; // marcadores con ≥2 goles totales no se corrigen
}
function applyDixonColes(mat, lam1, lam2, rho = DC_RHO) {
  const corrected = mat.map((row, h) =>
    row.map((p, a) => Math.max(0, p * dcTau(h, a, lam1, lam2, rho)))
  );
  // Renormalizar para que la suma de probabilidades sea exactamente 1
  const total = corrected.reduce((s, row) => s + row.reduce((sr, p) => sr + p, 0), 0);
  return corrected.map(row => row.map(p => p / total));
}

// ---- #4: Estimación dinámica de ρ desde los datos observados ----
// Compara los 0-0 reales del historial de ambos equipos contra los que
// el Poisson esperaría con sus λ. Si hay MÁS 0-0 de lo esperado, los goles
// están más correlacionados negativamente → ρ más negativo.
// Requiere ≥20 partidos combinados para ser fiable; si no, usa el ρ fijo.
// (Antes 10: con tan pocos, la tasa de 0-0 histórica —jugada contra rivales con
// otras λ— sesgaba ρ sistemáticamente. Umbral subido para reducir ese ruido.)
function estimateRho(s1, s2, lam1, lam2) {
  const gf1 = s1.gfArr || [], gc1 = s1.gcArr || [];
  const gf2 = s2.gfArr || [], gc2 = s2.gcArr || [];
  const n = gf1.length + gf2.length;
  if (n < 20) return { rho: DC_RHO, dynamic: false, n };

  // Cuenta de empates 0-0 observados en el historial de ambos equipos
  let obs00 = 0;
  for (let i = 0; i < gf1.length; i++) if (gf1[i] === 0 && gc1[i] === 0) obs00++;
  for (let i = 0; i < gf2.length; i++) if (gf2[i] === 0 && gc2[i] === 0) obs00++;
  const obsRate = obs00 / n;

  // 0-0 esperado por Poisson independiente con los λ del enfrentamiento
  const expRate = poissonP(lam1, 0) * poissonP(lam2, 0);
  if (expRate <= 0) return { rho: DC_RHO, dynamic: false, n };

  // Si obs > exp → más 0-0 de lo esperado → ρ más negativo.
  // Escalamos el ρ base por el ratio, con clamp para evitar valores extremos.
  const ratio = obsRate / expRate;
  let rho = -0.13 * ratio;
  rho = Math.max(-0.20, Math.min(0, rho)); // entre -0.20 y 0
  return { rho, dynamic: true, n, obsRate, expRate };
}

// ============================================================
//  ESTADÍSTICAS
// ============================================================
function get(r, k) { return +(r[k]) || 0; }

function parseSede(val) {
  const v = String(val||'').trim().toLowerCase();
  if (v === '0' || v === '0.0' || v === 'neutral' || v === 'neutro') return 'neutral';
  if (v === 'local' || v === 'home' || v === '1' || v === 'casa') return 'local';
  if (v === 'visitante' || v === 'away' || v === 'visita' || v === '2') return 'away';
  return 'neutral';
}

function computeStats(rows) {
  const n = rows.length;
  _curW = dateWeights(rows); // pesos por fecha si todas las filas la traen (null → índice)
  const res  = rows.map(r => r.resultado || '');
  const sede = rows.map(r => parseSede(r.sede));
  const gf  = rows.map(r => get(r,'goles_f'));
  const gc  = rows.map(r => get(r,'goles_c'));
  const g1f = rows.map(r => get(r,'goles_1t_f'));
  const g1c = rows.map(r => get(r,'goles_1t_c'));
  // Goles 2ª parte: usar el dato del CSV si la columna existe (incluso si es 0).
  // Solo si la columna falta del todo, derivar como total − 1ª parte.
  // (Antes usaba ||, que tomaba un 0 real como "ausente" y lo sobrescribía → bug.)
  const has2tF = rows.map(r => r.goles_2t_f !== undefined && r.goles_2t_f !== '' && r.goles_2t_f !== null);
  const has2tC = rows.map(r => r.goles_2t_c !== undefined && r.goles_2t_c !== '' && r.goles_2t_c !== null);
  const g2f = rows.map((r,i) => has2tF[i] ? get(r,'goles_2t_f') : Math.max(0, gf[i]-g1f[i]));
  const g2c = rows.map((r,i) => has2tC[i] ? get(r,'goles_2t_c') : Math.max(0, gc[i]-g1c[i]));

  // ---- #6 xG (Expected Goals) — detección automática ----
  // Solo donde la fila trae xg_f / xg_c se mezcla con el gol real; el resto
  // usa el gol bruto. effGF/effGC alimentan SOLO el λ (medias y splits de
  // sede, momentum, ventaja local). Los histogramas de eventos reales (BTTS,
  // portería a cero, conteo de 0-0 para ρ) siguen usando goles reales.
  const hasXgF = rows.map(r => r.xg_f !== undefined && r.xg_f !== '' && r.xg_f !== null);
  const hasXgC = rows.map(r => r.xg_c !== undefined && r.xg_c !== '' && r.xg_c !== null);
  const hasXG  = hasXgF.some(Boolean) || hasXgC.some(Boolean);
  const xgf = rows.map((r,i) => hasXgF[i] ? get(r,'xg_f') : gf[i]);
  const xgc = rows.map((r,i) => hasXgC[i] ? get(r,'xg_c') : gc[i]);

  // #8 xGOT (xG a puerta): opcional por fila. Mejor predictor de goles que el xG
  // normal. Construimos una SEÑAL DE CALIDAD q por partido: si hay xGOT y xG, q
  // = XGOT_WEIGHT*xGOT + (1-XGOT_WEIGHT)*xG; si solo hay uno, usa ese; si no hay
  // ninguno, q = null y se cae al gol real. q sustituye al xG dentro del blend de λ.
  const hasXgotF = rows.map(r => r.xgot_f !== undefined && r.xgot_f !== '' && r.xgot_f !== null);
  const hasXgotC = rows.map(r => r.xgot_c !== undefined && r.xgot_c !== '' && r.xgot_c !== null);
  const hasXGOT  = hasXgotF.some(Boolean) || hasXgotC.some(Boolean);
  const xgotf = rows.map((r,i) => hasXgotF[i] ? get(r,'xgot_f') : null);
  const xgotc = rows.map((r,i) => hasXgotC[i] ? get(r,'xgot_c') : null);
  const qF = rows.map((r,i) => {
    if (hasXgotF[i] && hasXgF[i]) return XGOT_WEIGHT*xgotf[i] + (1-XGOT_WEIGHT)*xgf[i];
    if (hasXgotF[i]) return xgotf[i];
    if (hasXgF[i])   return xgf[i];
    return null;
  });
  const qC = rows.map((r,i) => {
    if (hasXgotC[i] && hasXgC[i]) return XGOT_WEIGHT*xgotc[i] + (1-XGOT_WEIGHT)*xgc[i];
    if (hasXgotC[i]) return xgotc[i];
    if (hasXgC[i])   return xgc[i];
    return null;
  });
  const effGF = rows.map((r,i) => qF[i] !== null ? XG_WEIGHT*qF[i] + (1-XG_WEIGHT)*gf[i] : gf[i]);
  const effGC = rows.map((r,i) => qC[i] !== null ? XG_WEIGHT*qC[i] + (1-XG_WEIGHT)*gc[i] : gc[i]);
  const wXGF = hasXG ? wavg(xgf) : null;  // xG puro ponderado (solo display)
  const wXGA = hasXG ? wavg(xgc) : null;
  const wXGOTF = wavgMasked(xgotf, hasXgotF); // xGOT puro ponderado (solo display)
  const wXGOTA = wavgMasked(xgotc, hasXgotC);

  // #8 PPDA (presión): opcional por fila. Promedio ponderado solo de las filas
  // con dato; null si no hay ninguna → pressMult() devolverá 1 (no influye).
  const hasPpdaF = rows.map(r => r.ppda_f !== undefined && r.ppda_f !== '' && r.ppda_f !== null);
  const hasPpdaC = rows.map(r => r.ppda_c !== undefined && r.ppda_c !== '' && r.ppda_c !== null);
  const hasPPDA  = hasPpdaF.some(Boolean) || hasPpdaC.some(Boolean);
  const wPPDA_f = wavgMasked(rows.map(r=>get(r,'ppda_f')), hasPpdaF);
  const wPPDA_c = wavgMasked(rows.map(r=>get(r,'ppda_c')), hasPpdaC);
  const nPPDA_f = hasPpdaF.filter(Boolean).length; // muestras con dato (shrinkage)
  const nPPDA_c = hasPpdaC.filter(Boolean).length;
  const tiros   = rows.map(r => get(r,'tiros'));
  const tirosR  = rows.map(r => get(r,'tiros_rival'));
  const tp      = rows.map(r => get(r,'tiros_puerta') || Math.round(get(r,'tiros')*0.38));
  const tpR     = rows.map(r => get(r,'tiros_puerta_rival') || Math.round(get(r,'tiros_rival')*0.38));
  const corners  = rows.map(r => get(r,'corners'));
  const cornersR = rows.map(r => get(r,'corners_rival'));
  const ta   = rows.map(r => get(r,'tarjetas_a'));
  const tr   = rows.map(r => get(r,'tarjetas_r'));
  const asist = rows.map(r => get(r,'asistencias'));

  // ---- Calidad de rivales (ranking FIFA) por fila ----
  const rivalRanks = rows.map(r => {
    const rival = (r.rival || '').trim();
    const found = lookupFIFA(rival);
    return found ? found.rank : FIFA_UNKNOWN_RANK;
  });
  const rivalKnown = rows.map(r => !!lookupFIFA((r.rival || '').trim()));
  // Fuerza del rival: rank 1 → 1.0, rank FIFA_MAX_RANK → 0.0
  const rivalStrength = rivalRanks.map(rk => (FIFA_MAX_RANK - rk) / FIFA_MAX_RANK);

  // ---- #3 NORMALIZACIÓN POR RIVAL FILA A FILA ----
  // Antes, wGF/wGC promediaban goles sin importar contra quién, y se parcheaba
  // DESPUÉS con scheduleStrength + perfFactor a nivel agregado (redundantes
  // entre sí y con el factor FIFA). Ahora cada fila se ajusta por la fuerza del
  // rival DE ESA FILA antes de promediar: meter 3 a un colista vale menos;
  // encajar 2 del líder pesa menos.
  //   adjGF = effGF / (1 + OPP_ADJ·(0.5 − fuerza_rival))  → gol vs débil se descuenta
  //   adjGC = effGC / (1 + OPP_ADJ·(fuerza_rival − 0.5))  → encajar vs fuerte se perdona
  // Solo se ajustan filas con rival RECONOCIDO en el ranking (clubs/desconocidos
  // → ×1: ajustar con un rank inventado desplazaría el nivel de TODO el equipo).
  const OPP_ADJ = 0.6;
  const oppClamp = v => Math.min(1.3, Math.max(0.7, v));
  const oppDefF = rivalStrength.map((rs,i) => rivalKnown[i] ? oppClamp(1 + OPP_ADJ*(0.5 - rs)) : 1);
  const oppAtkF = rivalStrength.map((rs,i) => rivalKnown[i] ? oppClamp(1 + OPP_ADJ*(rs - 0.5)) : 1);
  const adjGF = effGF.map((v,i) => v / oppDefF[i]);
  const adjGC = effGC.map((v,i) => v / oppAtkF[i]);
  const oppAdjusted = rivalKnown.some(Boolean);

  // Ponderados temporalmente
  const wGF  = wavg(adjGF);   // efectivo: xG↔gol real, normalizado por rival
  const wGC  = wavg(adjGC);
  const wG1F = wavg(g1f);
  const wG1C = wavg(g1c);
  const wG2F = wavg(g2f);
  const wG2C = wavg(g2c);
  const wTP  = wavg(tp);
  const wTPR = wavg(tpR);
  const wTiros  = wavg(tiros);
  const wTirosR = wavg(tirosR);
  const wCorners  = wavg(corners);
  const wCornersR = wavg(cornersR);
  const wTA   = wavg(ta);
  const wTR   = wavg(tr);
  const wAsist = wavg(asist);
  const wCornersTotal = wCorners + wCornersR;
  const wTirosTotal   = wTiros + wTirosR;
  const wTPTotal      = wTP + wTPR;

  // Tasas ponderadas para Poisson
  const wins   = wpct(res, r => r === 'W');
  const draws  = wpct(res, r => r === 'D');
  const losses = wpct(res, r => r === 'L');

  const w = weights(n);
  // Varianzas ponderadas de TOTALES por partido (para binomial negativa)
  const varCornersTot = wvar(rows.map((_,i) => corners[i] + cornersR[i]));
  const varTPTot      = wvar(rows.map((_,i) => tp[i] + tpR[i]));
  const varTirosTot   = wvar(rows.map((_,i) => tiros[i] + tirosR[i]));
  const varCardsOwn   = wvar(rows.map((_,i) => ta[i] + tr[i]));
  const wBttsV  = rows.reduce((s,_,i) => s + w[i]*(gf[i]>0&&gc[i]>0?1:0), 0);
  const wOver25 = rows.reduce((s,_,i) => s + w[i]*(gf[i]+gc[i]>2.5?1:0), 0);
  const wBtts1T = rows.reduce((s,_,i) => s + w[i]*(g1f[i]>0&&g1c[i]>0?1:0), 0);
  const wBtts2T = rows.reduce((s,_,i) => s + w[i]*(g2f[i]>0&&g2c[i]>0?1:0), 0);
  const wGoalIn1T = rows.reduce((s,_,i) => s + w[i]*((g1f[i]>0||g1c[i]>0)?1:0), 0);
  const wGoalIn2T = rows.reduce((s,_,i) => s + w[i]*((g2f[i]>0||g2c[i]>0)?1:0), 0);
  const wWinsAnyHalf = rows.reduce((s,_,i) => s + w[i]*((g1f[i]>g1c[i]||g2f[i]>g2c[i])?1:0), 0);
  const wCleanSheet  = rows.reduce((s,_,i) => s + w[i]*(gc[i]===0?1:0), 0);
  const wWinCS = rows.reduce((s,_,i) => s + w[i]*(gf[i]>gc[i]&&gc[i]===0?1:0), 0);
  const wScoredFirst1T = rows.reduce((s,_,i) => s + w[i]*(g1f[i]>0?1:0), 0);

  // ---- Calidad de rivales: índice de calendario (solo display) ----
  // scheduleStrength y perfFactor YA NO entran en λ (los sustituyó la
  // normalización por rival fila a fila, arriba). Se mantienen para la UI.
  // Calendario ponderado: promedio de fuerza de rivales (ponderado temporalmente)
  const scheduleStrength = rows.reduce((s,_,i) => s + w[i]*rivalStrength[i], 0);
  // Factor de ajuste de rendimiento:
  // victorias vs rivales fuertes valen más, derrotas vs débiles penalizan más
  const perfFactor = rows.reduce((s,r,i) => {
    const rs = rivalStrength[i];
    const result = r.resultado || '';
    let bonus = 0;
    if (result === 'W') bonus =  0.3 * rs;       // ganar a rival fuerte → bonus
    if (result === 'L') bonus = -0.3 * (1 - rs);  // perder con rival débil → penaliza
    return s + w[i] * bonus;
  }, 0);
  // scheduleStrength: 0 = rivales muy débiles, 1 = todos top-1
  // perfFactor: positivo = buen rendimiento ajustado, negativo = malo

  // Sede breakdown — count and weighted avg GF per context
  const nLocal   = sede.filter(s => s==='local').length;
  const nAway    = sede.filter(s => s==='away').length;
  const nNeutral = sede.filter(s => s==='neutral').length;

  // Weighted avg goals at home vs away vs neutral (for empirical home advantage)
  const localIdx   = rows.map((_,i) => sede[i]==='local'   ? i : -1).filter(i=>i>=0);
  const awayIdx    = rows.map((_,i) => sede[i]==='away'    ? i : -1).filter(i=>i>=0);
  const neutralIdx = rows.map((_,i) => sede[i]==='neutral' ? i : -1).filter(i=>i>=0);

  const sedeAvgGF = ctx => {
    if (!ctx.length) return null;
    const sub = ctx.map(i => adjGF[i]);
    return sub.reduce((a,b)=>a+b,0)/sub.length;
  };
  const avgGF_local   = sedeAvgGF(localIdx);
  const avgGF_away    = sedeAvgGF(awayIdx);
  const avgGF_neutral = sedeAvgGF(neutralIdx);

  // Ventaja local empírica vs visitante. Fallback 1.10 si faltan datos.
  // ATENUACIÓN: se comprime el factor hacia 1 (HOME_ADV_WEIGHT) para restarle
  // peso a la localía — el efecto bruto del historial suele sobreestimarla.
  const HOME_ADV_WEIGHT = 0.6; // 60% del efecto observado (0 = sin ventaja, 1 = bruto)
  // Piso 0.85 (antes 1.0): un equipo que rinde PEOR en casa existe y debe reflejarse;
  // el clamp en 1.0 imponía sesgo pro-local sistemático.
  const attenuate = (raw, cap) => {
    const clamped = Math.min(cap, Math.max(0.85, raw));
    return 1 + (clamped - 1) * HOME_ADV_WEIGHT; // tira hacia 1
  };
  let empiricalHomeAdv = 1.10;
  if (avgGF_local !== null && avgGF_away !== null && avgGF_away > 0) {
    empiricalHomeAdv = attenuate(avgGF_local / avgGF_away, 1.5);
  } else if (avgGF_local !== null && avgGF_neutral !== null && avgGF_neutral > 0) {
    empiricalHomeAdv = attenuate(avgGF_local / avgGF_neutral, 1.4);
  }

  // ---- Split local/visitante con ponderación temporal + REGRESIÓN POR MUESTRA ----
  // Problema: con pocos partidos de una sede (4-7), el promedio de esa sede es
  // muy ruidoso y produce valores extremos. Solución: mezclar el promedio de la
  // sede con el promedio general según cuántos partidos haya en esa sede.
  // peso_split = n / (n + K). Con K=6: 4 partidos→40%, 8→57%, 15→71% de confianza
  // en el split; el resto tira hacia el promedio general (estable).
  const SPLIT_SHRINK_K = 6;
  const calcContextWavg = (idxArr, valArr, generalAvg) => {
    if (idxArr.length < 4) return null; // muy pocos: usar promedio general (null = fallback)
    const sub = idxArr.map(i => valArr[i]);
    const sw = idxArr.map((origI) => _curW ? _curW[origI] : Math.exp(-origI * DECAY));
    const swSum = sw.reduce((a,b)=>a+b,0);
    const splitAvg = sub.reduce((s,v,j) => s + (sw[j]/swSum)*v, 0);
    // Regresión hacia el promedio general según tamaño de muestra de la sede
    const wSplit = idxArr.length / (idxArr.length + SPLIT_SHRINK_K);
    return splitAvg * wSplit + generalAvg * (1 - wSplit);
  };

  const wGF_local   = calcContextWavg(localIdx,   adjGF, wGF);
  const wGC_local   = calcContextWavg(localIdx,   adjGC, wGC);
  const wGF_away    = calcContextWavg(awayIdx,     adjGF, wGF);
  const wGC_away    = calcContextWavg(awayIdx,     adjGC, wGC);
  const wGF_neutral = calcContextWavg(neutralIdx,  adjGF, wGF);
  const wGC_neutral = calcContextWavg(neutralIdx,  adjGC, wGC);

  // ---- Detección de tendencia (momentum) ----
  // Comparar promedio de últimos 5 partidos vs partidos 6-10
  const trendOf = (arr) => {
    if (arr.length < 6) return 1; // no hay suficiente historia
    const avg5  = arr.slice(0, 5).reduce((a,b)=>a+b,0) / 5;
    const end   = Math.min(arr.length, 10);
    const avg10 = arr.slice(5, end).reduce((a,b)=>a+b,0) / (end - 5);
    if (avg5 <= 0 || avg10 <= 0) return 1;
    return Math.min(1.20, Math.max(0.85, avg5 / avg10));
  };
  const trendGF = trendOf(adjGF);  // >1 → equipo mete más goles (xG) que antes
  const trendGC = trendOf(adjGC);  // >1 → equipo recibe más goles (xG) que antes

  // ---- Tiros a puerta: split por sede + momentum (misma maquinaria que goles) ----
  const wTP_local   = calcContextWavg(localIdx,   tp,   wTP);
  const wTPR_local  = calcContextWavg(localIdx,   tpR,  wTPR);
  const wTP_away    = calcContextWavg(awayIdx,    tp,   wTP);
  const wTPR_away   = calcContextWavg(awayIdx,    tpR,  wTPR);
  const wTP_neutral = calcContextWavg(neutralIdx, tp,   wTP);
  const wTPR_neutral= calcContextWavg(neutralIdx, tpR,  wTPR);
  const trendTP = trendOf(tp); // >1 → equipo genera más tiros a puerta que antes

  // ---- Corners: split por sede + momentum (misma maquinaria) ----
  const wCorners_local   = calcContextWavg(localIdx,   corners,  wCorners);
  const wCornersR_local  = calcContextWavg(localIdx,   cornersR, wCornersR);
  const wCorners_away    = calcContextWavg(awayIdx,    corners,  wCorners);
  const wCornersR_away   = calcContextWavg(awayIdx,    cornersR, wCornersR);
  const wCorners_neutral = calcContextWavg(neutralIdx, corners,  wCorners);
  const wCornersR_neutral= calcContextWavg(neutralIdx, cornersR, wCornersR);
  const trendCorners = trendOf(corners);

  const _statsW = _curW; _curW = null; // liberar pesos por fecha (fin del cómputo)
  return {
    n, wins, draws, losses,
    wGF, wGC, wG1F, wG1C, wG2F, wG2C,
    hasXG, wXGF, wXGA,
    hasXGOT, wXGOTF, wXGOTA,
    hasPPDA, wPPDA_f, wPPDA_c, nPPDA_f, nPPDA_c,
    varCornersTot, varTPTot, varTirosTot, varCardsOwn,
    dateWeighted: !!_statsW, oppAdjusted,
    wTP, wTPR, wTiros, wTirosR,
    wCorners, wCornersR, wCornersTotal,
    wTirosTotal, wTPTotal,
    wTA, wTR, wAsist,
    wBttsV, wOver25, wBtts1T, wBtts2T,
    wGoalIn1T, wGoalIn2T,
    wWinsAnyHalf, wCleanSheet, wWinCS, wScoredFirst1T,
    nLocal, nAway, nNeutral, empiricalHomeAdv,
    avgGF_local, avgGF_away, avgGF_neutral,
    wGF_local, wGC_local, wGF_away, wGC_away, wGF_neutral, wGC_neutral,
    trendGF, trendGC,
    wTP_local, wTPR_local, wTP_away, wTPR_away, wTP_neutral, wTPR_neutral, trendTP,
    wCorners_local, wCornersR_local, wCorners_away, wCornersR_away, wCorners_neutral, wCornersR_neutral, trendCorners,
    tpArr: tp, tirosArr: tiros, gfArr: gf, gcArr: gc,
    form: res.slice(0, 5),
    scheduleStrength, perfFactor, rivalRanks,
    rivalNames: rows.map(r => (r.rival||'').trim()),
    unmatchedRivals: [...new Set(
      rows.map(r => (r.rival||'').trim()).filter(name => name && !lookupFIFA(name))
    )]
  };
}

// ============================================================
//  MODELO PRINCIPAL — Poisson doble
//  λ1 = ataque local × defensa visitante × ventaja local
//  λ2 = ataque visitante × defensa local
//  Ventaja local calibrada: promedio histórico ~1.35 pero
//  ajustado por los datos de los propios equipos
// ============================================================
function buildModel(s1, s2) {
  // ---- Regresión a la media (prior bayesiano) ----
  // Con pocas muestras tiramos hacia el promedio de ambos equipos
  // PRIOR_WEIGHT = 1 con 0 partidos, 0 con 20+ partidos
  const PRIOR_WEIGHT_1 = Math.max(0, 1 - s1.n / 20);
  const PRIOR_WEIGHT_2 = Math.max(0, 1 - s2.n / 20);
  const priorGF = (s1.wGF + s2.wGF) / 2;
  const priorGC = (s1.wGC + s2.wGC) / 2;

  // GF/GC suavizados (con regresión a la media)
  const smoothGF1 = s1.wGF * (1 - PRIOR_WEIGHT_1) + priorGF * PRIOR_WEIGHT_1;
  const smoothGC1 = s1.wGC * (1 - PRIOR_WEIGHT_1) + priorGC * PRIOR_WEIGHT_1;
  const smoothGF2 = s2.wGF * (1 - PRIOR_WEIGHT_2) + priorGF * PRIOR_WEIGHT_2;
  const smoothGC2 = s2.wGC * (1 - PRIOR_WEIGHT_2) + priorGC * PRIOR_WEIGHT_2;

  // ---- Split local/visitante (o neutral) ----
  // Partido normal: lam1 usa stats de LOCAL del equipo 1, lam2 las de VISITANTE del 2.
  //
  // Partido NEUTRAL: cancha neutral = ni el bonus de jugar en casa ni el castigo de
  // jugar fuera. La mejor estimación es el PUNTO MEDIO entre lo que el equipo hace de
  // local y lo que hace de visitante: (wGF_local + wGF_away) / 2. Esto neutraliza el
  // sesgo de cuántos partidos de local/visitante tiene cada equipo (que contamina el
  // promedio general) y refleja físicamente lo que es una cancha neutral.
  // Si falta el split de una sede, cae al promedio general suavizado.
  // NO se usa wGF_neutral: con 4-6 partidos (finales/mundiales vs rivales atípicos)
  // es la muestra más ruidosa posible y causaba que el favorito se invirtiera.
  const neutralCtx = (vLocal, vAway, smooth, pw) => {
    if (vLocal !== null && vAway !== null) {
      const mid = (vLocal + vAway) / 2;        // punto medio sede
      return mid * (1 - pw) + smooth * pw;     // regresión a la media por muestra
    }
    return smooth; // sin split fiable → promedio general
  };

  let gf1_context, gc1_context, gf2_context, gc2_context;
  if (neutralVenue) {
    gf1_context = neutralCtx(s1.wGF_local, s1.wGF_away, smoothGF1, PRIOR_WEIGHT_1);
    gc1_context = neutralCtx(s1.wGC_local, s1.wGC_away, smoothGC1, PRIOR_WEIGHT_1);
    gf2_context = neutralCtx(s2.wGF_local, s2.wGF_away, smoothGF2, PRIOR_WEIGHT_2);
    gc2_context = neutralCtx(s2.wGC_local, s2.wGC_away, smoothGC2, PRIOR_WEIGHT_2);
  } else {
    gf1_context = s1.wGF_local !== null
      ? s1.wGF_local * (1 - PRIOR_WEIGHT_1) + smoothGF1 * PRIOR_WEIGHT_1
      : smoothGF1;
    gc1_context = s1.wGC_local !== null
      ? s1.wGC_local * (1 - PRIOR_WEIGHT_1) + smoothGC1 * PRIOR_WEIGHT_1
      : smoothGC1;
    gf2_context = s2.wGF_away !== null
      ? s2.wGF_away * (1 - PRIOR_WEIGHT_2) + smoothGF2 * PRIOR_WEIGHT_2
      : smoothGF2;
    gc2_context = s2.wGC_away !== null
      ? s2.wGC_away * (1 - PRIOR_WEIGHT_2) + smoothGC2 * PRIOR_WEIGHT_2
      : smoothGC2;
  }

  // Media de la liga (aproximación de referencia)
  const lgAvg = (gf1_context + gf2_context + gc1_context + gc2_context) / 4;
  const safeAvg = Math.max(0.5, lgAvg);

  // Fuerza de ataque / defensa relativa a la media
  const atkH = gf1_context / safeAvg;
  const defH = gc1_context / safeAvg;
  const atkA = gf2_context / safeAvg;
  const defA = gc2_context / safeAvg;

  // Ventaja local. En modo normal, lam1 YA usa las stats de local del equipo (que
  // incluyen el efecto de jugar en casa), así que aplicar empiricalHomeAdv completo
  // contaría la localía dos veces. Aplicamos solo un RESIDUAL suave (la mitad del
  // efecto que excede 1), para no duplicar. En cancha neutral no hay ventaja (=1).
  const rawAdv = s1.empiricalHomeAdv || 1.10;
  const homeAdv = neutralVenue ? 1 : (1 + (rawAdv - 1) * 0.5);

  // Ajuste por ranking FIFA del ENFRENTAMIENTO (prior de calidad entre los dos
  // equipos de HOY). Peso bajado 0.35 → 0.25: la normalización por rival ya
  // corrige la calidad del calendario en las tasas; mantenerlo alto doble-contaría.
  const FIFA_WEIGHT = 0.25;
  const MAX_TEAMS = FIFA_MAX_RANK;
  const _lookup1 = lookupFIFA(names.team1);
  const _lookup2 = lookupFIFA(names.team2);
  const rank1 = _lookup1 ? _lookup1.rank : null;
  const rank2 = _lookup2 ? _lookup2.rank : null;
  let fifaFactor1 = 1.0, fifaFactor2 = 1.0;
  if (rank1 !== null && rank2 !== null) {
    const str1 = (MAX_TEAMS - rank1) / MAX_TEAMS;
    const str2 = (MAX_TEAMS - rank2) / MAX_TEAMS;
    const avg  = (str1 + str2) / 2 || 0.5;
    const rel1 = avg > 0 ? str1 / avg : 1;
    const rel2 = avg > 0 ? str2 / avg : 1;
    fifaFactor1 = 1 + FIFA_WEIGHT * (rel1 - 1);
    fifaFactor2 = 1 + FIFA_WEIGHT * (rel2 - 1);
  }

  // #3: scheduleStrength y perfFactor ELIMINADOS de λ — su función la cumple
  // ahora la normalización por rival fila a fila dentro de computeStats
  // (adjGF/adjGC), sin apilar tres factores que medían lo mismo.

  // ---- Momentum (tendencia de últimos 5 vs 5 anteriores) ----
  const TREND_WEIGHT = 0.10;
  const trendFactor1 = 1 + TREND_WEIGHT * (s1.trendGF - 1); // ataque local mejorando/empeorando
  const trendFactor2 = 1 + TREND_WEIGHT * (s2.trendGF - 1); // ataque visitante
  // Clamp entre 0.85 y 1.20
  const tf1 = Math.min(1.20, Math.max(0.85, trendFactor1));
  const tf2 = Math.min(1.20, Math.max(0.85, trendFactor2));

  const lam1 = Math.max(0.3, atkH * defA * safeAvg * homeAdv * fifaFactor1 * tf1);
  const lam2 = Math.max(0.3, atkA * defH * safeAvg * fifaFactor2 * tf2);

  // Matriz de marcadores base (Poisson)
  const mat = scoreMatrix(lam1, lam2, 7);

  // #4: estimar ρ dinámicamente desde el historial; fallback a -0.13 si <10 partidos
  const rhoEst = estimateRho(s1, s2, lam1, lam2);

  // Aplicar corrección Dixon-Coles para marcadores bajos con ρ dinámico
  const matDC = applyDixonColes(mat, lam1, lam2, rhoEst.rho);

  // 1X2 desde la matriz corregida
  let pH = 0, pD = 0, pA = 0;
  for (let h = 0; h <= 7; h++) {
    for (let a = 0; a <= 7; a++) {
      const p = matDC[h][a];
      if (h > a) pH += p;
      else if (h === a) pD += p;
      else pA += p;
    }
  }

  // Over/under desde la matriz corregida (más preciso que Poisson simple)
  const lamTotal = lam1 + lam2;
  const overFromMatrix = (threshold) => {
    let cum = 0;
    for (let h = 0; h <= 7; h++)
      for (let a = 0; a <= 7; a++)
        if (h + a <= threshold) cum += matDC[h][a];
    return Math.max(0, 1 - cum);
  };
  const over15 = overFromMatrix(1);
  const over25 = overFromMatrix(2);
  const over35 = overFromMatrix(3);
  const over45 = overFromMatrix(4);

  // BTTS desde la matriz corregida
  // P(BTTS) = 1 - P(lam1=0) - P(lam2=0) + P(0-0)
  const p00   = matDC[0][0];
  const pLam1Zero = matDC[0].reduce((s, p) => s + p, 0);       // fila h=0
  const pLam2Zero = matDC.reduce((s, row) => s + row[0], 0);   // columna a=0
  const btts  = Math.max(0, 1 - pLam1Zero - pLam2Zero + p00);

  return { lam1, lam2, lamTotal, pH, pD, pA, over15, over25, over35, over45, btts, p00, mat: matDC,
           trendGF1: s1.trendGF, trendGF2: s2.trendGF,
           rho: rhoEst.rho, rhoDynamic: rhoEst.dynamic, rhoN: rhoEst.n,
           neutral: neutralVenue,
           usedXG: !!(s1.hasXG || s2.hasXG),
           usedXGOT: !!(s1.hasXGOT || s2.hasXGOT),
           usedPPDA: !!(s1.hasPPDA || s2.hasPPDA),
           wXGF1: s1.wXGF, wXGA1: s1.wXGA, wXGF2: s2.wXGF, wXGA2: s2.wXGA,
           contextUsed1: neutralVenue ? 'neutral' : (s1.wGF_local !== null ? 'local' : 'general'),
           contextUsed2: neutralVenue ? 'neutral' : (s2.wGF_away !== null ? 'away' : 'general') };
}

// ============================================================
//  PRIMER GOL — distribución normalizada y exclusiva
// ============================================================
function firstGoalProbs(model) {
  // P(home scores first) ∝ lam1 / (lam1 + lam2) × P(no 0-0)
  const noGoal = model.p00;
  const scored = 1 - noGoal;
  const shareH = model.lam1 / (model.lam1 + model.lam2);
  const shareA = model.lam2 / (model.lam1 + model.lam2);
  return {
    home:   scored * shareH,
    away:   scored * shareA,
    nogoal: noGoal
  };
}

// "Gana al menos una mitad" DERIVADO DEL MODELO del partido (no del histórico
// aislado, que ignoraba al rival y contradecía el 1X2).
// Un equipo gana la mitad si mete más goles que el rival en esa mitad.
// Reparto de λ por mitad: ~44% primera, ~56% segunda (patrón típico).
function winAnyHalfProbs(model) {
  const halfWinProb = (lamFor, lamAgainst) => {
    // P(equipo gana esta mitad) = Σ P(mete h) P(rival mete a) sobre h>a
    let pWin = 0;
    for (let h = 0; h <= 6; h++)
      for (let a = 0; a < h; a++)
        pWin += poissonP(lamFor, h) * poissonP(lamAgainst, a);
    return pWin;
  };
  const calc = (lamF, lamA) => {
    const f1 = lamF * 0.44, a1 = lamA * 0.44; // primera mitad
    const f2 = lamF * 0.56, a2 = lamA * 0.56; // segunda mitad
    const w1 = halfWinProb(f1, a1);
    const w2 = halfWinProb(f2, a2);
    // Gana al menos una = 1 − P(no gana ninguna). Mitades ~independientes.
    return 1 - (1 - w1) * (1 - w2);
  };
  return {
    home: calc(model.lam1, model.lam2),
    away: calc(model.lam2, model.lam1)
  };
}

// ============================================================
//  CORNERS — línea dinámica
// ============================================================
// ============================================================
//  CORNERS — modelo completo (consistente con goles y tiros)
//  Cruza los corners que genera cada equipo con los que concede
//  el rival, con regresión a la media, momentum y modo neutral.
// ============================================================
function expectedCorners(s1, s2) {
  // Selección por sede: atk = corners que fuerza el equipo, def = corners que concede
  const pick = (s, role) => {
    if (neutralVenue) {
      // Cancha neutral = punto medio local/visitante. NO usamos wCorners_neutral
      // (pocos partidos neutrales = ruido).
      const atk = (s.wCorners_local !== null && s.wCorners_away !== null) ? (s.wCorners_local + s.wCorners_away)/2 : s.wCorners;
      const def = (s.wCornersR_local !== null && s.wCornersR_away !== null) ? (s.wCornersR_local + s.wCornersR_away)/2 : s.wCornersR;
      return { atk, def };
    }
    if (role === 'home') {
      return { atk: s.wCorners_local !== null ? s.wCorners_local : s.wCorners,
               def: s.wCornersR_local !== null ? s.wCornersR_local : s.wCornersR };
    }
    return { atk: s.wCorners_away !== null ? s.wCorners_away : s.wCorners,
             def: s.wCornersR_away !== null ? s.wCornersR_away : s.wCornersR };
  };

  const a1 = pick(s1, 'home');
  const a2 = pick(s2, 'away');

  // Regresión a la media
  const PW1 = Math.max(0, 1 - s1.n / 20);
  const PW2 = Math.max(0, 1 - s2.n / 20);
  const priorAtk = (a1.atk + a2.atk) / 2;
  const priorDef = (a1.def + a2.def) / 2;
  const atk1 = a1.atk*(1-PW1) + priorAtk*PW1;
  const def1 = a1.def*(1-PW1) + priorDef*PW1;
  const atk2 = a2.atk*(1-PW2) + priorAtk*PW2;
  const def2 = a2.def*(1-PW2) + priorDef*PW2;

  // Cruce ataque-mío × defensa-rival
  const leagueAvg = Math.max(1, (atk1 + atk2 + def1 + def2) / 4);
  let exp1 = (atk1 / leagueAvg) * (def2 / leagueAvg) * leagueAvg;
  let exp2 = (atk2 / leagueAvg) * (def1 / leagueAvg) * leagueAvg;

  // Ventaja local (residual suave, no en neutral) — evita doble conteo.
  // Piso 0.9: permite reflejar equipos que rinden peor en casa.
  if (!neutralVenue) {
    const rawAdv = Math.min(1.25, Math.max(0.9, s1.empiricalHomeAdv || 1.1));
    exp1 *= 1 + (rawAdv - 1) * 0.5;
  }

  // Momentum de corners
  const tf1 = Math.min(1.20, Math.max(0.85, 1 + 0.10 * ((s1.trendCorners || 1) - 1)));
  const tf2 = Math.min(1.20, Math.max(0.85, 1 + 0.10 * ((s2.trendCorners || 1) - 1)));
  exp1 = Math.max(0.5, exp1 * tf1);
  exp2 = Math.max(0.5, exp2 * tf2);

  // #8 Presión (PPDA) con SHRINKAGE por muestra + señal del rival:
  // combina lo que el equipo presiona (ppda_f propio) con la presión que su
  // rival SUFRE habitualmente (ppda_c del rival = PPDA de quienes lo enfrentan).
  // Media de ambas señales cuando existen → un solo multiplicador, sin doble conteo.
  exp1 *= pressCross(s1.wPPDA_f, s1.nPPDA_f, s2.wPPDA_c, s2.nPPDA_c);
  exp2 *= pressCross(s2.wPPDA_f, s2.nPPDA_f, s1.wPPDA_c, s1.nPPDA_c);

  // #8 Obligación de ganar: el equipo que necesita ganar sí o sí empuja más → más córners.
  if (mustWin1) exp1 *= MUSTWIN_ATTACK_MULT;
  if (mustWin2) exp2 *= MUSTWIN_ATTACK_MULT;

  return { exp1, exp2, total: exp1 + exp2,
           trend1: s1.trendCorners || 1, trend2: s2.trendCorners || 1,
           ctx1: neutralVenue ? 'neutral' : (s1.wCorners_local !== null ? 'local' : 'general'),
           ctx2: neutralVenue ? 'neutral' : (s2.wCorners_away  !== null ? 'away'  : 'general') };
}

function cornerProbs(s1, s2) {
  const ec = expectedCorners(s1, s2);
  const mu = ec.total; // total de corners esperados del partido (ya cruzado con defensas)
  // Sobredispersión empírica (Fano = var/media del histórico de totales de cada
  // equipo, promediado) trasladada al mu del partido → binomial negativa.
  const fano = cornersFano(s1, s2);
  const varr = mu * fano;
  const base = Math.round(mu);
  const line1 = base - 0.5;
  const line2 = base + 0.5;
  const pOver1 = nbOver(mu, varr, base - 1); // P(X > base-0.5)
  const pOver2 = nbOver(mu, varr, base);     // P(X > base+0.5)
  return { mu, varr, line1, line2, pOver1, pOver2,
           exp1: ec.exp1, exp2: ec.exp2,
           trend1: ec.trend1, trend2: ec.trend2, ctx1: ec.ctx1, ctx2: ec.ctx2 };
}
// Fano factor (var/media) del total de córners, promediado entre equipos.
// ≥1 con clamp [1, 3] — si la muestra da <1 (posible con pocas filas) usamos
// Poisson (fano=1) para no INFRAdispersar sin evidencia sólida.
function cornersFano(s1, s2) {
  const f = [];
  if (s1.wCornersTotal > 0 && s1.varCornersTot != null) f.push(s1.varCornersTot / s1.wCornersTotal);
  if (s2.wCornersTotal > 0 && s2.varCornersTot != null) f.push(s2.varCornersTot / s2.wCornersTotal);
  if (!f.length) return 1;
  return Math.min(3, Math.max(1, f.reduce((a,b)=>a+b,0) / f.length));
}

// ============================================================
//  TARJETAS — línea dinámica
// ============================================================
function cardProbs(s1, s2) {
  // Base: tarjetas esperadas totales del partido desde el histórico de ambos equipos.
  let mu = s1.wTA + s1.wTR + s2.wTA + s2.wTR;
  const muBase = Math.max(0.1, mu);
  // Fano empírico: var/media de las tarjetas propias por partido, sumadas entre
  // equipos (var_total ≈ var1+var2 bajo independencia). Tarjetas es el mercado
  // MÁS sobredisperso — Poisson subestimaba las colas. Clamp [1, 3.5].
  const varBase = (s1.varCardsOwn || 0) + (s2.varCardsOwn || 0);
  const fano = Math.min(3.5, Math.max(1, varBase > 0 ? varBase / muBase : 1));
  const factors = [];

  // #8 Árbitro: si se introduce su promedio de tarjetas/partido, se mezcla hacia él.
  // El árbitro es el factor más predictivo de tarjetas, por eso pesa REF_WEIGHT.
  if (refAvgCards > 0) {
    mu = REF_WEIGHT * refAvgCards + (1 - REF_WEIGHT) * mu;
    factors.push(`árbitro ${fmt(refAvgCards)}/p`);
  }
  // #8 Clásico / derbi: rivalidad → más entradas, más tarjetas.
  if (isClasico)  { mu *= CLASICO_CARD_MULT;  factors.push(`clásico ×${CLASICO_CARD_MULT}`); }
  // #8 Eliminatoria: a partido único / a vida o muerte → más tensión.
  if (isKnockout) { mu *= KNOCKOUT_CARD_MULT; factors.push(`eliminatoria ×${KNOCKOUT_CARD_MULT}`); }
  // #8 Obligación de ganar: un equipo desesperado por ganar comete más faltas.
  if (mustWin1)   { mu *= MUSTWIN_CARD_MULT;  factors.push(`${names.team1} debe ganar`); }
  if (mustWin2)   { mu *= MUSTWIN_CARD_MULT;  factors.push(`${names.team2} debe ganar`); }

  const base = Math.round(mu);
  const line1 = base - 0.5;
  const line2 = base + 0.5;
  // La varianza escala con mu (Fano constante): los factores de contexto suben
  // la media y la dispersión proporcionalmente.
  const varr = mu * fano;
  const pOver1 = nbOver(mu, varr, base - 1);
  const pOver2 = nbOver(mu, varr, base);
  return { mu, varr, fano, line1, line2, pOver1, pOver2, factors };
}

// ============================================================
//  TIROS A PUERTA — modelo completo (consistente con el de goles)
//  Cruza la capacidad ofensiva propia (tiros que genera) con la
//  capacidad defensiva del rival (tiros que concede), aplica
//  regresión a la media, momentum y respeta el modo cancha neutral.
// ============================================================
function expectedShots(s1, s2) {
  // --- Selección de stats por sede (split local/visitante/neutral) ---
  // Ataque = tiros a puerta que genera el equipo; Defensa = tiros que concede (wTPR)
  const pick = (s, role) => {
    // role: 'home' (equipo 1, de local), 'away' (equipo 2, de visitante)
    if (neutralVenue) {
      // Cancha neutral = punto medio local/visitante (ni bonus de casa ni castigo
      // de fuera). NO usamos wTP_neutral: con pocos partidos neutrales es ruidoso.
      const atk = (s.wTP_local !== null && s.wTP_away !== null) ? (s.wTP_local + s.wTP_away)/2 : s.wTP;
      const def = (s.wTPR_local !== null && s.wTPR_away !== null) ? (s.wTPR_local + s.wTPR_away)/2 : s.wTPR;
      return { atk, def };
    }
    if (role === 'home') {
      return { atk: s.wTP_local !== null ? s.wTP_local : s.wTP,
               def: s.wTPR_local !== null ? s.wTPR_local : s.wTPR };
    }
    return { atk: s.wTP_away !== null ? s.wTP_away : s.wTP,
             def: s.wTPR_away !== null ? s.wTPR_away : s.wTPR };
  };

  const a1 = pick(s1, 'home');
  const a2 = pick(s2, 'away');

  // --- Regresión a la media (mismo shrinkage que en goles) ---
  const PW1 = Math.max(0, 1 - s1.n / 20);
  const PW2 = Math.max(0, 1 - s2.n / 20);
  const priorAtk = (a1.atk + a2.atk) / 2;   // tiros a puerta medios del enfrentamiento
  const priorDef = (a1.def + a2.def) / 2;
  const atk1 = a1.atk*(1-PW1) + priorAtk*PW1;
  const def1 = a1.def*(1-PW1) + priorDef*PW1;
  const atk2 = a2.atk*(1-PW2) + priorAtk*PW2;
  const def2 = a2.def*(1-PW2) + priorDef*PW2;

  // --- Cruce ataque-mío × defensa-rival, relativo a la media de la liga ---
  // El nivel base de tiros a puerta esperados en este partido
  const leagueAvg = Math.max(1, (atk1 + atk2 + def1 + def2) / 4);
  // exp1 = cuánto genera el equipo 1 ponderado por cuánto concede el equipo 2
  let exp1 = (atk1 / leagueAvg) * (def2 / leagueAvg) * leagueAvg;
  let exp2 = (atk2 / leagueAvg) * (def1 / leagueAvg) * leagueAvg;

  // --- Ventaja local (residual suave, no en neutral) ---
  // Piso 0.9: permite reflejar equipos que rinden peor en casa.
  if (!neutralVenue) {
    const rawAdv = Math.min(1.25, Math.max(0.9, s1.empiricalHomeAdv || 1.1));
    exp1 *= 1 + (rawAdv - 1) * 0.5;
  }

  // --- Momentum (tendencia de tiros a puerta, clamp 0.85–1.20) ---
  const tf1 = Math.min(1.20, Math.max(0.85, 1 + 0.10 * ((s1.trendTP || 1) - 1)));
  const tf2 = Math.min(1.20, Math.max(0.85, 1 + 0.10 * ((s2.trendTP || 1) - 1)));
  exp1 *= tf1;
  exp2 *= tf2;

  // #8 Presión (PPDA) con shrinkage + señal del rival (ver pressCross).
  exp1 *= pressCross(s1.wPPDA_f, s1.nPPDA_f, s2.wPPDA_c, s2.nPPDA_c);
  exp2 *= pressCross(s2.wPPDA_f, s2.nPPDA_f, s1.wPPDA_c, s1.nPPDA_c);

  // #8 Obligación de ganar: el equipo presionado a ganar dispara más.
  if (mustWin1) exp1 *= MUSTWIN_ATTACK_MULT;
  if (mustWin2) exp2 *= MUSTWIN_ATTACK_MULT;

  exp1 = Math.max(0.5, exp1);
  exp2 = Math.max(0.5, exp2);

  return { exp1, exp2, trend1: s1.trendTP || 1, trend2: s2.trendTP || 1,
           ctx1: neutralVenue ? 'neutral' : (s1.wTP_local !== null ? 'local' : 'general'),
           ctx2: neutralVenue ? 'neutral' : (s2.wTP_away  !== null ? 'away'  : 'general') };
}

function shotProbs(s1, s2) {
  const { exp1, exp2 } = expectedShots(s1, s2);
  const total = exp1 + exp2;
  return { home: exp1/total, away: exp2/total, exp1, exp2 };
}

// ============================================================
//  HELPERS DE RENDER
// ============================================================
function pct(v) { return Math.round(Math.max(0, Math.min(1, v)) * 100); }
function fmt(v) { return (+v).toFixed(1); }
function fmt2(v) { return (+v).toFixed(2); }
function confClass(p) { return p > 0.60 ? 'high' : p > 0.42 ? 'medium' : 'low'; }
function confLabel(p) { return p > 0.60 ? 'Alta' : p > 0.42 ? 'Media' : 'Baja'; }
function oddStr(p) { return p > 0 ? (1/p).toFixed(2) : '—'; }

// Registro en memoria de apuestas marcadas como "ya hechas".
// Los checks pertenecen al ENFRENTAMIENTO ACTUAL: si cambian los equipos
// (o su historial), se reinician solos. La "firma" identifica el partido.
let betChecked = new Set();
let betOdds = {};          // nombre de apuesta → cuota introducida (para EV/ROI)
let betCheckSignature = '';

function matchupSignature() {
  const n1 = (state.team1 || []).length;
  const n2 = (state.team2 || []).length;
  return `${names.team1}__${names.team2}__${n1}__${n2}`;
}

// Si la firma del partido cambió, descarta los checks del partido anterior.
function syncBetChecks() {
  const sig = matchupSignature();
  if (sig !== betCheckSignature) {
    betChecked = new Set();
    betOdds = {};
    betCheckSignature = sig;
  }
}

function toggleBetCheck(key) {
  if (betChecked.has(key)) betChecked.delete(key);
  else betChecked.add(key);
}
function setBetOdds(key, v) {
  const n = parseFloat(String(v).replace(',', '.'));
  if (!isNaN(n) && n > 1) betOdds[key] = n; else delete betOdds[key];
}

function betCard(name, desc, prob) {
  prob = Math.min(0.97, Math.max(0.03, prob));
  const cc = confClass(prob), cl = confLabel(prob);
  const key = name.replace(/"/g, '&quot;');
  const esc = key.replace(/'/g, "\\'");
  const isChecked = betChecked.has(name);
  // #4 Prob. ajustada por calibración histórica (por mercado si hay registros)
  const mkt = marketOfBet(name);
  const adj = calibrateProb(prob, mkt);
  const showAdj = adj != null && Math.abs(adj - prob) >= 0.02;
  const oddsVal = betOdds[name];
  // EV si hay cuota: usa la prob ajustada cuando existe (mejor estimación)
  const evP = showAdj ? adj : prob;
  const ev = oddsVal ? (evP * oddsVal - 1) : null;
  return `<div class="bet-card ${cc}${isChecked ? ' bet-done' : ''}">
    <div class="bet-top">
      <div class="bet-name">${name}</div>
      <div class="bet-conf ${cc}">Confianza ${cl}</div>
    </div>
    <div class="bet-desc">${desc}</div>
    <div class="bet-bar-bg"><div class="bet-bar-fill ${cc}" style="width:${pct(prob)}%"></div></div>
    <div class="bet-footer">
      <span class="bet-prob">Probabilidad: <strong>${pct(prob)}%</strong>${showAdj ? ` <span class="bet-adj" title="Ajustada con tu historial de calibración${mkt ? ` (mercado: ${mkt})` : ' (ajuste global)'}: según tus registros, el modelo ${adj<prob?'sobrestima':'subestima'} en esta zona de probabilidad">· ajust. ${pct(adj)}%</span>` : ''}</span>
      <label class="bet-check" onclick="event.stopPropagation()">
        <input type="checkbox" ${isChecked ? 'checked' : ''} onchange="toggleBetCheck('${esc}');this.closest('.bet-card').classList.toggle('bet-done',this.checked)">
        <span class="bet-check-box"></span>
        <span class="bet-check-label">Apuesta hecha</span>
      </label>
    </div>
    <div class="bet-oddsrow" onclick="event.stopPropagation()">
      <label>Cuota</label>
      <input class="bet-odds" type="number" step="0.01" min="1.01" placeholder="ej. 1.85" value="${oddsVal || ''}"
        onchange="setBetOdds('${esc}', this.value); const c=this.closest('.bet-card'); c.querySelector('.bet-ev').textContent = betEvText('${esc}', ${evP.toFixed(4)}); c.querySelector('.bet-kelly').textContent = betKellyText('${esc}', ${evP.toFixed(4)})">
      <span class="bet-ev" title="Valor esperado por unidad apostada: prob × cuota − 1. Positivo = apuesta con valor.">${ev != null ? evTxt(ev) : ''}</span>
      <span class="bet-kelly" title="Stake sugerido: Kelly 1/4 (más conservador que Kelly completo, absorbe el error de estimación del modelo), con tope duro de 5% de la banca.">${ev != null ? kellyTxt(kellyStake(evP, oddsVal)) : ''}</span>
    </div>
  </div>`;
}
function evTxt(ev) {
  const s = (ev >= 0 ? '+' : '') + Math.round(ev * 100) + '% EV';
  return ev >= 0.03 ? '🟢 ' + s : ev <= -0.03 ? '🔴 ' + s : '🟡 ' + s;
}
function betEvText(key, p) {
  const o = betOdds[key];
  return o ? evTxt(p * o - 1) : '';
}

// --- v10: staking sugerido (Kelly 1/4, tope 5% del bankroll) ---
// f* = (p·(cuota-1) − (1-p)) / (cuota-1)  →  Kelly completo
// Se usa 1/4 de Kelly (más conservador: absorbe el error de estimación
// del modelo) y se pone un tope duro de 5% para proteger el bankroll
// aunque la fórmula sugiera más.
const KELLY_FRACTION = 0.25;
const KELLY_CAP = 0.05;
function kellyStake(p, odds) {
  if (!odds || odds <= 1) return null;
  const b = odds - 1;
  const fFull = (p * b - (1 - p)) / b;
  if (fFull <= 0) return 0; // sin valor: no apostar
  return Math.min(KELLY_CAP, fFull * KELLY_FRACTION);
}
function kellyTxt(stake) {
  if (stake == null) return '';
  if (stake <= 0) return '⚪ sin valor';
  const capped = stake >= KELLY_CAP - 1e-9;
  return `💰 ${(stake * 100).toFixed(1)}% banca${capped ? ' (tope)' : ''}`;
}
function betKellyText(key, p) {
  const o = betOdds[key];
  return o ? kellyTxt(kellyStake(p, o)) : '';
}

function formDot(r) {
  const c = {W:'var(--accent)', D:'var(--warn)', L:'var(--bad)'};
  return `<span style="width:16px;height:16px;border-radius:50%;background:${c[r]||'var(--text-3)'};display:inline-flex;align-items:center;justify-content:center;font-size:8px;font-weight:700;color:var(--bg-0)">${r}</span>`;
}

function miniBar(arr, color) {
  const mx = Math.max(...arr, 1);
  return `<div class="mini-chart">${arr.slice(0,15).map(v =>
    `<div class="bar" style="background:${color};height:${Math.max(3,Math.round(v/mx*36))}px;opacity:.75"></div>`
  ).join('')}</div>`;
}

function matchHeader(model, s1, s2) {
  return `<div class="match-header">
    <div class="match-teams">
      <div class="mteam">${names.team1}</div><div class="vs">VS</div><div class="mteam">${names.team2}</div>
    </div>
    <label class="neutral-toggle" title="Actívalo para finales, Mundiales o cualquier partido en sede única: no se aplica ventaja local a ningún equipo.">
      <input type="checkbox" id="neutral-checkbox" ${model.neutral ? 'checked' : ''} onchange="toggleNeutral(this.checked)">
      <span class="neutral-slider"></span>
      <span class="neutral-label">⚪ Cancha neutral ${model.neutral ? '<strong style="color:var(--purple)">(activa)</strong>' : ''}</span>
    </label>
    ${ctxControls()}
    <div style="font-size:11px;color:var(--text-2);margin-bottom:8px">
      Goles esperados: ${names.team1} <strong style="color:var(--home-dim)">${fmt2(model.lam1)}</strong> · ${names.team2} <strong style="color:var(--away-dim)">${fmt2(model.lam2)}</strong>
      ${model.neutral ? '<span style="color:var(--purple);margin-left:6px">· sin ventaja local</span>' : `<span style="color:var(--text-2);margin-left:6px">· ${names.team1} con ventaja local ×${fmt(s1.empiricalHomeAdv||1.15)}</span>`}
    </div>
    ${(()=>{
      const _l1 = lookupFIFA(names.team1), _l2 = lookupFIFA(names.team2);
      const r1 = _l1 ? _l1.rank : null, r2 = _l2 ? _l2.rank : null;
      if (!r1 && !r2) return '';
      const badge = (name, rank, color) => rank
        ? `<span style="background:var(--bg-2);border:1px solid var(--line);border-radius:20px;padding:2px 10px;font-size:11px;color:${color};margin:0 4px">
            ${name} <strong>#${rank}</strong> FIFA
           </span>`
        : `<span style="font-size:11px;color:var(--text-2);margin:0 4px">${name} (sin ranking)</span>`;
      return `<div style="margin-bottom:8px">${badge(names.team1,r1,'var(--home-dim)')}${badge(names.team2,r2,'var(--away-dim)')}</div>`;
    })()}
    <div class="probs-bar">
      <div class="prob-h" style="width:${pct(model.pH)}%"></div>
      <div class="prob-d" style="width:${pct(model.pD)}%"></div>
      <div class="prob-a" style="width:${pct(model.pA)}%"></div>
    </div>
    <div class="prob-labels">
      <div class="prob-label-h">${names.team1} ${pct(model.pH)}%</div>
      <div class="prob-label-d">Empate ${pct(model.pD)}%</div>
      <div class="prob-label-a">${names.team2} ${pct(model.pA)}%</div>
    </div>
    <div><span class="model-tag">Poisson + Dixon-Coles (ρ=${model.rho.toFixed(3)}${model.rhoDynamic ? ' dinámico' : ' fijo'}) · ${model.neutral ? 'sede neutral' : 'split local/visitante'} · momentum${model.usedXG ? ` · <strong style="color:var(--accent)">xG ${Math.round(XG_WEIGHT*100)}%</strong>` : ''}${model.usedXGOT ? ` · <strong style="color:var(--accent)">xGOT</strong>` : ''}${model.usedPPDA ? ` · <strong style="color:var(--accent)">PPDA</strong>` : ''} · ${s1.n} p/equipo</span></div>
    ${(()=>{
      const f = [];
      if (refAvgCards > 0) f.push(`🧑‍⚖️ árbitro ${fmt(refAvgCards)} tarj./p`);
      if (isClasico)  f.push('🔥 clásico');
      if (isKnockout) f.push('🏆 eliminatoria');
      if (mustWin1)   f.push(`⚠️ ${names.team1} debe ganar`);
      if (mustWin2)   f.push(`⚠️ ${names.team2} debe ganar`);
      if (!f.length) return '';
      return `<div style="font-size:10px;color:var(--accent-dim);margin-top:4px">Contexto activo: ${f.join(' · ')}</div>`;
    })()}
    ${(()=>{
      const tArrow = t => t > 1.05 ? '↑' : t < 0.95 ? '↓' : '→';
      const tColor = t => t > 1.05 ? 'var(--accent)' : t < 0.95 ? 'var(--bad)' : 'var(--text-2)';
      const ctx1 = model.contextUsed1 === 'neutral' ? '⚪neutral' : model.contextUsed1 === 'local' ? '🏠casa' : '📊gral';
      const ctx2 = model.contextUsed2 === 'neutral' ? '⚪neutral' : model.contextUsed2 === 'away'  ? '✈️visita' : '📊gral';
      return `<div style="font-size:10px;color:var(--text-2);margin-top:4px">
        ${names.team1}: λ desde ${ctx1} · momentum <span style="color:${tColor(model.trendGF1)}">${tArrow(model.trendGF1)}</span>
        &nbsp;·&nbsp;
        ${names.team2}: λ desde ${ctx2} · momentum <span style="color:${tColor(model.trendGF2)}">${tArrow(model.trendGF2)}</span>
      </div>`;
    })()}
  </div>`;
}

// ============================================================
//  RENDER PRINCIPAL
// ============================================================
function toggleNeutral(on) {
  neutralVenue = !!on;
  renderAll();
}

// #8 Panel de contexto del partido (afecta tarjetas; la obligación de ganar
// también empuja córners/tiros). Se re-renderiza en cada renderAll, así que lee
// el estado global. El input numérico usa onchange (al salir) para no perder foco.
function ctxControls() {
  const mwVal = (mustWin1 && mustWin2) ? 'both' : mustWin1 ? '1' : mustWin2 ? '2' : '';
  const chip = (on, label) => on
    ? `<strong style="color:var(--accent)">${label}</strong>` : label;
  return `<div class="ctx-controls" title="Contexto del partido: ajusta sobre todo las tarjetas. La obligación de ganar también aumenta córners y tiros del equipo presionado.">
    <div class="ctx-row">
      <label class="ctx-item" title="Promedio de tarjetas por partido del árbitro designado. Es el factor más predictivo de tarjetas. Déjalo vacío si no lo sabes.">
        🧑‍⚖️ <span>Árbitro tarj./p</span>
        <input type="number" min="0" step="0.1" id="ctx-ref" placeholder="—"
          value="${refAvgCards > 0 ? refAvgCards : ''}" onchange="setRefCards(this.value)">
      </label>
      <label class="ctx-item ctx-check" title="Clásico o derbi: rivalidad histórica → más tarjetas.">
        <input type="checkbox" id="ctx-clasico" ${isClasico ? 'checked' : ''} onchange="toggleClasico(this.checked)">
        <span>${chip(isClasico, '🔥 Clásico')}</span>
      </label>
      <label class="ctx-item ctx-check" title="Partido de eliminatoria / a vida o muerte → más tensión y tarjetas.">
        <input type="checkbox" id="ctx-knockout" ${isKnockout ? 'checked' : ''} onchange="toggleKnockout(this.checked)">
        <span>${chip(isKnockout, '🏆 Eliminatoria')}</span>
      </label>
    </div>
    <div class="ctx-row">
      <label class="ctx-item ctx-mustwin" title="¿Algún equipo necesita ganar sí o sí para no quedar eliminado? (p. ej. 3ª jornada de fase de grupos). Aumenta sus córners, tiros y las tarjetas del partido.">
        ⚠️ <span>Necesita ganar</span>
        <select id="ctx-mustwin" onchange="setMustWin(this.value)">
          <option value="" ${mwVal===''?'selected':''}>Ninguno</option>
          <option value="1" ${mwVal==='1'?'selected':''}>${names.team1}</option>
          <option value="2" ${mwVal==='2'?'selected':''}>${names.team2}</option>
          <option value="both" ${mwVal==='both'?'selected':''}>Ambos</option>
        </select>
      </label>
    </div>
  </div>`;
}

function setRefCards(v) {
  const n = parseFloat(v);
  refAvgCards = (v === '' || isNaN(n) || n < 0) ? 0 : n;
  renderAll();
}
function toggleClasico(on)  { isClasico  = !!on; renderAll(); }
function toggleKnockout(on) { isKnockout = !!on; renderAll(); }
function setMustWin(val) {
  mustWin1 = (val === '1' || val === 'both');
  mustWin2 = (val === '2' || val === 'both');
  renderAll();
}

function renderAll() {
  syncBetChecks(); // reinicia los checks si cambió el enfrentamiento
  const s1 = computeStats(state.team1);
  const s2 = computeStats(state.team2);
  const model = buildModel(s1, s2);
  renderAnalysis(s1, s2, model);
  renderBets(s1, s2, model);
  renderHistory();
  renderValidation();
  saveSession(); // guardar enfrentamiento actual para la próxima sesión
}

// ---- ANÁLISIS ----
function renderAnalysis(s1, s2, model) {
  const el = document.getElementById('analysis-content');
  el.className = '';
  // Build warning panel for unmatched rivals
  const buildWarnings = (s, teamName) => {
    if (!s.unmatchedRivals || s.unmatchedRivals.length === 0) return '';
    return `<div class="warning-box">
      <div class="warning-title">⚠️ Rivales no encontrados en ranking FIFA — <strong>${teamName}</strong></div>
      <div class="warning-desc">Estos nombres no coinciden con ningún país del top 120. Se tratan como #130 (rival débil). Verifica la ortografía en tu CSV.</div>
      <div class="warning-pills">
        ${s.unmatchedRivals.map(name =>
          `<span class="warning-pill">${name}</span>`
        ).join('')}
      </div>
      <div class="warning-hint">💡 El sistema ya ignora tildes y mayúsculas automáticamente. Si ves este aviso, es probable que el nombre esté en otro idioma o tenga una ortografía muy diferente. Nombres oficiales: "Países Bajos" · "Estados Unidos" · "Corea del Sur" · "República Democrática del Congo"</div>
    </div>`;
  };

  el.innerHTML = `
  <div class="loaded-badge">✅ ${s1.n} partidos analizados por equipo · ponderación temporal activa</div>
  ${buildWarnings(s1, names.team1)}
  ${buildWarnings(s2, names.team2)}
  ${matchHeader(model, s1, s2)}
  <div class="poisson-info">
    <strong>📊 ¿Qué significan estos números?</strong><br>
    Las probabilidades se calculan analizando el historial reciente de ambos equipos: cuántos goles meten, cuántos reciben, si juegan mejor en casa o de visitante, y si están en buen momento de forma. Los últimos 5 partidos tienen el mayor peso en el modelo. Los datos de xG (Expected Goals), cuando están disponibles, mejoran la precisión de la predicción.
  </div>
  <div class="teams-grid">
    ${teamCardHTML(s1, names.team1, 'var(--home)', model.lam1)}
    ${teamCardHTML(s2, names.team2, 'var(--away)', model.lam2)}
  </div>

  <div class="bets-section-title" style="margin-top:24px">🥅 Detalle de tiros</div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
    ${shotsStatCard(s1, names.team1, 'var(--home)', expectedShots(s1,s2).exp1)}
    ${shotsStatCard(s2, names.team2, 'var(--away)', expectedShots(s1,s2).exp2)}
  </div>

  <div class="bets-section-title" style="margin-top:24px">⏱️ Detalle por mitades</div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
    ${halfTeamCard(s1, names.team1)}
    ${halfTeamCard(s2, names.team2)}
  </div>`;
}

// Tarjeta de estadísticas de tiros por equipo (movida desde la pestaña Tiros)
function shotsStatCard(s, name, color, expShots) {
  return `<div class="team-card"><h3>${name} — tiros</h3>
    <div class="stat-row"><span class="stat-label">Tiros totales/p (pond.)</span><span class="stat-val">${fmt(s.wTiros)}</span></div>
    <div class="stat-row"><span class="stat-label">Tiros a puerta/p (histórico)</span><span class="stat-val">${fmt(s.wTP)}</span></div>
    <div class="stat-row"><span class="stat-label">A puerta esperados (este partido)</span><span class="stat-val green">${fmt(expShots)}</span></div>
    <div class="stat-row"><span class="stat-label">Precisión (a puerta/totales)</span><span class="stat-val">${fmt(s.wTiros>0?s.wTP/s.wTiros*100:0)}%</span></div>
    <div class="stat-row"><span class="stat-label">Tiros rival recibidos/p</span><span class="stat-val red">${fmt(s.wTPR)}</span></div>
    <div style="font-size:10px;color:var(--text-0);margin-top:8px">Tiros a puerta por partido (recientes →)</div>
    ${miniBar(s.tpArr, color)}
  </div>`;
}

function teamCardHTML(s, name, color, lam) {
  const tArrow = t => t > 1.05 ? '↑' : t < 0.95 ? '↓' : '→';
  const tColor = t => t > 1.05 ? 'var(--accent)' : t < 0.95 ? 'var(--bad)' : 'var(--text-2)';
  const tLabel = t => t > 1.05 ? 'Mejorando' : t < 0.95 ? 'Bajando' : 'Estable';
  return `<div class="team-card">
    <h3>${name}</h3>
    <div style="display:flex;gap:6px;margin-bottom:10px">
      ${s.form.map(r => formDot(r)).join('')}
      <span style="font-size:10px;color:var(--text-3);align-self:center;margin-left:4px">Últimos ${s.form.length}</span>
      <span style="font-size:10px;align-self:center;margin-left:6px;color:${tColor(s.trendGF)};font-weight:700" title="Tendencia goles últimos 5 vs anteriores">${tArrow(s.trendGF)} ${tLabel(s.trendGF)}</span>
    </div>
    <div class="stat-row"><span class="stat-label">Contexto partidos</span><span class="stat-val">🏠${s.nLocal} · ✈️${s.nAway} · ⚪${s.nNeutral} neutros</span></div>
    <div class="stat-row"><span class="stat-label">Ventaja local (empírica)</span><span class="stat-val ${s.empiricalHomeAdv>1.15?'green':'yellow'}">×${fmt(s.empiricalHomeAdv)}</span></div>
    <div class="stat-row"><span class="stat-label">Victorias (ponderado)</span><span class="stat-val green">${pct(s.wins)}%</span></div>
    <div class="stat-row"><span class="stat-label">Empates</span><span class="stat-val yellow">${pct(s.draws)}%</span></div>
    <div class="stat-row"><span class="stat-label">Derrotas</span><span class="stat-val red">${pct(s.losses)}%</span></div>
    <div class="stat-row"><span class="stat-label">Goles/p (pond.)</span><span class="stat-val">${fmt(s.wGF)} ↑ · ${fmt(s.wGC)} ↓</span></div>
    ${s.wGF_local !== null ? `<div class="stat-row"><span class="stat-label" style="color:var(--text-0)">↳ de local/visitante</span><span class="stat-val" style="font-size:11px">🏠${fmt(s.wGF_local)} · ✈️${s.wGF_away !== null ? fmt(s.wGF_away) : '—'}</span></div>` : ''}
    <div class="stat-row"><span class="stat-label">λ goles esperados</span><span class="stat-val" style="color:${color}">${fmt(lam)}</span></div>
    <div class="stat-row"><span class="stat-label">Goles 1T/2T</span><span class="stat-val">${fmt(s.wG1F)} / ${fmt(s.wG2F)}</span></div>
    <div class="stat-row"><span class="stat-label">Tiros a puerta/p</span><span class="stat-val">${fmt(s.wTP)}</span></div>
    <div class="stat-row"><span class="stat-label">Corners/p</span><span class="stat-val">${fmt(s.wCorners)}</span></div>
    <div class="stat-row"><span class="stat-label">Tarjetas/p</span><span class="stat-val">${fmt(s.wTA+s.wTR)}</span></div>
    <div class="stat-row"><span class="stat-label">Clean sheets</span><span class="stat-val green">${pct(s.wCleanSheet)}%</span></div>
    <div style="font-size:10px;color:var(--text-0);margin-top:8px">Tiros a puerta por partido</div>
    ${miniBar(s.tpArr, color)}
    <div style="font-size:10px;color:var(--text-0);margin-top:10px;margin-bottom:4px">Últimos rivales (ranking FIFA)</div>
    <div style="display:flex;flex-wrap:wrap;gap:3px">
      ${s.rivalNames.slice(0,15).map((name,i) => {
        const _lk = lookupFIFA(name);
        const rk = _lk ? _lk.rank : FIFA_UNKNOWN_RANK;
        const isUnknown = !_lk;
        const strength = (FIFA_MAX_RANK - rk) / FIFA_MAX_RANK;
        const bg = strength > 0.7 ? 'var(--bad-bg)' : strength > 0.4 ? 'var(--warn-bg)' : 'var(--accent-deep)';
        const col = strength > 0.7 ? 'var(--bad)' : strength > 0.4 ? 'var(--warn)' : 'var(--accent)';
        const label = isUnknown ? '??' : ('#'+rk);
        return '<span title="'+name+' — FIFA '+label+'" style="font-size:9px;padding:1px 5px;border-radius:10px;background:'+bg+';color:'+col+';border:1px solid '+col+'22">'+
          (name.length>10?name.slice(0,9)+'…':name)+' '+label+'</span>';
      }).join('')}
    </div>
    <div class="stat-row" style="margin-top:8px"><span class="stat-label">Dificultad calendario</span>
      <span class="stat-val ${s.scheduleStrength>0.55?'red':s.scheduleStrength>0.38?'yellow':'green'}">
        ${s.scheduleStrength>0.55?'Alta 🔴':s.scheduleStrength>0.38?'Media 🟡':'Baja 🟢'}
        (${Math.round(s.scheduleStrength*100)}%)
      </span>
    </div>
  </div>`;
}

// ---- APUESTAS ----
// ---- Helpers de acordeón de apuestas ----
let accordionOpen = { goles: true }; // Goles abierto por defecto; recuerda el resto en la sesión
function toggleAccordion(id) {
  accordionOpen[id] = !accordionOpen[id];
  const sec = document.getElementById('acc-' + id);
  if (sec) sec.classList.toggle('open', accordionOpen[id]);
  saveSession(); // recordar acordeones abiertos
}

// ---- Filtro por probabilidad (pestaña Apuestas) ----
let betProbFilter = null;   // null = ver mercados normales; o un umbral 0.60–0.90
let betSearchPool = [];     // se llena en cada render: todas las apuestas aplanadas
const dispProb = p => Math.min(0.97, Math.max(0.03, p)); // prob tal como se MUESTRA (clamp de betCard)

// Cuenta cuántas apuestas de una lista son de confianza alta
function countHigh(bets) {
  return bets.filter(b => confClass(dispProb(b.prob)) === 'high').length;
}

// Construye una sección desplegable. bets puede venir en subgrupos.
// subgroups: [{ title, note, bets:[{name,desc,prob}] }, ...]
function accordionSection(id, icon, name, subgroups, extraHTML) {
  const allBets = subgroups.flatMap(g => g.bets || []);
  // Alimentar el buscador por probabilidad con todas las apuestas reales.
  // Conservamos el subgrupo (g.title) como "subdivisión" para el menú en cascada.
  subgroups.forEach(g => (g.bets || []).forEach(b => betSearchPool.push({
    market: name, icon, sub: g.title || name, name: b.name, desc: b.desc, prob: b.prob
  })));
  const highCount = countHigh(allBets);
  const total = allBets.length;
  const isOpen = !!accordionOpen[id];
  const badge = highCount > 0
    ? `<span class="acc-high-badge">🔥 ${highCount} alta${highCount>1?'s':''}</span>`
    : `<span class="acc-high-badge none">sin alta confianza</span>`;

  const body = subgroups.map(g => {
    const sub = g.title ? `<div class="acc-subtitle">${g.title}</div>` : '';
    const note = g.note ? `<div class="acc-note">${g.note}</div>` : '';
    const cards = (g.bets && g.bets.length)
      ? `<div class="bets-grid">${g.bets.map(b => betCard(b.name, b.desc, b.prob)).join('')}</div>`
      : '';
    return sub + note + cards + (g.html || '');
  }).join('');

  return `<div class="acc-section ${isOpen?'open':''}" id="acc-${id}">
    <div class="acc-header" onclick="toggleAccordion('${id}')">
      <span class="acc-icon">${icon}</span>
      <div class="acc-titles">
        <div class="acc-name">${name}</div>
        <div class="acc-meta">${total} predicci${total!==1?'ones':'ón'}</div>
      </div>
      ${badge}
      <span class="acc-chevron">▼</span>
    </div>
    <div class="acc-body">${body}${extraHTML||''}</div>
  </div>`;
}

function renderBets(s1, s2, model) {
  const el = document.getElementById('bets-content');
  el.className = '';
  betSearchPool = []; // se rellena al construir las secciones (accordionSection)
  const winner = model.pH >= model.pA ? names.team1 : names.team2;
  const wp = Math.max(model.pH, model.pA);
  const fg = firstGoalProbs(model);
  const cp = cornerProbs(s1, s2);
  const cards = cardProbs(s1, s2);
  const sh = expectedShots(s1, s2);
  const acc1 = s1.wTiros > 0 ? Math.min(0.65, Math.max(0.25, s1.wTP / s1.wTiros)) : 0.38;
  const acc2 = s2.wTiros > 0 ? Math.min(0.65, Math.max(0.25, s2.wTP / s2.wTiros)) : 0.38;
  const shotsTot1 = sh.exp1 / acc1, shotsTot2 = sh.exp2 / acc2;
  const shotsTotal = shotsTot1 + shotsTot2;
  const csWin1 = Math.min(0.75, s1.wWinCS * 1.08);
  const csWin2 = Math.min(0.70, s2.wWinCS);

  // ---- Doble oportunidad ----
  const dc1X = model.pH + model.pD;  // local o empate
  const dc12 = model.pH + model.pA;  // local o visitante (no empate)
  const dcX2 = model.pD + model.pA;  // empate o visitante

  // ============================================================
  //  #5 COMBINADAS (correlación entre mercados)
  // ============================================================
  // (A) EXACTAS: la prob. conjunta sale de la matriz de marcadores
  //     (la correlación es la del propio marcador, sin supuestos).
  const jointMat = (pred) => {
    let p = 0;
    for (let h = 0; h <= 7; h++)
      for (let a = 0; a <= 7; a++)
        if (pred(h, a)) p += model.mat[h][a];
    return p;
  };
  const favIsHome = model.pH >= model.pA;
  const favName = favIsHome ? names.team1 : names.team2;
  const favWinMarg = favIsHome ? model.pH : model.pA;
  const favWin = favIsHome ? (h, a) => h > a : (h, a) => a > h;

  const exactCombos = [
    { name: `${favName} gana y +2.5 goles`,        note: 'partido abierto donde gana el favorito',
      indep: favWinMarg * model.over25,            prob: jointMat((h, a) => favWin(h, a) && h + a >= 3) },
    { name: `${favName} gana y −2.5 goles`,        note: 'victoria ajustada (1-0 / 2-0 / 2-1…)',
      indep: favWinMarg * (1 - model.over25),      prob: jointMat((h, a) => favWin(h, a) && h + a <= 2) },
    { name: `${favName} gana y ambos anotan`,      note: 'gana pero encaja al menos un gol',
      indep: favWinMarg * model.btts,              prob: jointMat((h, a) => favWin(h, a) && h >= 1 && a >= 1) },
    { name: `Cualquiera gana y +2.5 goles`,        note: 'sin empate y con goles',
      indep: (model.pH + model.pA) * model.over25, prob: jointMat((h, a) => h !== a && h + a >= 3) },
    { name: `Empate y −2.5 goles`,                 note: '0-0, 1-1',
      indep: model.pD * (1 - model.over25),        prob: jointMat((h, a) => h === a && h + a <= 2) },
    { name: `+2.5 goles y ambos anotan`,           note: 'festival de goles repartido',
      indep: model.over25 * model.btts,            prob: jointMat((h, a) => h + a >= 3 && h >= 1 && a >= 1) },
  ].map(c => ({ name: c.name, prob: c.prob,
    desc: `Conjunta exacta desde la matriz. Si fueran independientes: ${pct(c.indep)}%. ${c.note}.` }));

  // (B) ENTRE MERCADOS: cópula gaussiana sobre marginales sin tocar.
  const sotTotal = sh.exp1 + sh.exp2; // tiros a puerta totales esperados
  const goalsCDF = (k) => {
    let cum = 0;
    for (let h = 0; h <= 7; h++)
      for (let a = 0; a <= 7; a++)
        if (h + a <= k) cum += model.mat[h][a];
    return cum;
  };
  const poissonCDF = (mu, k) => {
    let cum = 0;
    for (let i = 0; i <= k; i++) cum += poissonP(mu, i);
    return Math.min(1, cum);
  };
  const gK = 2;                                       // over 2.5 goles
  const cK = Math.max(0, Math.round(cp.mu) - 1);      // over (cK).5 corners
  const sK = Math.max(0, Math.round(sotTotal) - 1);   // over (sK).5 tiros a puerta
  const Fg = goalsCDF(gK), Fc = poissonCDF(cp.mu, cK), Fs = poissonCDF(sotTotal, sK);

  const corrCombos = [
    { name: `+2.5 goles y +${cK}.5 corners`, rho: MKT_CORR.goals_corners,
      indep: (1 - Fg) * (1 - Fc), prob: jointOverOver(Fg, Fc, MKT_CORR.goals_corners) },
    { name: `+2.5 goles y +${sK}.5 tiros a puerta`, rho: MKT_CORR.goals_shots,
      indep: (1 - Fg) * (1 - Fs), prob: jointOverOver(Fg, Fs, MKT_CORR.goals_shots) },
    { name: `+${cK}.5 corners y +${sK}.5 tiros a puerta`, rho: MKT_CORR.corners_shots,
      indep: (1 - Fc) * (1 - Fs), prob: jointOverOver(Fc, Fs, MKT_CORR.corners_shots) },
  ].map(c => ({ name: c.name, prob: c.prob,
    desc: `Correlación asumida ρ=${fmt2(c.rho)} (no estimada de tus datos). Independiente daría ${pct(c.indep)}%.` }));

  // ---- Espectro de líneas de goles (over genérico desde la matriz) ----
  const overLine = (thr) => {
    let cum = 0;
    for (let h = 0; h <= 7; h++)
      for (let a = 0; a <= 7; a++)
        if (h + a <= thr) cum += model.mat[h][a];
    return Math.max(0, 1 - cum);
  };
  const underLine = (thr) => 1 - overLine(thr);

  // ---- Espectro de líneas para un total esperado (tiros/corners/tarjetas) ----
  // Genera líneas hacia ABAJO hasta cubrir al menos el 90% de probabilidad
  // (las apuestas "seguras") y un par hacia ARRIBA (las arriesgadas).
  const lineSet = (mu, label, baseDesc) => {
    const base = Math.round(mu);
    const lines = [];
    // Hacia abajo: desde base+2 bajando, hasta que la prob supere ~0.90
    // (y como mínimo hasta 0.5). Recogemos en orden descendente de línea.
    const top = base + 2;
    for (let k = top; k >= 0; k--) {
      const p = poissonOver(mu, k); // P(X > k+0.5) = P(X >= k+1)
      lines.push({
        name: `${label} +${k}.5`,
        desc: `${baseDesc} (esperados ~${fmt(mu)}).`,
        prob: p
      });
      // Si ya pasamos el 90% y tenemos suficientes líneas, paramos
      if (p >= 0.90 && k <= base) break;
    }
    // #9 Recortar a la banda de casa de apuestas: fuera las demasiado seguras y
    // las demasiado improbables. Si la banda deja <2 líneas, conservar las 3 más
    // cercanas al 50% (las más "apostables") para no vaciar el mercado.
    const inBand = lines.filter(l => l.prob <= LINE_PMAX && l.prob >= LINE_PMIN);
    if (inBand.length >= 2) return inBand;
    const core = [...lines].sort((a,b) => Math.abs(a.prob-0.5) - Math.abs(b.prob-0.5)).slice(0,3);
    return core.sort((a,b) => a.prob - b.prob); // riesgo→seguridad, como el resto
  };

  // Espectro de goles totales: misma idea, pero la prob viene de la matriz DC
  const goalsSpectrum = () => {
    const base = Math.round(model.lamTotal);
    const lines = [];
    const top = base + 3;
    for (let k = top; k >= 0; k--) {
      const p = overLine(k);
      lines.push({
        name: `Más de ${k}.5 goles`,
        desc: k === 0 ? 'Al menos un gol en el partido.' : `Al menos ${k+1} goles (λ total ${fmt2(model.lamTotal)}).`,
        prob: p
      });
      if (p >= 0.90 && k <= base) break;
    }
    return lines;
  };

  el.innerHTML = `
  ${matchHeader(model, s1, s2)}

  <!-- DESTACADAS: 1X2 + Doble oportunidad -->
  <div class="featured-bets">
    <div class="featured-title">Resultado del partido (1X2)</div>
    <div class="outcome-row">
      <div class="outcome-card win ${confClass(model.pH)}">
        <div class="oc-label">${names.team1}</div>
        <div class="oc-prob">${pct(model.pH)}%</div>
        <div class="oc-tag">Gana local (1)</div>
      </div>
      <div class="outcome-card ${confClass(model.pD)}">
        <div class="oc-label">Empate</div>
        <div class="oc-prob">${pct(model.pD)}%</div>
        <div class="oc-tag">Empate (X)</div>
      </div>
      <div class="outcome-card win ${confClass(model.pA)}">
        <div class="oc-label">${names.team2}</div>
        <div class="oc-prob">${pct(model.pA)}%</div>
        <div class="oc-tag">Gana visitante (2)</div>
      </div>
    </div>
    <div class="featured-title">Doble oportunidad</div>
    <div class="dc-row">
      <div class="dc-card ${confClass(dc1X)==='high'?'dc-high':''}">
        <div class="dc-label">1X</div>
        <div class="dc-prob" style="color:${confClass(dc1X)==='high'?'var(--accent)':confClass(dc1X)==='medium'?'var(--warn)':'var(--text-1)'}">${pct(dc1X)}%</div>
        <div class="dc-sub">${names.team1} o empate</div>
      </div>
      <div class="dc-card ${confClass(dc12)==='high'?'dc-high':''}">
        <div class="dc-label">12</div>
        <div class="dc-prob" style="color:${confClass(dc12)==='high'?'var(--accent)':confClass(dc12)==='medium'?'var(--warn)':'var(--text-1)'}">${pct(dc12)}%</div>
        <div class="dc-sub">Cualquiera gana (no empate)</div>
      </div>
      <div class="dc-card ${confClass(dcX2)==='high'?'dc-high':''}">
        <div class="dc-label">X2</div>
        <div class="dc-prob" style="color:${confClass(dcX2)==='high'?'var(--accent)':confClass(dcX2)==='medium'?'var(--warn)':'var(--text-1)'}">${pct(dcX2)}%</div>
        <div class="dc-sub">Empate o ${names.team2}</div>
      </div>
    </div>
  </div>

  <div class="bet-filter-bar">
    <span class="bfb-label">🔎 Filtrar por probabilidad</span>
    <button class="bfb-chip" data-th="all" onclick="applyBetFilter(null,null)">Todas</button>
    <div class="bfb-sep"></div>
    <span class="bfb-sublabel">≥</span>
    <button class="bfb-chip" data-th-min="0.9" onclick="applyBetFilter(0.90,null)">90%</button>
    <button class="bfb-chip" data-th-min="0.85" onclick="applyBetFilter(0.85,null)">85%</button>
    <button class="bfb-chip" data-th-min="0.8" onclick="applyBetFilter(0.80,null)">80%</button>
    <button class="bfb-chip" data-th-min="0.75" onclick="applyBetFilter(0.75,null)">75%</button>
    <button class="bfb-chip" data-th-min="0.7" onclick="applyBetFilter(0.70,null)">70%</button>
    <button class="bfb-chip" data-th-min="0.65" onclick="applyBetFilter(0.65,null)">65%</button>
    <button class="bfb-chip" data-th-min="0.6" onclick="applyBetFilter(0.60,null)">60%</button>
    <div class="bfb-sep"></div>
    <span class="bfb-sublabel">Rango</span>
    <div class="bfb-range-row">
      <span class="bfb-range-label">de</span>
      <input class="bfb-range-input" id="bfb-min" type="number" min="0" max="100" step="1" placeholder="mín" title="Probabilidad mínima (%)">
      <span class="bfb-range-label">%&nbsp;&nbsp;a</span>
      <input class="bfb-range-input" id="bfb-max" type="number" min="0" max="100" step="1" placeholder="máx" title="Probabilidad máxima (%)">
      <span class="bfb-range-label">%</span>
      <button class="bfb-chip bfb-range-go" onclick="applyRangeFilter()">Buscar</button>
    </div>
  </div>
  <div id="bet-filter-results" style="display:none"></div>

  <!-- ============ CONSTRUCTOR DE COMBINADA PERSONALIZADA ============ -->
  <div class="combo-builder" id="combo-builder">
    <div class="cb-head" onclick="toggleComboBuilder()">
      <span class="cb-icon">🧪</span>
      <div class="cb-titles">
        <div class="cb-name">Arma tu combinada</div>
        <div class="cb-meta">Elige varias predicciones y mira la probabilidad combinada</div>
      </div>
      <span class="cb-chevron">▼</span>
    </div>
    <div class="cb-body" id="cb-body">
      <div class="cb-picker">
        <button class="cb-menu-trigger" id="cb-menu-trigger" onclick="toggleCbMenu()">
          <span class="cb-mt-icon">➕</span>
          <span class="cb-mt-text">Añadir predicción</span>
          <span class="cb-mt-chevron">▾</span>
        </button>
        <div class="cb-menu" id="cb-menu" style="display:none">
          <div class="cb-menu-bar" id="cb-menu-bar"></div>
          <div class="cb-menu-body" id="cb-menu-body"></div>
        </div>
      </div>
      <div id="cb-legs" class="cb-legs"></div>
      <div id="cb-result" class="cb-result" style="display:none"></div>
    </div>
  </div>

  <div id="bet-accordions">
  <div class="featured-title">Mercados (toca para desplegar)</div>

  ${accordionSection('goles', '⚽', 'Goles', [
    { title: 'Más de X goles (total del partido)', note: `λ total esperado = ${fmt2(model.lamTotal)} · espectro hasta ~90%`, bets: goalsSpectrum() },
    { title: 'Menos de X goles (total del partido)', bets: [
      { name: 'Menos de 1.5 goles', desc: 'Partido cerrado, 0 o 1 gol.', prob: underLine(1) },
      { name: 'Menos de 2.5 goles', desc: 'Como máximo 2 goles.', prob: underLine(2) },
      { name: 'Menos de 3.5 goles', desc: 'Como máximo 3 goles.', prob: underLine(3) },
      { name: 'Menos de 4.5 goles', desc: 'Como máximo 4 goles.', prob: underLine(4) },
    ]},
    { title: 'Ambos equipos anotan', bets: [
      { name: 'Ambos anotan (BTTS) — Sí', desc: `P(${names.team1}≥1)×P(${names.team2}≥1) = ${pct(1-poissonP(model.lam1,0))}%×${pct(1-poissonP(model.lam2,0))}%.`, prob: model.btts },
      { name: 'Ambos anotan — No', desc: 'Al menos un equipo se queda sin marcar.', prob: 1 - model.btts },
    ]},
    { title: 'Primer gol', note: 'Mercado exclusivo — las tres opciones suman 100%', bets: [
      { name: `${names.team1} marca primero`, desc: `Proporción ${pct(fg.home)}% del total esperado.`, prob: fg.home },
      { name: `${names.team2} marca primero`, desc: `Proporción de su λ en el total.`, prob: fg.away },
      { name: 'Sin goles (0-0)', desc: `P(0-0) = ${pct(model.p00)}%.`, prob: model.p00 },
    ]},
  ])}

  ${accordionSection('combinadas', '🔗', 'Combinadas (mismo partido)', [
    { title: 'Exactas — desde la matriz de marcadores',
      note: 'Sin supuestos: la correlación es la del propio marcador. Compáralas con su versión "independiente".',
      bets: exactCombos },
    { title: 'Entre mercados — correlación estimada',
      note: 'Cópula gaussiana que respeta las distribuciones marginales. ρ asumido (no de tus datos), tuneable en MKT_CORR.',
      bets: corrCombos },
  ])}

  ${accordionSection('tiros', '🥅', 'Tiros', [
    { title: 'Tiros a puerta — total', note: `Esperados: ${names.team1} ~${fmt(sh.exp1)} · ${names.team2} ~${fmt(sh.exp2)} · total ~${fmt(sh.exp1+sh.exp2)}`, bets:
      lineSet(sh.exp1 + sh.exp2, 'Tiros a puerta totales', 'Suma cruzada con defensas') },
    { title: `Tiros a puerta — ${names.team1}`, bets:
      lineSet(sh.exp1, `${names.team1} tiros a puerta`, `Ajustado por defensa de ${names.team2}`) },
    { title: `Tiros a puerta — ${names.team2}`, bets:
      lineSet(sh.exp2, `${names.team2} tiros a puerta`, `Ajustado por defensa de ${names.team1}`) },
    { title: 'Tiros totales (normales)', note: `Esperados: ${names.team1} ~${fmt(shotsTot1)} · ${names.team2} ~${fmt(shotsTot2)} · total ~${fmt(shotsTotal)}`, bets:
      lineSet(shotsTotal, 'Tiros totales', 'Derivado de tiros a puerta y precisión histórica') },
    { title: `Tiros totales — ${names.team1}`, bets:
      lineSet(shotsTot1, `${names.team1} tiros`, `Precisión histórica ${pct(acc1)}%`) },
    { title: `Tiros totales — ${names.team2}`, bets:
      lineSet(shotsTot2, `${names.team2} tiros`, `Precisión histórica ${pct(acc2)}%`) },
    { title: '¿Quién tira más a puerta?', bets: [
      { name: `${names.team1} tira más a puerta`, desc: `${fmt(sh.exp1)} vs ${fmt(sh.exp2)} esperados.`, prob: sh.exp1/(sh.exp1+sh.exp2) },
      { name: `${names.team2} tira más a puerta`, desc: `${fmt(sh.exp2)} vs ${fmt(sh.exp1)} esperados.`, prob: sh.exp2/(sh.exp1+sh.exp2) },
    ]},
  ])}

  ${accordionSection('corners', '🚩', 'Corners', [
    { title: 'Corners totales', note: `Esperados: ${names.team1} ~${fmt(cp.exp1)} · ${names.team2} ~${fmt(cp.exp2)} · total ~${fmt(cp.mu)}`, bets:
      lineSet(cp.mu, 'Corners totales', 'Ataque vs defensa del rival') },
    { title: `Corners — ${names.team1}`, bets:
      lineSet(cp.exp1, `${names.team1} corners`, `Ajustado por defensa de ${names.team2}`) },
    { title: `Corners — ${names.team2}`, bets:
      lineSet(cp.exp2, `${names.team2} corners`, `Ajustado por defensa de ${names.team1}`) },
  ])}

  ${accordionSection('tarjetas', '🟨', 'Tarjetas', [
    { title: 'Tarjetas totales', note: `μ esperadas = ${fmt(cards.mu)} entre ambos equipos${cards.factors && cards.factors.length ? ' · ajustes: ' + cards.factors.join(', ') : ''}`, bets:
      lineSet(cards.mu, 'Tarjetas totales', cards.factors && cards.factors.length ? 'Histórico + contexto del partido' : 'Suma esperada del partido') },
  ])}

  ${(() => {
    const wah = winAnyHalfProbs(model);
    return accordionSection('mitades', '⏱️', 'Mitades', [
    { title: 'Resultado por mitad', bets: [
      { name: `${names.team1} gana al menos una mitad`, desc: `Según el modelo del partido (λ ${fmt2(model.lam1)} vs ${fmt2(model.lam2)}). Coherente con su prob. de ganar.`, prob: wah.home },
      { name: `${names.team2} gana al menos una mitad`, desc: `Según el modelo del partido. Probabilidad de superar al rival en la 1ª o la 2ª mitad.`, prob: wah.away },
    ]},
    { title: 'Goles por mitad', bets: [
      { name: 'Gol en 1ª parte', desc: `Histórico ${pct((s1.wGoalIn1T+s2.wGoalIn1T)/2)}%.`, prob: Math.min(0.97,(s1.wGoalIn1T+s2.wGoalIn1T)/2) },
      { name: 'Gol en 2ª parte', desc: `Histórico ${pct((s1.wGoalIn2T+s2.wGoalIn2T)/2)}%.`, prob: Math.min(0.97,(s1.wGoalIn2T+s2.wGoalIn2T)/2) },
    ]},
    { title: 'Ambos anotan por mitad', bets: [
      { name: 'Ambos anotan en 1ª parte', desc: 'BTTS primera mitad.', prob: Math.min(0.95,(s1.wBtts1T+s2.wBtts1T)/2) },
      { name: 'Ambos anotan en 2ª parte', desc: 'BTTS segunda mitad.', prob: Math.min(0.95,(s1.wBtts2T+s2.wBtts2T)/2) },
    ]},
  ]); })()}

  ${accordionSection('otros', '🛡️', 'Victoria a cero y otros', [
    { title: 'Gana sin recibir goles', bets: [
      { name: `${names.team1} gana a 0`, desc: `Clean sheet ${pct(s1.wCleanSheet)}%, gana a 0 en ${pct(s1.wWinCS)}%.`, prob: csWin1 },
      { name: `${names.team2} gana a 0`, desc: `Clean sheet ${pct(s2.wCleanSheet)}%, gana a 0 en ${pct(s2.wWinCS)}%.`, prob: csWin2 },
    ]},
  ])}

  ${accordionSection('marcadores', '🎲', 'Marcadores más probables', [
    { title: 'Top 12 marcadores', note: 'Poisson + Dixon-Coles, ordenados por probabilidad',
      bets: [],
      html: (() => {
        const scores = [];
        for (let h = 0; h <= 7; h++)
          for (let a = 0; a <= 7; a++) {
            const p = model.mat[h][a];
            if (p > 0.001) scores.push({ h, a, p });
          }
        scores.sort((a, b) => b.p - a.p);
        const top = scores.slice(0, 12);
        const maxP = top[0].p;
        return `<div class="scoreline-grid">${top.map((s, idx) => {
          const isHome = s.h > s.a, isDraw = s.h === s.a;
          const color = isHome ? 'var(--home)' : isDraw ? '#6b7280' : 'var(--away)';
          const label = isHome ? names.team1 : isDraw ? 'Empate' : names.team2;
          const barW = Math.round((s.p / maxP) * 100);
          return `<div class="scoreline-card ${idx === 0 ? 'sc-top' : ''}">
            <div class="sc-score" style="color:${color}">${s.h} — ${s.a}</div>
            <div class="sc-label">${label}</div>
            <div class="sc-bar-bg"><div class="sc-bar-fill" style="width:${barW}%;background:${color}"></div></div>
            <div class="sc-pct">${(s.p * 100).toFixed(1)}%</div>
          </div>`;
        }).join('')}</div>`;
      })()
    },
  ])}
  </div>
  `;

  // Si había un filtro activo, mantenerlo tras recalcular el modelo
  if (betProbFilter != null) applyBetFilter(betProbFilter, null);

  // Reconstruir el constructor de combinada (el pool ya está lleno)
  initComboBuilder();
}

// Aplana todas las apuestas y muestra solo las que superan el umbral.
// null = vista normal de mercados. El umbral compara contra la prob MOSTRADA.
function applyBetFilter(threshold, maxThreshold) {
  betProbFilter = threshold;
  const acc = document.getElementById('bet-accordions');
  const res = document.getElementById('bet-filter-results');
  if (!acc || !res) return;

  // Marcar el chip activo
  document.querySelectorAll('.bfb-chip').forEach(c => {
    const thMin = c.getAttribute('data-th-min');
    const thAll = c.getAttribute('data-th');
    const on = (threshold == null && maxThreshold == null && thAll === 'all')
             || (threshold != null && maxThreshold == null && thMin != null && Math.abs(parseFloat(thMin) - threshold) < 1e-9);
    c.classList.toggle('active', on);
  });

  if (threshold == null && maxThreshold == null) { // volver a la vista de mercados
    res.style.display = 'none';
    res.innerHTML = '';
    acc.style.display = '';
    return;
  }

  acc.style.display = 'none';
  res.style.display = '';

  const minTh = threshold != null ? threshold : 0;
  const maxTh = maxThreshold != null ? maxThreshold : 1;

  // Filtrar + dedupe por nombre
  const seen = new Set();
  const hits = betSearchPool
    .map(b => ({ ...b, disp: dispProb(b.prob) }))
    .filter(b => b.disp >= minTh - 1e-9 && b.disp <= maxTh + 1e-9)
    .sort((a, b) => b.disp - a.disp)
    .filter(b => { if (seen.has(b.name)) return false; seen.add(b.name); return true; });

  const minLabel = Math.round(minTh * 100);
  const maxLabel = maxThreshold != null ? Math.round(maxTh * 100) : null;
  const rangeLabel = maxLabel != null ? `entre <strong>${minLabel}%</strong> y <strong>${maxLabel}%</strong>` : `≥ <strong>${minLabel}%</strong>`;

  if (!hits.length) {
    res.innerHTML = `<div class="bet-filter-empty">Ninguna predicción ${maxLabel != null ? `entre ${minLabel}% y ${maxLabel}%` : `≥ ${minLabel}%`}.<br>Prueba un umbral diferente.</div>`;
    return;
  }

  // Agrupar por mercado
  const groups = new Map();
  hits.forEach(b => {
    if (!groups.has(b.market)) groups.set(b.market, { icon: b.icon, bets: [] });
    groups.get(b.market).bets.push(b);
  });

  const sections = [...groups.entries()].map(([market, g]) => {
    const cards = g.bets.map(b => betCard(b.name, b.desc, b.prob)).join('');
    return `<div class="bet-filter-group">
      <div class="bet-filter-group-head"><span class="bfg-icon">${g.icon || '🎯'}</span><span class="bfg-name">${market}</span><span class="bfg-count">${g.bets.length}</span></div>
      <div class="bets-grid">${cards}</div>
    </div>`;
  }).join('');

  res.innerHTML = `
    <div class="bet-filter-summary"><strong>${hits.length}</strong> predicci${hits.length !== 1 ? 'ones' : 'ón'} con probabilidad ${rangeLabel}, ordenadas de mayor a menor.</div>
    ${sections}`;
}

function applyRangeFilter() {
  const minInp = document.getElementById('bfb-min');
  const maxInp = document.getElementById('bfb-max');
  const minVal = minInp && minInp.value.trim() !== '' ? parseFloat(minInp.value) / 100 : 0;
  const maxVal = maxInp && maxInp.value.trim() !== '' ? parseFloat(maxInp.value) / 100 : 1;
  applyBetFilter(minVal, maxVal);
}

// ============================================================
//  CONSTRUCTOR DE COMBINADA PERSONALIZADA
//  El usuario elige varias apuestas del partido y ve la prob.
//  combinada. Se asume independencia entre selecciones (igual que
//  las combinadas "independientes" del modelo): es una aproximación
//  conservadora, no refleja correlaciones reales entre mercados.
// ============================================================
let comboBuilderLegs = [];   // nombres de apuestas seleccionadas
let comboBuilderOpen = false;

function toggleComboBuilder() {
  comboBuilderOpen = !comboBuilderOpen;
  const b = document.getElementById('combo-builder');
  if (b) b.classList.toggle('open', comboBuilderOpen);
}

// Estado de navegación del menú en cascada: Mercado › Subdivisión › Líneas
let cbMenuOpen = false;
let cbNav = { market: null, sub: null };

// Construye el árbol Mercado → Subdivisión → Apuestas a partir del pool.
// Conserva el orden de aparición (mercados y subdivisiones) y deduplica por
// nombre quedándose con la mayor probabilidad mostrada.
function comboMarketTree() {
  const best = new Map();
  betSearchPool.forEach(b => {
    const dp = dispProb(b.prob);
    if (!best.has(b.name) || dp > best.get(b.name).dp) best.set(b.name, { ...b, dp });
  });
  const tree = new Map(); // market -> { icon, subs: Map(sub -> Map(name -> item)) }
  betSearchPool.forEach(b => {
    const o = best.get(b.name);
    if (!o) return;
    if (!tree.has(b.market)) tree.set(b.market, { icon: b.icon || '🎯', subs: new Map() });
    const mk = tree.get(b.market);
    const subKey = b.sub || b.market;
    if (!mk.subs.has(subKey)) mk.subs.set(subKey, new Map());
    mk.subs.get(subKey).set(b.name, o);
  });
  return tree;
}

// Reconstruye el menú cuando cambia el partido: limpia el estado de navegación
// y las legs que ya no existan, y mantiene el panel como esté.
function initComboBuilder() {
  const builder = document.getElementById('combo-builder');
  if (!builder) return;
  builder.classList.toggle('open', comboBuilderOpen);

  const seen = comboPoolMap();
  // Si la subdivisión/mercado donde estábamos ya no existe, volvemos a la raíz
  const tree = comboMarketTree();
  if (cbNav.market && !tree.has(cbNav.market)) cbNav = { market: null, sub: null };
  else if (cbNav.sub && (!tree.get(cbNav.market) || !tree.get(cbNav.market).subs.has(cbNav.sub)))
    cbNav.sub = null;

  // Limpiar legs que ya no existan en este enfrentamiento
  comboBuilderLegs = comboBuilderLegs.filter(n => seen.has(n));

  // El DOM del constructor se recrea en cada cálculo: re-aplicar estado del panel
  const picker = document.querySelector('.cb-picker');
  const menu = document.getElementById('cb-menu');
  if (picker) picker.classList.toggle('menu-open', cbMenuOpen);
  if (menu) menu.style.display = cbMenuOpen ? '' : 'none';

  renderCbMenu();
  renderComboLegs();
}

// Abre/cierra el panel del menú
function toggleCbMenu() {
  cbMenuOpen = !cbMenuOpen;
  if (cbMenuOpen) cbNav = { market: null, sub: null }; // siempre arranca en la raíz
  const picker = document.querySelector('.cb-picker');
  const menu = document.getElementById('cb-menu');
  if (picker) picker.classList.toggle('menu-open', cbMenuOpen);
  if (menu) menu.style.display = cbMenuOpen ? '' : 'none';
  if (cbMenuOpen) renderCbMenu();
}

// Navega a un mercado / subdivisión
function cbGoTo(market, sub) {
  cbNav = { market: market || null, sub: sub || null };
  renderCbMenu();
}

// Añade o quita una línea desde el menú (toggle), manteniendo el menú abierto
function cbToggleLine(name) {
  if (comboBuilderLegs.includes(name)) {
    comboBuilderLegs = comboBuilderLegs.filter(n => n !== name);
  } else {
    comboBuilderLegs.push(name);
  }
  renderCbMenu();
  renderComboLegs();
}

// Dibuja el nivel actual del menú (raíz / mercado / subdivisión)
function renderCbMenu() {
  const bar = document.getElementById('cb-menu-bar');
  const body = document.getElementById('cb-menu-body');
  if (!bar || !body) return;

  const tree = comboMarketTree();
  const esc = s => String(s).replace(/\\/g, '\\\\').replace(/'/g, "\\'");

  // --- Migas de pan ---
  const crumbs = [];
  crumbs.push(cbNav.market
    ? `<span class="cb-crumb-seg link" onclick="cbGoTo(null,null)">Mercados</span>`
    : `<span class="cb-crumb-seg current">Mercados</span>`);
  if (cbNav.market) {
    crumbs.push(`<span class="cb-crumb-sep">›</span>`);
    crumbs.push(cbNav.sub
      ? `<span class="cb-crumb-seg link" onclick="cbGoTo('${esc(cbNav.market)}',null)">${cbNav.market}</span>`
      : `<span class="cb-crumb-seg current">${cbNav.market}</span>`);
  }
  if (cbNav.sub) {
    crumbs.push(`<span class="cb-crumb-sep">›</span>`);
    crumbs.push(`<span class="cb-crumb-seg current">${cbNav.sub}</span>`);
  }
  bar.innerHTML = `<div class="cb-crumb">${crumbs.join('')}</div>`
    + `<button class="cb-menu-close" onclick="toggleCbMenu()" title="Cerrar">✕</button>`;

  // --- Nivel hoja: líneas de una subdivisión ---
  if (cbNav.market && cbNav.sub) {
    const subMap = tree.get(cbNav.market) && tree.get(cbNav.market).subs.get(cbNav.sub);
    const items = subMap ? [...subMap.values()].sort((a, b) => b.dp - a.dp) : [];
    if (!items.length) { body.innerHTML = `<div class="cb-menu-empty">Sin predicciones aquí.</div>`; return; }
    body.innerHTML = items.map(o => {
      const added = comboBuilderLegs.includes(o.name);
      const cc = confClass(o.dp);
      return `<button class="cb-line ${added ? 'added' : ''}" onclick="cbToggleLine('${esc(o.name)}')">
        <span class="cb-line-check">✓</span>
        <span class="cb-line-name">${o.name}</span>
        <span class="cb-line-prob ${cc}">${pct(o.dp)}%</span>
      </button>`;
    }).join('');
    return;
  }

  // --- Nivel medio: subdivisiones de un mercado ---
  if (cbNav.market) {
    const mk = tree.get(cbNav.market);
    if (!mk) { body.innerHTML = `<div class="cb-menu-empty">Mercado no disponible.</div>`; cbNav.market = null; return; }
    body.innerHTML = [...mk.subs.entries()].map(([sub, items]) =>
      `<button class="cb-node" onclick="cbGoTo('${esc(cbNav.market)}','${esc(sub)}')">
        <span class="cb-node-icon">${mk.icon}</span>
        <span class="cb-node-name">${sub}</span>
        <span class="cb-node-count">${items.size}</span>
        <span class="cb-node-arrow">›</span>
      </button>`
    ).join('');
    return;
  }

  // --- Raíz: mercados ---
  if (!tree.size) { body.innerHTML = `<div class="cb-menu-empty">Calcula un partido para ver mercados.</div>`; return; }
  body.innerHTML = [...tree.entries()].map(([market, mk]) => {
    const count = [...mk.subs.values()].reduce((a, m) => a + m.size, 0);
    return `<button class="cb-node" onclick="cbGoTo('${esc(market)}',null)">
      <span class="cb-node-icon">${mk.icon}</span>
      <span class="cb-node-name">${market}</span>
      <span class="cb-node-count">${count}</span>
      <span class="cb-node-arrow">›</span>
    </button>`;
  }).join('');
}

function comboPoolMap() {
  const seen = new Map();
  betSearchPool.forEach(b => {
    const dp = dispProb(b.prob);
    if (!seen.has(b.name) || dp > seen.get(b.name).dp) seen.set(b.name, { ...b, dp });
  });
  return seen;
}

function removeComboLeg(name) {
  comboBuilderLegs = comboBuilderLegs.filter(n => n !== name);
  renderComboLegs();
  if (cbMenuOpen) renderCbMenu();
}

function clearComboLegs() {
  comboBuilderLegs = [];
  renderComboLegs();
  if (cbMenuOpen) renderCbMenu();
}

function renderComboLegs() {
  const legsEl = document.getElementById('cb-legs');
  const resEl = document.getElementById('cb-result');
  if (!legsEl || !resEl) return;
  const pool = comboPoolMap();

  if (comboBuilderLegs.length === 0) {
    legsEl.innerHTML = `<div class="cb-empty">Aún no has añadido predicciones. Elige al menos dos para ver la combinada. 👆</div>`;
    resEl.style.display = 'none';
    return;
  }

  legsEl.innerHTML = comboBuilderLegs.map(n => {
    const b = pool.get(n);
    const p = b ? b.dp : 0;
    return `<div class="cb-leg">
      <span class="cb-leg-icon">${b ? (b.icon||'🎯') : '🎯'}</span>
      <span class="cb-leg-name">${n}</span>
      <span class="cb-leg-prob">${pct(p)}%</span>
      <button class="cb-leg-del" onclick="removeComboLeg('${n.replace(/'/g,"\\'")}')" title="Quitar">✕</button>
    </div>`;
  }).join('');

  // Probabilidad combinada (producto = independencia)
  const combined = comboBuilderLegs.reduce((acc, n) => {
    const b = pool.get(n);
    return acc * (b ? b.dp : 1);
  }, 1);
  // Cuota implícita justa (sin margen): 1 / prob
  const fairOdds = combined > 0 ? (1 / combined) : 0;

  const cc = combined > 0.35 ? 'high' : combined > 0.15 ? 'medium' : 'low';
  const ccLabel = combined > 0.35 ? 'Alta' : combined > 0.15 ? 'Media' : 'Baja';
  const ccColor = cc === 'high' ? 'var(--accent)' : cc === 'medium' ? 'var(--warn)' : 'var(--bad)';

  resEl.style.display = '';
  resEl.innerHTML = `
    <div class="cb-result-grid">
      <div class="cb-result-main">
        <div class="cb-result-val" style="color:${ccColor}">${pct(combined)}%</div>
        <div class="cb-result-lbl">Probabilidad combinada · ${comboBuilderLegs.length} selecciones</div>
      </div>
      <div class="cb-result-side">
        <div class="cb-side-item"><span class="cb-side-val">${fairOdds.toFixed(2)}</span><span class="cb-side-lbl">Cuota justa</span></div>
        <div class="cb-side-item"><span class="cb-side-val" style="color:${ccColor}">${ccLabel}</span><span class="cb-side-lbl">Confianza</span></div>
      </div>
    </div>
    <div class="cb-result-note">⚠️ Calculada asumiendo que las predicciones son independientes (producto de probabilidades). Si los eventos están correlacionados (p. ej. "+2.5 goles" y "ambos anotan"), la probabilidad real puede ser distinta. La cuota justa es sin margen de casa.</div>
    <div class="cb-result-actions"><span class="cb-clear" onclick="clearComboLegs()">🗑 Vaciar selección</span></div>`;
}


// ---- MITADES ----
function renderHalves(s1, s2, model) {
  const el = document.getElementById('halves-content');
  el.className = '';
  const btts1T  = Math.min(0.95, (s1.wBtts1T + s2.wBtts1T) / 2);
  const btts2T  = Math.min(0.95, (s1.wBtts2T + s2.wBtts2T) / 2);
  const bttsAmbas = Math.min(0.80, btts1T * btts2T * 1.25);
  const goalIn1T  = Math.min(0.97, (s1.wGoalIn1T + s2.wGoalIn1T) / 2);
  const goalIn2T  = Math.min(0.97, (s1.wGoalIn2T + s2.wGoalIn2T) / 2);
  const goalAmbas = Math.min(0.95, goalIn1T * goalIn2T * 1.15);

  // Poisson por mitad
  const lam1H = model.lam1 * 0.44;
  const lam2H = model.lam2 * 0.44;
  const lam1S = model.lam1 * 0.56;
  const lam2S = model.lam2 * 0.56;
  const btts1T_p = (1-poissonP(lam1H,0)) * (1-poissonP(lam2H,0));
  const btts2T_p = (1-poissonP(lam1S,0)) * (1-poissonP(lam2S,0));
  const goalIn1T_p = 1 - poissonP(lam1H+lam2H, 0);
  const goalIn2T_p = 1 - poissonP(lam1S+lam2S, 0);

  // Combinamos Poisson con histórico ponderado (50/50)
  const mixBtts1T  = (btts1T  + btts1T_p) / 2;
  const mixBtts2T  = (btts2T  + btts2T_p) / 2;
  const mixGoal1T  = (goalIn1T + goalIn1T_p) / 2;
  const mixGoal2T  = (goalIn2T + goalIn2T_p) / 2;
  const mixBttsAmbas = Math.min(0.80, mixBtts1T * mixBtts2T * 1.2);
  const mixGoalAmbas = Math.min(0.95, mixGoal1T * mixGoal2T * 1.1);

  el.innerHTML = `
  ${matchHeader(model, s1, s2)}
  <div class="bets-section-title">Goles en ambas mitades</div>
  <div class="half-grid">
    <div class="half-card">
      <div class="half-title">Gol en 1ª parte</div>
      <div class="half-val">${pct(mixGoal1T)}%</div>
      <div class="half-sub">Hist: ${pct(goalIn1T)}% · Poisson: ${pct(goalIn1T_p)}%</div>
    </div>
    <div class="half-card">
      <div class="half-title">Gol en 2ª parte</div>
      <div class="half-val">${pct(mixGoal2T)}%</div>
      <div class="half-sub">Hist: ${pct(goalIn2T)}% · Poisson: ${pct(goalIn2T_p)}%</div>
    </div>
  </div>
  <div class="bets-grid" style="margin-bottom:20px">
    ${betCard('Goles en ambas mitades', `Hay gol en 1ª (${pct(mixGoal1T)}%) Y en 2ª parte (${pct(mixGoal2T)}%). Mixtura histórico + Poisson.`, mixGoalAmbas)}
  </div>

  <div class="bets-section-title">Ambos equipos anotan por mitad</div>
  <div class="half-grid">
    <div class="half-card">
      <div class="half-title">BTTS en 1ª parte</div>
      <div class="half-val">${pct(mixBtts1T)}%</div>
      <div class="half-sub">Hist: ${pct(btts1T)}% · Poisson: ${pct(btts1T_p)}%</div>
    </div>
    <div class="half-card">
      <div class="half-title">BTTS en 2ª parte</div>
      <div class="half-val">${pct(mixBtts2T)}%</div>
      <div class="half-sub">Hist: ${pct(btts2T)}% · Poisson: ${pct(btts2T_p)}%</div>
    </div>
  </div>
  <div class="bets-grid">
    ${betCard('Ambos anotan en 1ª parte', `λ 1T: ${names.team1}=${fmt2(lam1H)} · ${names.team2}=${fmt2(lam2H)}. Mix histórico+Poisson.`, mixBtts1T)}
    ${betCard('Ambos anotan en 2ª parte', `λ 2T: ${names.team1}=${fmt2(lam1S)} · ${names.team2}=${fmt2(lam2S)}.`, mixBtts2T)}
    ${betCard('Ambos anotan en 1ª Y 2ª parte', 'Ambos equipos marcan en las dos mitades.', mixBttsAmbas)}
  </div>

  <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:16px">
    ${halfTeamCard(s1, names.team1)}
    ${halfTeamCard(s2, names.team2)}
  </div>`;
}

function halfTeamCard(s, name) {
  return `<div class="team-card"><h3>${name}</h3>
    <div class="stat-row"><span class="stat-label">Goles 1T anotados/p</span><span class="stat-val">${fmt(s.wG1F)}</span></div>
    <div class="stat-row"><span class="stat-label">Goles 1T recibidos/p</span><span class="stat-val">${fmt(s.wG1C)}</span></div>
    <div class="stat-row"><span class="stat-label">Goles 2T anotados/p</span><span class="stat-val">${fmt(s.wG2F)}</span></div>
    <div class="stat-row"><span class="stat-label">Goles 2T recibidos/p</span><span class="stat-val">${fmt(s.wG2C)}</span></div>
    <div class="stat-row"><span class="stat-label">Anota en 1T</span><span class="stat-val green">${pct(s.wGoalIn1T)}%</span></div>
    <div class="stat-row"><span class="stat-label">Anota en 2T</span><span class="stat-val green">${pct(s.wGoalIn2T)}%</span></div>
    <div class="stat-row"><span class="stat-label">BTTS 1T</span><span class="stat-val">${pct(s.wBtts1T)}%</span></div>
    <div class="stat-row"><span class="stat-label">BTTS 2T</span><span class="stat-val">${pct(s.wBtts2T)}%</span></div>
  </div>`;
}

// ============================================================
//  HISTORIAL DE PARTIDOS — muestra las filas crudas del CSV
// ============================================================
function setHistoryTeam(t) { historyActiveTeam = t; renderHistory(); }

function renderHistory() {
  const el = document.getElementById('history-content');
  if (!el) return; // sección no presente para este usuario (solo-admin)
  if (!state.team1 || !state.team2) {
    el.className = 'no-data';
    el.innerHTML = '<div style="font-size:36px">📋</div><p>Carga los datos de los equipos para ver su historial de partidos</p>';
    return;
  }
  el.className = '';

  const t = historyActiveTeam;
  const rows = (t === 1 ? state.team1 : state.team2) || [];
  const teamName = t === 1 ? names.team1 : names.team2;
  const color = t === 1 ? 'var(--home)' : 'var(--away)';

  // Resumen rápido (totales crudos, no ponderados — es un historial, no predicción)
  const n = rows.length;
  let w=0,d=0,l=0,gfSum=0,gcSum=0;
  rows.forEach(r => {
    const res = (r.resultado||'').toUpperCase();
    if (res==='W') w++; else if (res==='D') d++; else if (res==='L') l++;
    gfSum += get(r,'goles_f'); gcSum += get(r,'goles_c');
  });
  const sedeIcon = s => s==='local' ? '🏠' : s==='away' ? '✈️' : '⚪';
  const sedeLabel = s => s==='local' ? 'Local' : s==='away' ? 'Visita' : 'Neutral';

  // Helper para celdas: muestra valor o guion si está vacío/0 sin dato
  const cell = (r, key) => {
    const raw = r[key];
    if (raw === '' || raw === undefined || raw === null) return '<span class="hist-empty-cell">—</span>';
    return get(r, key);
  };
  // Celda xG: 2 decimales, o "—" si la fila no trae el dato
  const xgCell = (r, key) => {
    const raw = r[key];
    if (raw === '' || raw === undefined || raw === null) return '<span class="hist-empty-cell">—</span>';
    return (+raw).toFixed(2);
  };
  const anyXG = rows.some(r => (r.xg_f!==''&&r.xg_f!=null) || (r.xg_c!==''&&r.xg_c!=null));

  const bodyRows = rows.map((r, i) => {
    const res = (r.resultado||'').toUpperCase();
    const sede = parseSede(r.sede);
    const rival = (r.rival||'').trim() || '—';
    const _lk = lookupFIFA(rival);
    const rk = _lk ? _lk.rank : null;
    const strength = rk !== null ? (FIFA_MAX_RANK - rk)/FIFA_MAX_RANK : 0;
    const fifaCol = rk === null ? 'var(--text-3)' : strength > 0.7 ? 'var(--bad)' : strength > 0.4 ? 'var(--warn)' : 'var(--accent)';
    const fifaBg  = rk === null ? 'var(--bg-2)' : strength > 0.7 ? 'var(--bad-bg)' : strength > 0.4 ? 'var(--warn-bg)' : 'var(--accent-deep)';
    const fecha = (r.fecha||'').trim() || '—';
    const recentClass = i < 5 ? ' hist-recent' : '';
    return `<tr class="${recentClass}">
      <td class="sticky-col hist-rival">${i < 5 ? '<span style="color:'+color+'">●</span> ' : ''}${rival}</td>
      <td><span class="hist-fifa" style="color:${fifaCol};background:${fifaBg}">${rk!==null?'#'+rk:'??'}</span></td>
      <td class="hist-sede" title="${sedeLabel(sede)}">${sedeIcon(sede)}</td>
      <td><span class="hist-res ${res}">${res||'?'}</span></td>
      <td class="hist-score">${cell(r,'goles_f')}–${cell(r,'goles_c')}</td>
      <td style="color:var(--accent);font-family:var(--mono);font-size:11px">${xgCell(r,'xg_f')}–${xgCell(r,'xg_c')}</td>
      <td>${cell(r,'goles_1t_f')}–${cell(r,'goles_1t_c')}</td>
      <td>${cell(r,'goles_2t_f')}–${cell(r,'goles_2t_c')}</td>
      <td>${cell(r,'tiros')}</td>
      <td>${cell(r,'tiros_puerta')}</td>
      <td>${cell(r,'corners')}</td>
      <td>${cell(r,'tarjetas_a')}/${cell(r,'tarjetas_r')}</td>
      <td>${cell(r,'asistencias')}</td>
      <td style="color:var(--text-2);font-size:11px">${fecha}</td>
      <td class="hist-del-cell">
        <span style="display:inline-flex;gap:4px">
          <button class="hist-edit-btn" onclick="openEditHist(${t},${i})" title="Editar este partido">✎</button>
          <button class="hist-del-btn" data-team="${t}" data-idx="${i}" onclick="confirmDeleteHist(this)" title="Eliminar este partido">✕</button>
        </span>
      </td>
    </tr>`;
  }).join('');

  el.innerHTML = `
  <div class="hist-team-select">
    <button class="hist-team-btn ${t===1?'active':''}" onclick="setHistoryTeam(1)">🏠 ${names.team1} <span style="opacity:.6">(${(state.team1||[]).length})</span></button>
    <button class="hist-team-btn ${t===2?'active':''}" onclick="setHistoryTeam(2)">✈️ ${names.team2} <span style="opacity:.6">(${(state.team2||[]).length})</span></button>
  </div>

  <div class="hist-summary">
    <div class="hist-stat"><div class="hs-val" style="color:${color}">${n}</div><div class="hs-lbl">Partidos</div></div>
    <div class="hist-stat"><div class="hs-val" style="color:var(--accent)">${w}-${d}-${l}</div><div class="hs-lbl">V-E-D</div></div>
    <div class="hist-stat"><div class="hs-val">${n>0?(gfSum/n).toFixed(1):'0'}</div><div class="hs-lbl">Goles/p ↑</div></div>
    <div class="hist-stat"><div class="hs-val">${n>0?(gcSum/n).toFixed(1):'0'}</div><div class="hs-lbl">Goles/p ↓</div></div>
  </div>

  <div class="bets-section-title">Historial de ${teamName} <span style="font-size:10px;color:var(--text-2);font-weight:400;text-transform:none">— ordenado del más reciente al más antiguo</span></div>
  <button class="hist-add-match" onclick="addHistMatch(${t})">➕ Añadir partido</button>
  <span style="font-size:11px;color:var(--text-2);margin-left:10px">${anyXG ? '⚡ Este equipo tiene datos de xG → el modelo los usa para λ.' : '⚡ Pulsa ✎ para añadir xG a un partido (mejora la predicción).'}</span>
  <div class="hist-table-wrap">
    <table class="hist-table">
      <thead><tr>
        <th class="sticky-col">Rival</th>
        <th title="Ranking FIFA del rival">FIFA</th>
        <th>Sede</th>
        <th>Res</th>
        <th>Marcador</th>
        <th title="Expected Goals favor–contra" style="color:var(--accent)">xG</th>
        <th title="Goles primer tiempo">1ª parte</th>
        <th title="Goles segundo tiempo">2ª parte</th>
        <th title="Tiros totales">Tiros</th>
        <th title="Tiros a puerta">T.Puerta</th>
        <th>Corners</th>
        <th title="Tarjetas amarillas/rojas">Tarj A/R</th>
        <th title="Asistencias">Asist</th>
        <th>Fecha</th>
        <th></th>
      </tr></thead>
      <tbody>${bodyRows}</tbody>
    </table>
  </div>
  <div class="hist-legend">
    <span><span style="color:${color}">●</span> Últimos 5 partidos (mayor peso en el modelo)</span>
    <span>🏠 Local</span><span>✈️ Visitante</span><span>⚪ Neutral</span>
    <span><span class="hist-res W" style="width:14px;height:14px;font-size:9px">W</span> Victoria</span>
    <span><span class="hist-res D" style="width:14px;height:14px;font-size:9px">D</span> Empate</span>
    <span><span class="hist-res L" style="width:14px;height:14px;font-size:9px">L</span> Derrota</span>
    <span style="color:var(--accent)">✎ Editar partido · xG en verde</span>
  </div>
  <span class="hist-export" onclick="exportHistory(${t})">⬇ Exportar este historial a CSV</span>
  `;
}

// Confirmación en dos pasos dentro de la fila: el botón ✕ se transforma en
// "Sí / No" para evitar borrados accidentales sin un popup molesto.
function confirmDeleteHist(btn) {
  const cell = btn.closest('.hist-del-cell');
  if (!cell) return;
  const team = btn.getAttribute('data-team');
  const idx = btn.getAttribute('data-idx');
  cell.innerHTML = `<span class="hist-del-confirm">
    <button class="hist-del-yes" onclick="doDeleteHist(${team},${idx})" title="Confirmar">Sí</button>
    <button class="hist-del-no" onclick="renderHistory()" title="Cancelar">No</button>
  </span>`;
}

function doDeleteHist(t, i) {
  const key = 'team' + t;
  const rows = state[key];
  if (!rows || i < 0 || i >= rows.length) return;
  rows.splice(i, 1);
  // Si el equipo está guardado en la biblioteca, reflejar el cambio ahí también
  if (typeof syncTeamToLibrary === 'function') syncTeamToLibrary(t);
  // Recalcular todo el modelo (la predicción cambia al quitar un partido)
  renderAll();
}

function exportHistory(t) {
  const rows = (t === 1 ? state.team1 : state.team2) || [];
  if (!rows.length) return;
  const cols = ['fecha','equipo','rival','sede','goles_f','goles_c','goles_1t_f','goles_1t_c',
    'goles_2t_f','goles_2t_c','tiros','tiros_rival','tiros_puerta','tiros_puerta_rival',
    'corners','corners_rival','tarjetas_a','tarjetas_r','asistencias','resultado','xg_f','xg_c',
    'xgot_f','xgot_c','ppda_f','ppda_c'];
  const header = cols.join(',');
  const lines = rows.map(r => cols.map(c => (r[c]===''||r[c]==null)?'':r[c]).join(','));
  const csv = [header, ...lines].join('\n');
  const blob = new Blob([csv], {type:'text/csv'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `historial_${(t===1?names.team1:names.team2).replace(/\s+/g,'_')}.csv`;
  a.click();
}

// ============================================================
//  #6 — EDITAR / AÑADIR partido del historial (con xG)
// ============================================================
let editCtx = null; // { t, idx }  · idx === null → alta de partido nuevo

// Todos los campos editables del modal (id del input = clave de la fila)
const EDIT_FIELDS = ['rival','sede','fecha','goles_f','goles_c','xg_f','xg_c',
  'goles_1t_f','goles_1t_c','goles_2t_f','goles_2t_c','tiros','tiros_rival',
  'tiros_puerta','tiros_puerta_rival','corners','corners_rival',
  'xgot_f','xgot_c','ppda_f','ppda_c',
  'tarjetas_a','tarjetas_r','asistencias'];

function openEditHist(t, i) {
  const rows = state['team'+t] || [];
  const r = rows[i];
  if (!r) return;
  editCtx = { t, idx: i };
  document.getElementById('edit-modal-icon').textContent = '✎';
  document.getElementById('edit-modal-title').textContent = `Editar partido vs ${(r.rival||'rival').trim()}`;
  EDIT_FIELDS.forEach(f => {
    const inp = document.getElementById('edit-'+f);
    if (!inp) return;
    inp.value = (r[f] === undefined || r[f] === null) ? '' : r[f];
  });
  if (!document.getElementById('edit-sede').value) document.getElementById('edit-sede').value = 'local';
  const bw = document.getElementById('edit-both-wrap'); if (bw) bw.style.display = 'none';
  document.getElementById('edit-modal-bg').classList.add('show');
  setTimeout(() => document.getElementById('edit-rival')?.focus(), 50);
}

function addHistMatch(t) {
  editCtx = { t, idx: null };
  document.getElementById('edit-modal-icon').textContent = '➕';
  document.getElementById('edit-modal-title').textContent = `Añadir partido a ${names['team'+t]}`;
  EDIT_FIELDS.forEach(f => { const inp = document.getElementById('edit-'+f); if (inp) inp.value = ''; });
  document.getElementById('edit-sede').value = 'local';
  document.getElementById('edit-fecha').value = new Date().toISOString().slice(0,10);
  // Opción "ambos equipos": solo tiene sentido si los dos equipos están cargados.
  const other = t === 1 ? 2 : 1;
  const bw = document.getElementById('edit-both-wrap');
  const bc = document.getElementById('edit-both');
  const hasOther = !!(state['team'+other] && names['team'+other]);
  if (bw) bw.style.display = hasOther ? '' : 'none';
  if (bc) bc.checked = false;
  if (hasOther) {
    const rivalInp = document.getElementById('edit-rival');
    if (rivalInp) rivalInp.value = names['team'+other];   // prefill con el rival = otro equipo
    const hint = document.getElementById('edit-both-hint');
    if (hint) hint.innerHTML = `Crea el mismo partido en el historial de <strong>${names['team'+other]}</strong> con goles, tiros, córners, xG y PPDA invertidos. Tarjetas y asistencias quedan vacías (son propias de cada equipo).`;
  }
  document.getElementById('edit-modal-bg').classList.add('show');
  setTimeout(() => document.getElementById('edit-rival')?.focus(), 50);
}

function closeEditModal() {
  document.getElementById('edit-modal-bg').classList.remove('show');
  editCtx = null;
}

function saveEditHist() {
  if (!editCtx) return;
  const { t, idx } = editCtx;
  const val = f => { const inp = document.getElementById('edit-'+f); return inp ? inp.value.trim() : ''; };
  // Numéricos: vacío se conserva como '' (para que xG/2ª parte ausentes se
  // detecten bien y la celda muestre "—"); si hay valor, se normaliza ≥0.
  const num = f => { const v = val(f); return v === '' ? '' : Math.max(0, +v); };

  const gf = num('goles_f') === '' ? 0 : num('goles_f');
  const gc = num('goles_c') === '' ? 0 : num('goles_c');
  const row = {
    fecha: val('fecha'),
    equipo: names['team'+t],
    rival: val('rival'),
    sede: val('sede') || 'local',
    goles_f: gf, goles_c: gc,
    xg_f: num('xg_f'), xg_c: num('xg_c'),
    goles_1t_f: num('goles_1t_f'), goles_1t_c: num('goles_1t_c'),
    goles_2t_f: num('goles_2t_f'), goles_2t_c: num('goles_2t_c'),
    tiros: num('tiros'), tiros_rival: num('tiros_rival'),
    tiros_puerta: num('tiros_puerta'), tiros_puerta_rival: num('tiros_puerta_rival'),
    corners: num('corners'), corners_rival: num('corners_rival'),
    xgot_f: num('xgot_f'), xgot_c: num('xgot_c'),
    ppda_f: num('ppda_f'), ppda_c: num('ppda_c'),
    tarjetas_a: num('tarjetas_a'), tarjetas_r: num('tarjetas_r'),
    asistencias: num('asistencias'),
    resultado: outcomeOf(gf, gc)
  };

  const rows = state['team'+t] || (state['team'+t] = []);
  if (idx === null) rows.unshift(row);   // alta: más reciente primero
  else rows[idx] = row;                   // edición: reemplaza en sitio

  if (typeof syncTeamToLibrary === 'function') syncTeamToLibrary(t);

  // --- Reflejo al otro equipo (solo en alta, si el checkbox está marcado) ---
  const both = document.getElementById('edit-both');
  if (idx === null && both && both.checked) {
    const other = t === 1 ? 2 : 1;
    if (state['team'+other] && names['team'+other]) {
      const invSede = row.sede === 'local' ? 'away' : row.sede === 'away' ? 'local' : 'neutral';
      const mGf = row.goles_c, mGc = row.goles_f;
      const mirror = {
        fecha: row.fecha,
        equipo: names['team'+other],
        rival: names['team'+t],
        sede: invSede,
        goles_f: mGf, goles_c: mGc,
        xg_f: row.xg_c, xg_c: row.xg_f,
        goles_1t_f: row.goles_1t_c, goles_1t_c: row.goles_1t_f,
        goles_2t_f: row.goles_2t_c, goles_2t_c: row.goles_2t_f,
        tiros: row.tiros_rival, tiros_rival: row.tiros,
        tiros_puerta: row.tiros_puerta_rival, tiros_puerta_rival: row.tiros_puerta,
        corners: row.corners_rival, corners_rival: row.corners,
        xgot_f: row.xgot_c, xgot_c: row.xgot_f,
        ppda_f: row.ppda_c, ppda_c: row.ppda_f,
        tarjetas_a: '', tarjetas_r: '', asistencias: '',
        resultado: outcomeOf(mGf, mGc)
      };
      const orows = state['team'+other] || (state['team'+other] = []);
      orows.unshift(mirror);
      if (typeof syncTeamToLibrary === 'function') syncTeamToLibrary(other);
    }
  }

  closeEditModal();
  renderAll(); // recalcula modelo, historial y validación
}

// ---- TIROS ----
function renderShots(s1, s2, model) {
  const el = document.getElementById('shots-content');
  el.className = '';
  const sp = shotProbs(s1, s2);
  const e1 = sp.exp1, e2 = sp.exp2;            // tiros a puerta esperados (modelados)
  const tpTotal = e1 + e2;
  const tpLine1 = Math.floor(tpTotal) - 0.5;
  const tpLine2 = Math.floor(tpTotal) + 0.5;
  const tirosTotal = s1.wTirosTotal + s2.wTirosTotal;
  const t1pct = Math.round(sp.home * 100);
  const t2pct = 100 - t1pct;
  const tArrow = t => t > 1.05 ? '↑' : t < 0.95 ? '↓' : '→';
  const tColor = t => t > 1.05 ? 'var(--accent)' : t < 0.95 ? 'var(--bad)' : 'var(--text-2)';
  const ctxLabel = c => c === 'neutral' ? '⚪neutral' : c === 'local' ? '🏠casa' : c === 'away' ? '✈️visita' : '📊gral';
  const sh = expectedShots(s1, s2);

  el.innerHTML = `
  ${matchHeader(model, s1, s2)}
  <div class="bets-section-title">Comparativa tiros a puerta esperados</div>
  <div style="background:var(--bg-2);border:1px solid var(--line);border-radius:12px;padding:14px;margin-bottom:16px">
    <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:6px">
      <span style="color:var(--home-dim);font-weight:600">${names.team1} ~${fmt(e1)}/p</span>
      <span style="color:var(--text-0)">Tiros a puerta esperados</span>
      <span style="color:var(--away-dim);font-weight:600">${fmt(e2)}/p ${names.team2}</span>
    </div>
    <div style="display:flex;gap:8px;align-items:center;margin-bottom:6px">
      <div class="shots-bar-wrap" style="flex:1;height:10px">
        <div class="shots-h" style="width:${t1pct}%"></div>
        <div class="shots-a" style="width:${t2pct}%"></div>
      </div>
    </div>
    <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--text-2)">
      <span>${t1pct}% del total</span>
      <span>Total esperado: ~${fmt(tpTotal)} a puerta · ~${fmt(tirosTotal)} totales</span>
      <span>${t2pct}%</span>
    </div>
    <div style="font-size:10px;color:var(--text-2);margin-top:8px;border-top:1px solid var(--bg-3);padding-top:8px">
      ${names.team1}: genera ${fmt(s1.wTP)}/p, ajustado por defensa rival → <strong style="color:var(--home-dim)">${fmt(e1)}</strong> · contexto ${ctxLabel(sh.ctx1)} · momentum <span style="color:${tColor(sh.trend1)}">${tArrow(sh.trend1)}</span><br>
      ${names.team2}: genera ${fmt(s2.wTP)}/p, ajustado por defensa rival → <strong style="color:var(--away-dim)">${fmt(e2)}</strong> · contexto ${ctxLabel(sh.ctx2)} · momentum <span style="color:${tColor(sh.trend2)}">${tArrow(sh.trend2)}</span>
    </div>
  </div>

  <div class="bets-section-title">¿Qué equipo tira más a puerta? <span style="font-size:10px;color:var(--text-2);font-weight:400;text-transform:none">— mercado exclusivo</span></div>
  <div class="firstgoal-box">
    <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px">
      <span style="color:var(--home-dim);font-weight:600">${names.team1}</span>
      <span style="color:var(--away-dim);font-weight:600">${names.team2}</span>
    </div>
    <div class="fg-bar-wrap">
      <div class="fg-bar-h" style="width:${t1pct}%">${t1pct}%</div>
      <div class="fg-bar-a" style="width:${t2pct}%">${t2pct}%</div>
    </div>
    <div class="fg-labels">
      <span style="color:var(--home-dim)">${names.team1} más tiros</span>
      <span style="color:var(--away-dim)">${names.team2} más tiros</span>
    </div>
  </div>
  <div class="bets-grid" style="margin-top:10px;margin-bottom:16px">
    ${betCard(`${names.team1} tira más a puerta`, `Tiros a puerta esperados (ataque vs defensa rival${neutralVenue?', sede neutral':', con ventaja local'}): ${fmt(e1)} vs ${fmt(e2)}.`, sp.home)}
    ${betCard(`${names.team2} tira más a puerta`, `Tiros a puerta esperados ${names.team2}: ${fmt(e2)}/partido (modelado).`, sp.away)}
  </div>

  <div class="bets-section-title">Líneas de tiros a puerta</div>
  <div class="bets-grid" style="margin-bottom:16px">
    ${betCard(`Más de ${fmt(tpLine1)} tiros a puerta totales`, `Suma esperada ~${fmt(tpTotal)} tiros a puerta entre ambos (cruzado con defensas).`, poissonOver(tpTotal, Math.floor(tpLine1)))}
    ${betCard(`Más de ${fmt(tpLine2)} tiros a puerta totales`, `Línea superior del mercado.`, poissonOver(tpTotal, Math.floor(tpLine2)))}
    ${betCard(`${names.team1} más de ${Math.max(0,Math.floor(e1)-1)}.5 tiros a puerta`, `Esperados ${fmt(e1)}/p ajustados por la defensa de ${names.team2}.`, poissonOver(e1, Math.max(0,Math.floor(e1)-1)))}
    ${betCard(`${names.team2} más de ${Math.max(0,Math.floor(e2)-1)}.5 tiros a puerta`, `Esperados ${fmt(e2)}/p ajustados por la defensa de ${names.team1}.`, poissonOver(e2, Math.max(0,Math.floor(e2)-1)))}
  </div>

  <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
    <div class="team-card"><h3>${names.team1} — tiros</h3>
      <div class="stat-row"><span class="stat-label">Tiros totales/p (pond.)</span><span class="stat-val">${fmt(s1.wTiros)}</span></div>
      <div class="stat-row"><span class="stat-label">Tiros a puerta/p (histórico)</span><span class="stat-val">${fmt(s1.wTP)}</span></div>
      <div class="stat-row"><span class="stat-label">Esperados este partido</span><span class="stat-val green">${fmt(e1)}</span></div>
      <div class="stat-row"><span class="stat-label">Precisión</span><span class="stat-val">${fmt(s1.wTiros>0?s1.wTP/s1.wTiros*100:0)}%</span></div>
      <div class="stat-row"><span class="stat-label">Tiros rival recibidos/p</span><span class="stat-val red">${fmt(s1.wTPR)}</span></div>
      ${miniBar(s1.tpArr, 'var(--home)')}
    </div>
    <div class="team-card"><h3>${names.team2} — tiros</h3>
      <div class="stat-row"><span class="stat-label">Tiros totales/p (pond.)</span><span class="stat-val">${fmt(s2.wTiros)}</span></div>
      <div class="stat-row"><span class="stat-label">Tiros a puerta/p (histórico)</span><span class="stat-val">${fmt(s2.wTP)}</span></div>
      <div class="stat-row"><span class="stat-label">Esperados este partido</span><span class="stat-val green">${fmt(e2)}</span></div>
      <div class="stat-row"><span class="stat-label">Precisión</span><span class="stat-val">${fmt(s2.wTiros>0?s2.wTP/s2.wTiros*100:0)}%</span></div>
      <div class="stat-row"><span class="stat-label">Tiros rival recibidos/p</span><span class="stat-val red">${fmt(s2.wTPR)}</span></div>
      ${miniBar(s2.tpArr, 'var(--away)')}
    </div>
  </div>`;
}

// ---- COMBINADAS ----
function renderCombos(s1, s2, model) {
  const el = document.getElementById('combos-content');
  el.className = '';
  const winner = model.pH >= model.pA ? names.team1 : names.team2;
  const wp = Math.max(model.pH, model.pA);
  const fg = firstGoalProbs(model);
  const sp = shotProbs(s1, s2);
  const cp = cornerProbs(s1, s2);
  const csW1 = Math.min(0.70, s1.wWinCS * 1.08);
  const lam1H = model.lam1 * 0.44;
  const lam2H = model.lam2 * 0.44;
  const lam1S = model.lam1 * 0.56;
  const lam2S = model.lam2 * 0.56;
  const btts1T_p = (1-poissonP(lam1H,0)) * (1-poissonP(lam2H,0));
  const btts2T_p = (1-poissonP(lam1S,0)) * (1-poissonP(lam2S,0));
  // Gana ≥1 tiempo del equipo señalado como "winner" — derivado del modelo del partido
  const winnerIsHome = model.pH >= model.pA;
  const _wah = winAnyHalfProbs(model);
  const wAnyHalf = winnerIsHome ? _wah.home : _wah.away;

  const combos = [
    {
      title: `${winner} gana + Ambos anotan`,
      legs: [`${winner} gana (${pct(wp)}%)`, `Ambos equipos anotan (${pct(model.btts)}%)`],
      prob: wp * model.btts
    },
    {
      title: `+2.5 Goles + ${names.team1} marca primero`,
      legs: [`Más de 2.5 goles (${pct(model.over25)}%)`, `${names.team1} marca primero (${pct(fg.home)}%)`],
      prob: model.over25 * fg.home
    },
    {
      title: `BTTS en 1ª parte + BTTS en 2ª parte`,
      legs: [`Ambos anotan en 1T (${pct(btts1T_p)}%)`, `Ambos anotan en 2T (${pct(btts2T_p)}%)`],
      prob: Math.min(0.75, btts1T_p * btts2T_p * 1.2)
    },
    {
      title: `${winner} gana + +2.5 Goles + BTTS`,
      legs: [`${winner} gana (${pct(wp)}%)`, `+2.5 goles (${pct(model.over25)}%)`, `Ambos anotan (${pct(model.btts)}%)`],
      prob: wp * model.over25 * model.btts
    },
    {
      title: `${names.team1} gana a 0 + Más tiros a puerta`,
      legs: [`${names.team1} gana sin recibir goles (${pct(csW1)}%)`, `${names.team1} tira más a puerta (${pct(sp.home)}%)`],
      prob: csW1 * sp.home
    },
    {
      title: `${winner} gana al menos 1 parte + BTTS`,
      legs: [`${winner} gana ≥1 tiempo (${pct(wAnyHalf)}%)`, `Ambos equipos anotan (${pct(model.btts)}%)`],
      prob: wAnyHalf * model.btts
    },
    {
      title: `Más de ${fmt(cp.line1)} corners + +2.5 Goles`,
      legs: [`+${fmt(cp.line1)} corners (${pct(cp.pOver1)}%)`, `+2.5 goles (${pct(model.over25)}%)`],
      prob: cp.pOver1 * model.over25
    }
  ];

  el.innerHTML = `
  <div style="margin-bottom:14px;font-size:12px;color:var(--text-2)">
    Probabilidades combinadas asumiendo independencia entre eventos (conservador).<br>
    Solo orientativo — no refleja correlaciones reales entre mercados.
  </div>
  ${combos.map(c => {
    const prob = Math.min(0.85, Math.max(0.02, c.prob));
    const cc   = prob > 0.35 ? 'var(--accent)' : prob > 0.18 ? 'var(--warn)' : 'var(--bad)';
    const cl   = prob > 0.35 ? 'Alta' : prob > 0.18 ? 'Media' : 'Baja';
    return `<div class="combo-card">
      <div class="combo-badge">COMBINADA</div>
      <div class="combo-title">🔗 ${c.title}</div>
      <div class="combo-legs">${c.legs.map(l => `<div class="combo-leg">${l}</div>`).join('')}</div>
      <div class="combo-stats">
        <div class="combo-stat"><div class="val purple">${pct(prob)}%</div><div class="lbl">Prob. combinada</div></div>
        <div class="combo-stat"><div class="val" style="color:${cc}">${cl}</div><div class="lbl">Confianza</div></div>
      </div>
    </div>`;
  }).join('')}`;
}

// ============================================================
//  JUGADORES — STATS Y APUESTAS
// ============================================================
function aggregatePlayers(rows) {
  // Group rows by player name, compute weighted averages
  const map = {};
  rows.forEach(r => {
    const name = r.jugador || r.nombre || r.player || '?';
    if (!map[name]) map[name] = {
      name, team: r.equipo||'', pos: (r.posicion||r.pos||'').toUpperCase().slice(0,2),
      games:0, goles:0, asist:0, tiros:0, tirosPuerta:0, ta:0, tr:0, mins:0,
      rows:[]
    };
    map[name].rows.push(r);
  });
  return Object.values(map).map(p => {
    const n = p.rows.length;
    const w = weights(n);
    p.games = n;
    p.goles       = p.rows.reduce((s,r,i) => s + w[i]*(+(r.goles)||0), 0);
    p.asist       = p.rows.reduce((s,r,i) => s + w[i]*(+(r.asistencias)||0), 0);
    p.tiros       = p.rows.reduce((s,r,i) => s + w[i]*(+(r.tiros)||0), 0);
    p.tirosPuerta = p.rows.reduce((s,r,i) => s + w[i]*(+(r.tiros_puerta)||0), 0);
    p.ta          = p.rows.reduce((s,r,i) => s + w[i]*(+(r.tarjetas_a)||0), 0);
    p.tr          = p.rows.reduce((s,r,i) => s + w[i]*(+(r.tarjetas_r)||0), 0);
    p.mins        = p.rows.reduce((s,r,i) => s + w[i]*(+(r.minutos)||90), 0);
    // Probabilities (rate per game, weighted)
    p.pGoal   = Math.min(0.95, p.goles);        // already a rate 0-1 from wavg
    p.pCard   = Math.min(0.90, p.ta + p.tr*2);  // red weighs double
    p.pShot1  = Math.min(0.97, 1 - poissonP(p.tirosPuerta, 0));  // P(≥1 tiro a puerta)
    p.pShot2  = Math.min(0.90, 1 - poissonP(p.tirosPuerta, 0) - poissonP(p.tirosPuerta, 1)); // P(≥2)
    delete p.rows;
    return p;
  }).sort((a,b) => b.tirosPuerta - a.tirosPuerta); // sort by shots on target desc
}

function posLabel(pos) {
  const map = {GK:'GK',DF:'DF',DE:'DF',CB:'DF',LB:'DF',RB:'DF',MF:'MF',CM:'MF',DM:'MF',AM:'MF',FW:'FW',ST:'FW',LW:'FW',RW:'FW'};
  return map[pos] || pos || '—';
}

function playerBetCard(player, market, prob, teamColor) {
  prob = Math.min(0.97, Math.max(0.03, prob));
  const cc = confClass(prob), cl = confLabel(prob);
  const betKey = `${player.name} · ${market}`;
  const key = betKey.replace(/"/g, '&quot;');
  const isChecked = betChecked.has(betKey);
  return `<div class="player-bet-card ${cc}${isChecked ? ' bet-done' : ''}">
    <div class="pb-name">${player.name}</div>
    <div class="pb-team" style="color:${teamColor}">${player.team} · ${posLabel(player.pos)}</div>
    <div class="pb-market">${market}</div>
    <div class="pb-bar-bg"><div class="pb-bar-fill ${cc}" style="width:${pct(prob)}%;height:4px;border-radius:3px;background:${cc==='high'?'var(--accent)':cc==='medium'?'var(--warn)':'var(--text-3)'}"></div></div>
    <div class="pb-footer">
      <span style="color:var(--text-0)">Prob: <strong style="color:var(--text-1)">${pct(prob)}%</strong></span>
      <label class="bet-check" onclick="event.stopPropagation()">
        <input type="checkbox" ${isChecked ? 'checked' : ''} onchange="toggleBetCheck('${key.replace(/'/g,"\\'")}');this.closest('.player-bet-card').classList.toggle('bet-done',this.checked)">
        <span class="bet-check-box"></span>
        <span class="bet-check-label">Hecha</span>
      </label>
    </div>
  </div>`;
}

function playerTableHTML(aggPlayers, teamColor) {
  const sorted = [...aggPlayers].sort((a,b) => b.tirosPuerta - a.tirosPuerta);
  return `<table class="player-table">
    <thead><tr>
      <th>Jugador</th>
      <th>Pos</th>
      <th title="Partidos">PJ</th>
      <th title="Goles/partido (pond.)">Goles/p</th>
      <th title="Asistencias/partido (pond.)">Asist/p</th>
      <th title="Tiros totales/partido">Tiros/p</th>
      <th title="Tiros a puerta/partido">T.Puerta/p</th>
      <th title="Tarjetas amarillas/partido">TA/p</th>
      <th title="Tarjetas rojas/partido">TR/p</th>
    </tr></thead>
    <tbody>${sorted.map(p => {
      const pos = posLabel(p.pos);
      return `<tr>
        <td class="player-name-cell">${p.name}<span class="player-pos pos-${pos}" style="background:${teamColor}22;color:${teamColor}">${pos}</span></td>
        <td>${pos}</td>
        <td>${p.games}</td>
        <td>${p.goles > 0.15 ? `<span class="stat-pill pill-green">${fmt(p.goles)}</span>` : fmt(p.goles)}</td>
        <td>${p.asist > 0.10 ? `<span class="stat-pill pill-blue">${fmt(p.asist)}</span>` : fmt(p.asist)}</td>
        <td>${fmt(p.tiros)}</td>
        <td>${p.tirosPuerta > 1.5 ? `<span class="stat-pill pill-blue">${fmt(p.tirosPuerta)}</span>` : fmt(p.tirosPuerta)}</td>
        <td>${p.ta > 0.25 ? `<span class="stat-pill pill-yellow">${fmt(p.ta)}</span>` : fmt(p.ta)}</td>
        <td>${p.tr > 0.05 ? `<span class="stat-pill pill-red">${fmt(p.tr)}</span>` : fmt(p.tr)}</td>
      </tr>`;
    }).join('')}</tbody>
  </table>`;
}

function renderPlayers() {
  const el = document.getElementById('players-content');
  if (!players.team1 && !players.team2) return;
  el.className = '';

  const agg1 = players.team1 ? aggregatePlayers(players.team1) : [];
  const agg2 = players.team2 ? aggregatePlayers(players.team2) : [];

  // Top scorers bets — anota en el partido
  const topScorers = [...agg1.map(p=>({...p,_color:'var(--home)'})), ...agg2.map(p=>({...p,_color:'var(--away)'}))]
    .filter(p => p.pGoal > 0.05)
    .sort((a,b) => b.pGoal - a.pGoal)
    .slice(0, 8);

  // Top cards bets
  const topCards = [...agg1.map(p=>({...p,_color:'var(--home)'})), ...agg2.map(p=>({...p,_color:'var(--away)'}))]
    .filter(p => p.pCard > 0.05)
    .sort((a,b) => b.pCard - a.pCard)
    .slice(0, 8);

  // Top shots bets
  const topShots = [...agg1.map(p=>({...p,_color:'var(--home)'})), ...agg2.map(p=>({...p,_color:'var(--away)'}))]
    .filter(p => p.pShot1 > 0.10)
    .sort((a,b) => b.pShot1 - a.pShot1)
    .slice(0, 8);

  el.innerHTML = `
  <div class="loaded-badge">👤 ${agg1.length + agg2.length} jugadores analizados · ponderación temporal activa</div>

  ${agg1.length ? `<div class="player-team-block">
    <div class="player-team-title"><span style="color:var(--home)">🏠</span> ${names.team1} — Estadísticas por jugador</div>
    <div style="overflow-x:auto">${playerTableHTML(agg1, 'var(--home)')}</div>
  </div>` : ''}

  ${agg2.length ? `<div class="player-team-block">
    <div class="player-team-title"><span style="color:var(--away)">✈️</span> ${names.team2} — Estadísticas por jugador</div>
    <div style="overflow-x:auto">${playerTableHTML(agg2, 'var(--away)')}</div>
  </div>` : ''}

  <div class="bets-section-title">🎯 Jugador anota en el partido</div>
  <div class="player-bet-grid">
    ${topScorers.map(p => playerBetCard(p, 'Anota en el partido', p.pGoal, p._color)).join('')}
  </div>

  <div class="bets-section-title">🟨 Jugador recibe tarjeta</div>
  <div class="player-bet-grid">
    ${topCards.map(p => playerBetCard(p, 'Recibe tarjeta (amarilla o roja)', p.pCard, p._color)).join('')}
  </div>

  <div class="bets-section-title">🥅 Jugador tira a puerta</div>
  <div class="player-bet-grid">
    ${topShots.map(p => playerBetCard(p, '1+ tiro a puerta', p.pShot1, p._color)).join('')}
    ${topShots.map(p => playerBetCard(p, '2+ tiros a puerta', p.pShot2, p._color)).join('')}
  </div>`;
}

// ============================================================
//  MÓDULO DE VALIDACIÓN (BACKTEST MANUAL)
//  El usuario añade partidos ya disputados. Para cada uno el modelo
//  PREDICE (usando solo la base CSV + fuerza FIFA del rival + sede)
//  cuántos goles esperaba y qué resultado, y se compara con lo real.
//  Los partidos más recientes pesan más (decaimiento gradual).
// ============================================================

// Predice el desempeño de un equipo (con stats base s) contra un rival
// representado solo por su ranking FIFA, en una sede dada.
function predictTeamMatch(s, sede, rivalRank) {
  // Ataque/defensa base según sede (usa el split local/visitante si existe)
  let baseGF, baseGC;
  if (sede === 'local' && s.wGF_local !== null) {
    baseGF = s.wGF_local; baseGC = s.wGC_local !== null ? s.wGC_local : s.wGC;
  } else if (sede === 'away' && s.wGF_away !== null) {
    baseGF = s.wGF_away; baseGC = s.wGC_away !== null ? s.wGC_away : s.wGC;
  } else {
    baseGF = s.wGF; baseGC = s.wGC;
  }

  // Ajuste por sede (ventaja local empírica del propio equipo)
  const homeAdv = s.empiricalHomeAdv || 1.15;
  let sedeAtk = 1, sedeDef = 1;
  if (sede === 'local')      { sedeAtk = homeAdv;            sedeDef = 1; }
  else if (sede === 'away')  { sedeAtk = 1 / Math.sqrt(homeAdv); sedeDef = Math.sqrt(homeAdv); }
  // neutral → 1 / 1

  // Fuerza del rival desde FIFA: 0 = muy débil, 1 = top mundial.
  // Comparada contra la dificultad media del calendario base del equipo.
  const rivalStrength = (FIFA_MAX_RANK - rivalRank) / FIFA_MAX_RANK;
  const baseSched = (typeof s.scheduleStrength === 'number') ? s.scheduleStrength : 0.5;
  const diff = rivalStrength - baseSched; // >0 → rival más duro que lo habitual

  // Peso FIFA sobre la predicción del partido (35%, como en buildModel)
  const FIFA_W = 0.35;
  // Rival más fuerte → marcamos menos y recibimos más
  const rivalDefAdj = Math.max(0.55, Math.min(1.45, 1 - FIFA_W * diff));
  const rivalAtkAdj = Math.max(0.55, Math.min(1.45, 1 + FIFA_W * diff));

  // Momentum gradual del propio equipo
  const tf = Math.min(1.20, Math.max(0.85, 1 + 0.10 * ((s.trendGF || 1) - 1)));

  const lamFor     = Math.max(0.25, baseGF * sedeAtk * rivalDefAdj * tf);
  const lamAgainst = Math.max(0.25, baseGC * sedeDef * rivalAtkAdj);

  // #4: ρ dinámico desde el historial del propio equipo (el rival solo lo
  // tenemos vía FIFA, sin sus goles, así que estimamos con un solo lado).
  let rhoVal = DC_RHO;
  const gfA = s.gfArr || [], gcA = s.gcArr || [];
  if (gfA.length >= 10) {
    let obs00 = 0;
    for (let i = 0; i < gfA.length; i++) if (gfA[i] === 0 && gcA[i] === 0) obs00++;
    const obsRate = obs00 / gfA.length;
    const expRate = poissonP(lamFor, 0) * poissonP(lamAgainst, 0);
    if (expRate > 0) rhoVal = Math.max(-0.20, Math.min(0, -0.13 * (obsRate / expRate)));
  }

  // Matriz Poisson + Dixon-Coles para P(W/D/L)
  const mat = applyDixonColes(scoreMatrix(lamFor, lamAgainst, 7), lamFor, lamAgainst, rhoVal);
  let pW = 0, pD = 0, pL = 0;
  for (let h = 0; h <= 7; h++)
    for (let a = 0; a <= 7; a++) {
      const p = mat[h][a];
      if (h > a) pW += p; else if (h === a) pD += p; else pL += p;
    }
  return { lamFor, lamAgainst, pW, pD, pL, rivalStrength };
}

// Calcula el resultado W/D/L a partir de goles
function outcomeOf(gf, gc) { return gf > gc ? 'W' : gf === gc ? 'D' : 'L'; }

// Evalúa un partido añadido: compara predicción vs realidad
function evaluateValMatch(s, m) {
  const sede = parseSede(m.sede);
  const _lk = lookupFIFA((m.rival || '').trim());
  const rivalRank = _lk ? _lk.rank : FIFA_UNKNOWN_RANK;
  const pred = predictTeamMatch(s, sede, rivalRank);

  const gf = +m.goles_f || 0, gc = +m.goles_c || 0;
  const actualOutcome = outcomeOf(gf, gc);
  const predProbs = { W: pred.pW, D: pred.pD, L: pred.pL };
  const predOutcome = pred.pW >= pred.pD && pred.pW >= pred.pL ? 'W'
                    : pred.pD >= pred.pL ? 'D' : 'L';

  // Error en goles (predicho vs real)
  const errFor     = Math.abs(pred.lamFor - gf);
  const errAgainst = Math.abs(pred.lamAgainst - gc);
  const goalMAE = (errFor + errAgainst) / 2;

  // Brier multiclase (0 = perfecto, 2 = pésimo)
  const oneHot = { W: actualOutcome==='W'?1:0, D: actualOutcome==='D'?1:0, L: actualOutcome==='L'?1:0 };
  const brier = ['W','D','L'].reduce((s2,k) => s2 + (predProbs[k]-oneHot[k])**2, 0);

  // Clasificación visual del acierto
  const probOfActual = predProbs[actualOutcome];
  let grade;
  if (predOutcome === actualOutcome) grade = 'hit';        // acertó el resultado
  else if (probOfActual >= 0.30) grade = 'close';          // no acertó pero le daba opción real
  else grade = 'miss';

  return {
    sede, rivalRank, rivalStrength: pred.rivalStrength,
    predFor: pred.lamFor, predAgainst: pred.lamAgainst,
    predProbs, predOutcome, actualOutcome,
    gf, gc, goalMAE, brier, probOfActual, grade
  };
}

function valTeamName(t) { return t === 1 ? names.team1 : names.team2; }
function valTeamColor(t) { return t === 1 ? 'var(--home)' : 'var(--away)'; }
function valTeamStats(t) {
  const data = t === 1 ? state.team1 : state.team2;
  return data ? computeStats(data) : null;
}

// Stats aumentadas para validación incremental:
// para predecir el partido en el índice i (0 = más reciente), usamos
// la base CSV + los partidos de validación ANTERIORES a él (más antiguos),
// nunca el propio partido i. Así cada predicción sigue siendo a ciegas.
function valAugmentedStats(t, i) {
  const base = (t === 1 ? state.team1 : state.team2) || [];
  const list = valMatches['team'+t];
  // list[i+1..end] son los más antiguos que el partido i (orden: reciente→antiguo)
  const priorVal = list.slice(i + 1);
  // Combinado en orden temporal correcto: validación previa (más reciente primero) + base
  const combined = [...priorVal, ...base];
  return computeStats(combined);
}

function setValTeam(t) { valActiveTeam = t; renderValidation(); }

function toggleValOptional() {
  document.getElementById('val-optional').classList.toggle('show');
  const t = document.getElementById('val-optional-toggle');
  if (t) t.textContent = document.getElementById('val-optional').classList.contains('show')
    ? '▲ Ocultar campos avanzados' : '▼ Añadir campos avanzados (1T/2T, tiros, corners, tarjetas)';
}

function previewRival() {
  const el = document.getElementById('val-rival-preview');
  if (!el) return;
  const name = document.getElementById('val-rival').value.trim();
  if (!name) { el.textContent = ''; el.className = 'val-rival-preview'; return; }
  const _lk = lookupFIFA(name);
  if (_lk) {
    el.textContent = `✓ ${_lk.pais} · FIFA #${_lk.rank}`;
    el.className = 'val-rival-preview found';
  } else {
    el.textContent = `⚠️ No está en el top 120 — se tratará como rival débil (#${FIFA_UNKNOWN_RANK})`;
    el.className = 'val-rival-preview unknown';
  }
}

function addValMatch() {
  const t = valActiveTeam;
  const list = valMatches['team'+t];
  if (list.length >= VAL_MAX) return;

  const g = id => document.getElementById('val-'+id);
  const rival = g('rival').value.trim();
  const sede  = g('sede').value;
  const gf    = g('gf').value;
  const gc    = g('gc').value;

  if (!rival) { g('rival').focus(); return; }
  if (gf === '' || gc === '') { (gf===''?g('gf'):g('gc')).focus(); return; }

  const gfN = Math.max(0, +gf), gcN = Math.max(0, +gc);
  const opt = id => { const v = g(id) ? g(id).value : ''; return v === '' ? '' : Math.max(0, +v); };

  const match = {
    fecha: new Date().toISOString().slice(0,10),
    equipo: valTeamName(t),
    rival, sede,
    goles_f: gfN, goles_c: gcN,
    goles_1t_f: opt('g1f'), goles_1t_c: opt('g1c'),
    goles_2t_f: opt('g2f'), goles_2t_c: opt('g2c'),
    tiros: opt('tiros'), tiros_rival: opt('tirosr'),
    tiros_puerta: opt('tp'), tiros_puerta_rival: opt('tpr'),
    corners: opt('corners'), corners_rival: opt('cornersr'),
    tarjetas_a: opt('ta'), tarjetas_r: opt('tr'),
    asistencias: opt('asist'),
    resultado: outcomeOf(gfN, gcN)
  };
  // Más reciente primero
  list.unshift(match);
  renderValidation();
}

function deleteValMatch(t, i) {
  valMatches['team'+t].splice(i, 1);
  renderValidation();
}

// ---- PROMOVER a la base (mover, no copiar) ----
// Regla de oro: el partido sale del banco de pruebas y entra a la base CSV
// como el más reciente. A partir de ahí afecta la predicción principal
// (Análisis/Apuestas) pero ya no se sigue calificando como validación.
function promoteValMatch(t, i) {
  const list = valMatches['team'+t];
  if (i < 0 || i >= list.length) return;
  // Promover en orden cronológico: primero los más antiguos, para que
  // el orden temporal de la base quede coherente (índice 0 = más reciente).
  // Aquí promovemos uno solo: lo insertamos al frente de la base.
  const match = list.splice(i, 1)[0];
  const key = 'team'+t;
  if (!state[key]) state[key] = [];
  state[key].unshift(match); // más reciente primero
  syncTeamToLibrary(t);      // actualiza la biblioteca si el equipo está guardado
  renderAll(); // recalcula TODO el modelo, incluida la predicción principal
}

function promoteAllVal(t) {
  const list = valMatches['team'+t];
  if (!list.length) return;
  const key = 'team'+t;
  if (!state[key]) state[key] = [];
  // list está en orden reciente→antiguo. Para mantener ese orden al frente
  // de la base, insertamos del más antiguo al más reciente.
  for (let j = list.length - 1; j >= 0; j--) {
    state[key].unshift(list[j]);
  }
  valMatches[key] = []; // se vacía el banco de pruebas
  syncTeamToLibrary(t);
  renderAll();
}

// Si el equipo cargado coincide con uno guardado en la biblioteca,
// actualiza su base ahí para que las promociones persistan.
function syncTeamToLibrary(t) {
  const nm = names['team'+t];
  if (nm && teamLibrary[nm] !== undefined) {
    teamLibrary[nm] = { rows: state['team'+t].slice(), savedAt: new Date().toISOString() };
    persistLibrary();
    renderLibrary();
    libStatus(`💾 Base de "${nm}" actualizada en la biblioteca`);
  }
}

function exportValMatches() {
  const t = valActiveTeam;
  const list = valMatches['team'+t];
  if (!list.length) return;
  const cols = ['fecha','equipo','rival','sede','goles_f','goles_c','goles_1t_f','goles_1t_c',
    'goles_2t_f','goles_2t_c','tiros','tiros_rival','tiros_puerta','tiros_puerta_rival',
    'corners','corners_rival','tarjetas_a','tarjetas_r','asistencias','resultado','xg_f','xg_c'];
  // Exportar del más antiguo al más reciente (orden cronológico natural)
  const ordered = [...list].reverse();
  const header = cols.join(',');
  const lines = ordered.map(m => cols.map(c => m[c] === '' || m[c] == null ? '' : m[c]).join(','));
  const csv = [header, ...lines].join('\n');
  const blob = new Blob([csv], {type:'text/csv'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `validacion_${valTeamName(t).replace(/\s+/g,'_')}.csv`;
  a.click();
}

// ============================================================
//  #9 RENDIMIENTO DE APUESTAS — registro y calibración
//  Sustituye al antiguo backtest de goles. Por cada partido REAL que el
//  usuario introduce, evalúa TODAS las apuestas que generó el modelo
//  (acierto/fallo) y las acumula en un registro global persistente. Luego
//  agrega los resultados (1) por franja de probabilidad → calibración y
//  (2) por mercado → qué tipos de apuesta se cumplen más. Filtrable por
//  equipo o liga.
// ============================================================
const BETLOG_KEY = 'fba_betlog_v1';
const BETLOGMETA_KEY = 'fba_betlogmeta_v1';
let betLog = [];               // [{ts, date?, team1, team2, league, market, icon, label, prob, hit, mine?, odds?}]
let betLogMeta = {};           // {ts: {a, league, date, team1, team2}} → permite EDITAR registros
let regEditTs = null;          // ts del registro en edición (null = alta normal)
// #7 Filtros COMBINABLES (antes: solo equipo O liga)
let betLogFilter = { team:'all', league:'all', market:'all', period:'all' };
let regFlash = '';             // mensaje efímero tras registrar
let mktExpanded = {};          // qué mercados están desplegados en "Acierto por mercado"

const MARKET_ORDER = ['1X2','Goles','BTTS','Córners','Tiros a puerta','Tiros','Tarjetas','Mitades'];

// Extrae el valor numérico de línea de una etiqueta ("Más de 5.5" → 5.5).
// Devuelve null si no hay número (ej. "Gana Local", "Empate", "BTTS Sí").
function lineVal(label) {
  const m = String(label).match(/-?\d+(?:[.,]\d+)?/);
  return m ? parseFloat(m[0].replace(',', '.')) : null;
}

async function loadBetLog() {
  try {
    const resp = await fetch(API.cargarApuestas, { headers:{'X-Requested-With':'fetch'} });
    const data = await resp.json();
    betLog = data.betLog || [];
    betLogMeta = data.betLogMeta || {};
  } catch (e) { betLog = []; betLogMeta = {}; }
}
function saveBetLog() {
  // Persiste el registro (apuestas + metadatos) en MySQL en segundo plano.
  try {
    fetch(API.guardarApuestas, {
      method:'POST',
      headers:{'Content-Type':'application/json','X-CSRFToken':getCsrf()},
      body: JSON.stringify({ betLog, betLogMeta })
    });
  } catch (e) {}
  _calibFit = null; _calibCVRes = null; // el historial cambió → recalcular calibración
}

// ============================================================
//  #4 LOOP DE CALIBRACIÓN v2 — el registro corrige al modelo
//  Antes: deciles globales (todos los mercados mezclados, sin ajuste hasta
//  n ≥ 30 POR franja y con saltos en los bordes). Ahora:
//  (1) Recalibración logística suave (Platt): p' = σ(a + b·logit(p)).
//      Usa TODO el historial a la vez y varía de forma continua con p.
//  (2) JERÁRQUICA por mercado: cada mercado (1X2, Córners, Tarjetas…) ajusta
//      sus propios (a,b) con prior hacia el ajuste global — con pocos
//      registros hereda la corrección global, con muchos manda su sesgo.
//  (3) Peso por recencia: semivida CALIB_HALFLIFE_D días.
//  (4) calibCV(): validación cruzada por partido que comprueba con TUS
//      registros si la corrección de verdad mejora el Brier score.
//  Salvaguardas: solo actúa con n ≥ CALIB_MIN_N total, desplazamiento
//  acotado (±CALIB_MAX_SHIFT) y prob final en [0.02, 0.98].
//  IMPORTANTE: betLog guarda SIEMPRE la prob. CRUDA del modelo (si guardara la
//  ajustada, la calibración se retroalimentaría a sí misma). El ajuste es capa
//  de LECTURA: se muestra junto a la cruda en las tarjetas de apuesta.
// ============================================================
const CALIB_MIN_N = 30;        // apuestas mínimas en el registro para activar
const CALIB_PRIOR = 10;        // fuerza del prior (≈ apuestas "imaginarias" que anclan identidad/global)
const CALIB_MAX_SHIFT = 0.15;  // desplazamiento máximo sobre la prob cruda
const CALIB_HALFLIFE_D = 270;  // semivida del peso por antigüedad (días)
let _calibFit = null;          // cache del ajuste (null = recalcular, false = muestra insuficiente)
let _calibCVRes = null;        // cache de la validación cruzada

const _logit = p => { const q = Math.min(0.98, Math.max(0.02, p)); return Math.log(q / (1 - q)); };
const _sigm  = z => 1 / (1 + Math.exp(-z));

// Mercado del registro al que pertenece una tarjeta de Apuestas, deducido del
// nombre (las secciones mezclan mercados: "Tiros" tiene tiros y tiros a
// puerta, "Goles" incluye BTTS…). null = sin mercado claro → ajuste global.
function marketOfBet(name) {
  const s = String(name).toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  if (/\sy\s/.test(s)) return null;          // combinadas: mezclan mercados
  if (/gana a 0/.test(s)) return null;       // victoria + portería a cero: mixto
  if (/tir/.test(s)) return /puerta/.test(s) ? 'Tiros a puerta' : 'Tiros';
  if (/corner/.test(s)) return 'Córners';
  if (/tarjeta/.test(s)) return 'Tarjetas';
  if (/parte|mitad/.test(s)) return 'Mitades';
  if (/ambos anotan|btts/.test(s)) return 'BTTS';
  if (/gol/.test(s)) return 'Goles';
  if (/gana|empate/.test(s)) return '1X2';
  return null;
}

// Filas del registro con peso por recencia (los registros viejos pesan menos:
// tus datos y el contexto de los equipos cambian con el tiempo).
function _calibRows() {
  const now = Date.now();
  return betLog.map(r => {
    const t = r.date ? Date.parse(r.date + 'T12:00:00') : r.ts;
    const age = Math.max(0, (now - (isFinite(t) ? t : now)) / 86400000);
    return { ts: r.ts, market: r.market, prob: r.prob, hit: !!r.hit,
             w: Math.pow(2, -age / CALIB_HALFLIFE_D) };
  });
}

// Ajusta (a,b) de p' = σ(a + b·logit(p)) minimizando log-loss ponderado con
// prior gaussiano hacia (a0,b0) de fuerza `prior` (Newton-Raphson 2×2).
// El prior evita ajustes salvajes con pocos datos y la separación perfecta.
function _fitPlatt(rows, a0, b0, prior) {
  let a = a0, b = b0;
  for (let it = 0; it < 25; it++) {
    let ga = prior * (a - a0), gb = prior * (b - b0);
    let haa = prior, hab = 0, hbb = prior;
    for (const r of rows) {
      const z = _logit(r.prob), mu = _sigm(a + b * z);
      const d = r.w * (mu - (r.hit ? 1 : 0)), v = r.w * mu * (1 - mu);
      ga += d; gb += d * z;
      haa += v; hab += v * z; hbb += v * z * z;
    }
    const det = haa * hbb - hab * hab;
    if (!isFinite(det) || Math.abs(det) < 1e-9) break;
    const da = (hbb * ga - hab * gb) / det, db = (haa * gb - hab * ga) / det;
    a -= da; b -= db;
    a = Math.max(-2.5, Math.min(2.5, a));
    b = Math.max(0.2, Math.min(3, b));
    if (Math.abs(da) < 1e-6 && Math.abs(db) < 1e-6) break;
  }
  return { a, b };
}

// Ajuste completo: global (prior → identidad) + por mercado (prior → global).
function _calibFitRows(rows) {
  const g = _fitPlatt(rows, 0, 1, CALIB_PRIOR);
  const byM = {};
  rows.forEach(r => { (byM[r.market] = byM[r.market] || []).push(r); });
  const mkt = {};
  Object.keys(byM).forEach(m => {
    const f = _fitPlatt(byM[m], g.a, g.b, CALIB_PRIOR);
    mkt[m] = { a: f.a, b: f.b, n: byM[m].length };
  });
  return { global: { a: g.a, b: g.b, n: rows.length }, mkt };
}

function calibFit() {
  if (_calibFit !== null) return _calibFit === false ? null : _calibFit;
  if (betLog.length < CALIB_MIN_N) { _calibFit = false; return null; }
  return (_calibFit = _calibFitRows(_calibRows()));
}

// Aplica un ajuste con las salvaguardas (tope de desplazamiento + clamps).
function _applyCalib(fit, p, market) {
  const f = (market && fit.mkt[market]) ? fit.mkt[market] : fit.global;
  const adj = _sigm(f.a + f.b * _logit(p));
  const capped = Math.max(p - CALIB_MAX_SHIFT, Math.min(p + CALIB_MAX_SHIFT, adj));
  return Math.max(0.02, Math.min(0.98, capped));
}

// Probabilidad ajustada por el historial (o null si aún no hay muestra).
// `market` opcional: usa la corrección específica del mercado si existe.
function calibrateProb(p, market) {
  const fit = calibFit();
  return fit ? _applyCalib(fit, p, market || null) : null;
}

// ¿La calibración MEJORA de verdad? Validación cruzada 5-fold por PARTIDO
// (las apuestas de un mismo partido van juntas al mismo fold: están
// correlacionadas y separarlas inflaría el resultado). Compara el Brier de
// la prob cruda vs la calibrada SOLO sobre partidos que el ajuste no vio.
function calibCV() {
  if (_calibCVRes !== null) return _calibCVRes === false ? null : _calibCVRes;
  const rows = _calibRows();
  const matchTs = [...new Set(rows.map(r => r.ts))].sort((x, y) => x - y);
  if (rows.length < CALIB_MIN_N || matchTs.length < 6) { _calibCVRes = false; return null; }
  const K = 5, foldOf = {};
  matchTs.forEach((t, i) => { foldOf[t] = i % K; });
  let sqRaw = 0, sqCal = 0, n = 0;
  for (let f = 0; f < K; f++) {
    const train = rows.filter(r => foldOf[r.ts] !== f);
    const test  = rows.filter(r => foldOf[r.ts] === f);
    if (!train.length || !test.length) continue;
    const fit = _calibFitRows(train);
    for (const r of test) {
      const y = r.hit ? 1 : 0;
      sqRaw += Math.pow(r.prob - y, 2);
      sqCal += Math.pow(_applyCalib(fit, r.prob, r.market) - y, 2);
      n++;
    }
  }
  _calibCVRes = n ? { n, brierRaw: sqRaw / n, brierCal: sqCal / n } : false;
  return _calibCVRes === false ? null : _calibCVRes;
}

// ---- #5 Vínculo "Apuesta hecha" ↔ betLog ----
// Las tarjetas de Apuestas y las specs del registro nombran igual el mismo
// evento pero con distinto orden ("Más de 8.5 tiros..." vs "Tiros... +8.5").
// Se comparan como CONJUNTO de tokens normalizados (sin acentos ni conectores).
function betNormKey(s) {
  return String(s).toLowerCase()
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .replace(/\+/g, ' ').replace(/[^a-z0-9. ]/g, ' ')
    .split(/\s+/)
    .filter(t => t && !['de','del','la','el','los','las','mas','en','y','o'].includes(t))
    .sort().join('|');
}

// Genera las apuestas del partido como objetos RESOLUBLES contra el resultado
// real. Cada una trae su probabilidad del modelo y una función resolve(a) que
// devuelve true/false (acierto/fallo) o null si falta el dato real necesario
// (así, si solo metes el marcador, solo se evalúan los mercados de goles).
function buildBetSpecs(s1, s2, model) {
  const specs = [];
  const N = names;
  // Generador de líneas "Más de X.5" con la misma banda de casa de apuestas.
  // Si se pasa varr (>mu) usa binomial negativa (sobredispersión); si no, Poisson.
  const overSet = (mu, market, icon, label, getVal, varr) => {
    const base = Math.round(mu); const arr = [];
    for (let k = base + 2; k >= 0; k--) {
      const p = (varr && varr > mu) ? nbOver(mu, varr, k) : poissonOver(mu, k);
      arr.push({ market, icon, label: `${label} +${k}.5`, prob: p,
        resolve: a => { const v = getVal(a); return (v == null) ? null : (v > k + 0.5); } });
      if (p >= 0.90 && k <= base) break;
    }
    const band = arr.filter(b => b.prob <= LINE_PMAX && b.prob >= LINE_PMIN);
    return band.length >= 2 ? band
      : [...arr].sort((x, y) => Math.abs(x.prob - 0.5) - Math.abs(y.prob - 0.5)).slice(0, 3);
  };
  // Prob. exacta de goles totales desde la matriz Dixon-Coles del modelo.
  const goalsOver = line => {
    let p = 0; const m = model.mat;
    for (let i = 0; i < m.length; i++) for (let j = 0; j < m[i].length; j++) if (i + j > line) p += m[i][j];
    return p;
  };

  // --- 1X2 + doble oportunidad ---
  specs.push({ market:'1X2', icon:'🏆', label:`Gana ${N.team1}`, prob:model.pH, resolve:a=>a.gf>a.gc });
  specs.push({ market:'1X2', icon:'🏆', label:'Empate', prob:model.pD, resolve:a=>a.gf===a.gc });
  specs.push({ market:'1X2', icon:'🏆', label:`Gana ${N.team2}`, prob:model.pA, resolve:a=>a.gf<a.gc });
  specs.push({ market:'1X2', icon:'🏆', label:`${N.team1} o empate (1X)`, prob:model.pH+model.pD, resolve:a=>a.gf>=a.gc });
  specs.push({ market:'1X2', icon:'🏆', label:`${N.team2} o empate (X2)`, prob:model.pD+model.pA, resolve:a=>a.gf<=a.gc });
  specs.push({ market:'1X2', icon:'🏆', label:'Sin empate (12)', prob:model.pH+model.pA, resolve:a=>a.gf!==a.gc });

  // --- Goles totales (líneas con banda) ---
  {
    const base = Math.round(model.lamTotal); const arr = [];
    for (let k = base + 2; k >= 0; k--) {
      const p = goalsOver(k + 0.5);
      arr.push({ market:'Goles', icon:'⚽', label:`Más de ${k}.5 goles`, prob:p, resolve:a=>(a.gf+a.gc)>k+0.5 });
      if (p >= 0.90 && k <= base) break;
    }
    const band = arr.filter(b => b.prob <= LINE_PMAX && b.prob >= LINE_PMIN);
    (band.length >= 2 ? band : [...arr].sort((x,y)=>Math.abs(x.prob-0.5)-Math.abs(y.prob-0.5)).slice(0,3))
      .forEach(b => specs.push(b));
  }

  // --- BTTS ---
  specs.push({ market:'BTTS', icon:'🤝', label:'Ambos anotan', prob:model.btts, resolve:a=>a.gf>0&&a.gc>0 });
  specs.push({ market:'BTTS', icon:'🤝', label:'No ambos anotan', prob:1-model.btts, resolve:a=>!(a.gf>0&&a.gc>0) });

  // --- Córners ---
  const cp = cornerProbs(s1, s2);
  overSet(cp.mu,  'Córners','🚩','Córners totales', a => (a.cf!=null&&a.cc!=null)?(a.cf+a.cc):null, cp.varr).forEach(b=>specs.push(b));
  overSet(cp.exp1,'Córners','🚩',`Córners ${N.team1}`, a => a.cf).forEach(b=>specs.push(b));
  overSet(cp.exp2,'Córners','🚩',`Córners ${N.team2}`, a => a.cc).forEach(b=>specs.push(b));

  // --- Tiros a puerta ---
  const sh = expectedShots(s1, s2);
  const tpFano = (() => {
    const f = [];
    if (s1.wTPTotal > 0 && s1.varTPTot != null) f.push(s1.varTPTot / s1.wTPTotal);
    if (s2.wTPTotal > 0 && s2.varTPTot != null) f.push(s2.varTPTot / s2.wTPTotal);
    return f.length ? Math.min(3, Math.max(1, f.reduce((a,b)=>a+b,0)/f.length)) : 1;
  })();
  overSet(sh.exp1+sh.exp2,'Tiros a puerta','🎯','Tiros a puerta totales', a => (a.tf!=null&&a.tc!=null)?(a.tf+a.tc):null, (sh.exp1+sh.exp2)*tpFano).forEach(b=>specs.push(b));
  overSet(sh.exp1,'Tiros a puerta','🎯',`T. a puerta ${N.team1}`, a => a.tf).forEach(b=>specs.push(b));
  overSet(sh.exp2,'Tiros a puerta','🎯',`T. a puerta ${N.team2}`, a => a.tc).forEach(b=>specs.push(b));
  specs.push({ market:'Tiros a puerta', icon:'🎯', label:`${N.team1} tira más a puerta`,
    prob: sh.exp1/(sh.exp1+sh.exp2), resolve:a=>(a.tf!=null&&a.tc!=null)?(a.tf>a.tc):null });

  // --- Tiros totales (normales) ---
  const acc1 = s1.wTiros>0 ? Math.min(0.65,Math.max(0.25,s1.wTP/s1.wTiros)) : 0.38;
  const acc2 = s2.wTiros>0 ? Math.min(0.65,Math.max(0.25,s2.wTP/s2.wTiros)) : 0.38;
  const st1 = sh.exp1/acc1, st2 = sh.exp2/acc2;
  const stFano = (() => {
    const f = [];
    if (s1.wTirosTotal > 0 && s1.varTirosTot != null) f.push(s1.varTirosTot / s1.wTirosTotal);
    if (s2.wTirosTotal > 0 && s2.varTirosTot != null) f.push(s2.varTirosTot / s2.wTirosTotal);
    return f.length ? Math.min(3, Math.max(1, f.reduce((a,b)=>a+b,0)/f.length)) : 1;
  })();
  overSet(st1+st2,'Tiros','💥','Tiros totales', a => (a.sf!=null&&a.sc!=null)?(a.sf+a.sc):null, (st1+st2)*stFano).forEach(b=>specs.push(b));
  overSet(st1,'Tiros','💥',`Tiros ${N.team1}`, a => a.sf).forEach(b=>specs.push(b));
  overSet(st2,'Tiros','💥',`Tiros ${N.team2}`, a => a.sc).forEach(b=>specs.push(b));

  // --- Tarjetas (binomial negativa: el mercado más sobredisperso) ---
  const cards = cardProbs(s1, s2);
  overSet(cards.mu,'Tarjetas','🟨','Tarjetas totales', a => a.cards, cards.varr).forEach(b=>specs.push(b));

  // --- Mitades: DERIVADAS DE λ DEL PARTIDO (consistente con 1X2/goles) ---
  // Antes: promedio de tasas históricas de cada equipo — ignoraba al rival de
  // este partido y podía contradecir el modelo. Ahora: reparto típico de goles
  // por mitades (45% en 1ª, 55% en 2ª) sobre λ total → P(gol) = 1 - e^(-λ·share).
  {
    const lamT = model.lamTotal;
    const SHARE_1T = 0.45, SHARE_2T = 0.55;
    specs.push({ market:'Mitades', icon:'⏱️', label:'Gol en 1ª parte',
      prob: Math.min(0.97, 1 - Math.exp(-lamT * SHARE_1T)),
      resolve:a=>(a.g1f!=null&&a.g1c!=null)?((a.g1f+a.g1c)>0):null });
    specs.push({ market:'Mitades', icon:'⏱️', label:'Gol en 2ª parte',
      prob: Math.min(0.97, 1 - Math.exp(-lamT * SHARE_2T)),
      resolve:a=>(a.g1f!=null&&a.g1c!=null)?(((a.gf-a.g1f)+(a.gc-a.g1c))>0):null });
  }

  return specs;
}

// Lee el formulario, evalúa todas las apuestas y las añade al registro global.
function registerMatchResult() {
  if (!state.team1 || !state.team2) return;
  const num = id => { const el = document.getElementById(id); if (!el) return null;
    const v = el.value.trim(); if (v === '') return null; const n = +v; return isNaN(n) ? null : Math.max(0, n); };
  const gf = num('reg-gf'), gc = num('reg-gc');
  if (gf == null || gc == null) {
    regFlash = '⚠️ Introduce al menos el marcador final (goles de ambos equipos).';
    renderValidation(); return;
  }
  const a = { gf, gc,
    cf:num('reg-cf'), cc:num('reg-cc'),
    sf:num('reg-sf'), sc:num('reg-sc'),
    tf:num('reg-tf'), tc:num('reg-tc'),
    cards:num('reg-cards'),
    g1f:num('reg-g1f'), g1c:num('reg-g1c') };
  const leagueEl = document.getElementById('reg-league');
  const league = (leagueEl && leagueEl.value.trim()) || '';
  // #2 Fecha REAL del partido (antes: siempre Date.now(), mentía si registrabas tarde)
  const dateEl = document.getElementById('reg-date');
  const date = (dateEl && dateEl.value) || new Date().toISOString().slice(0,10);

  const s1 = computeStats(state.team1), s2 = computeStats(state.team2);
  const model = buildModel(s1, s2);
  const specs = buildBetSpecs(s1, s2, model);

  const editing = regEditTs != null;
  let ts;
  if (editing) {
    // #6 EDICIÓN: reemplaza las filas del registro original conservando su ts.
    // Nota: las probabilidades se recalculan con el modelo ACTUAL (si el
    // historial cambió desde entonces, pueden variar ligeramente).
    ts = regEditTs;
    betLog = betLog.filter(r => r.ts !== ts);
    regEditTs = null;
  } else {
    ts = Date.now();
    // Aviso de duplicado por FECHA DE PARTIDO (no de registro)
    const dup = betLog.some(r => r.team1 === names.team1 && r.team2 === names.team2 &&
      (r.date || new Date(r.ts).toISOString().slice(0,10)) === date);
    if (dup && !confirm(`⚠️ Ya registraste ${names.team1} vs ${names.team2} con fecha ${date}.\nRegistrarlo dos veces duplica sus apuestas y contamina la calibración.\n\n¿Registrar de todas formas?`)) {
      regFlash = 'Registro cancelado (duplicado de la misma fecha).';
      renderValidation(); return;
    }
  }

  // #5 Vínculo con "Apuesta hecha": las tarjetas marcadas en Apuestas se casan
  // con las specs por clave de tokens normalizados; heredan la cuota si la hay.
  const checkedKeys = new Map(); // normKey → nombre original
  betChecked.forEach(name => checkedKeys.set(betNormKey(name), name));

  let added = 0, hits = 0, mineN = 0;
  specs.forEach(sp => {
    const r = sp.resolve(a);
    if (r === null || r === undefined) return;
    const nk = betNormKey(sp.label);
    const srcName = checkedKeys.get(nk);
    const mine = srcName !== undefined;
    const odds = mine && betOdds[srcName] ? betOdds[srcName] : null;
    const row = { ts, date, team1:names.team1, team2:names.team2, league,
      market:sp.market, icon:sp.icon, label:sp.label, prob:sp.prob, hit:!!r };
    if (mine) { row.mine = true; if (odds) row.odds = odds; mineN++; }
    betLog.push(row);
    added++; if (r) hits++;
  });
  betLogMeta[ts] = { a, league, date, team1:names.team1, team2:names.team2 };
  saveBetLog();
  regFlash = added
    ? `${editing ? '✏️ Registro actualizado' : '✅ Registradas'} ${added} apuestas de ${names.team1} ${a.gf}–${a.gc} ${names.team2} · acertaron ${hits} (${Math.round(hits/added*100)}%)${mineN ? ` · ${mineN} marcadas como tuyas` : ''}.`
    : '⚠️ No se pudo evaluar ninguna apuesta (revisa los datos introducidos).';
  renderValidation();
}

// #6 Cargar un registro existente en el formulario para corregirlo.
function editRegMatch(ts) {
  const meta = betLogMeta[ts];
  if (!meta) { alert('Este registro es de una versión anterior y no guarda los datos del partido; solo puede eliminarse y reingresarse.'); return; }
  if (meta.team1 !== names.team1 || meta.team2 !== names.team2) {
    alert(`Este registro es de ${meta.team1} vs ${meta.team2}. Carga ese enfrentamiento en "Datos" antes de editarlo (las apuestas se reevalúan con su modelo).`);
    return;
  }
  regEditTs = ts;
  regFlash = '';
  renderValidation();
  // Prefill tras el re-render
  const setv = (id, v) => { const el = document.getElementById(id); if (el) el.value = (v == null ? '' : v); };
  const A = meta.a || {};
  setv('reg-gf', A.gf); setv('reg-gc', A.gc);
  setv('reg-cf', A.cf); setv('reg-cc', A.cc);
  setv('reg-tf', A.tf); setv('reg-tc', A.tc);
  setv('reg-sf', A.sf); setv('reg-sc', A.sc);
  setv('reg-g1f', A.g1f); setv('reg-g1c', A.g1c);
  setv('reg-cards', A.cards);
  setv('reg-league', meta.league);
  setv('reg-date', meta.date);
  const form = document.querySelector('.reg-form');
  if (form) form.scrollIntoView({ behavior:'smooth', block:'start' });
}
function cancelEditReg() { regEditTs = null; regFlash = ''; renderValidation(); }

function setBetLogFilter(v) { betLogFilter = v; regFlash = ''; renderValidation(); } // legado (no usado)
// #7 Filtros combinables: equipo Y liga Y mercado Y periodo a la vez.
function setBetLogF(key, val) { betLogFilter[key] = val; regFlash = ''; renderValidation(); }
function betFilterIsAll() { return Object.values(betLogFilter).every(v => v === 'all'); }

function filteredBetLog() {
  const f = betLogFilter;
  const periodDays = { d30:30, d90:90, d365:365 }[f.period] || null;
  const now = Date.now();
  return betLog.filter(r => {
    if (f.team !== 'all' && r.team1 !== f.team && r.team2 !== f.team) return false;
    if (f.league !== 'all' && (r.league || '') !== f.league) return false;
    if (f.market !== 'all' && r.market !== f.market) return false;
    if (periodDays) {
      const t = r.date ? Date.parse(r.date + 'T12:00:00') : r.ts;
      if (now - t > periodDays * 86400000) return false;
    }
    return true;
  });
}

// Buscador en vivo de la lista de partidos registrados. Filtra por
// data-search (equipos + liga) sin re-renderizar, así no pierde el foco.
function filterRegLog(q) {
  const list = document.getElementById('reglog-list');
  if (!list) return;
  const term = (q || '').trim().toLowerCase();
  let shown = 0;
  list.querySelectorAll('.reglog-row').forEach(row => {
    const hit = !term || (row.getAttribute('data-search') || '').includes(term);
    row.style.display = hit ? '' : 'none';
    if (hit) shown++;
  });
  const none = document.getElementById('reglog-noresults');
  if (none) none.style.display = shown ? 'none' : '';
}
function toggleMktRow(m) { mktExpanded[m] = !mktExpanded[m]; renderValidation(); }

function clearBetLog() {
  if (!betLog.length) return;
  if (!confirm('¿Borrar TODO el registro de apuestas? Esta acción no se puede deshacer.')) return;
  betLog = []; saveBetLog(); regFlash = ''; renderValidation();
}
function deleteBetLogMatch(ts) {
  betLog = betLog.filter(r => r.ts !== ts);
  delete betLogMeta[ts];
  if (regEditTs === ts) regEditTs = null;
  saveBetLog(); renderValidation();
}
function exportBetLog() {
  const rows = filteredBetLog();
  if (!rows.length) return;
  const cols = ['fecha','team1','team2','league','market','label','prob','hit','mia','cuota'];
  const lines = rows.map(r => [
    r.date || new Date(r.ts).toISOString().slice(0,10), r.team1, r.team2, r.league||'',
    r.market, `"${(r.label||'').replace(/"/g,'')}"`, r.prob.toFixed(4), r.hit?1:0,
    r.mine?1:0, r.odds!=null?r.odds:''
  ].join(','));
  const csv = [cols.join(','), ...lines].join('\n');
  const blob = new Blob([csv], {type:'text/csv'});
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = 'registro_apuestas.csv';
  link.click();
}

// ---- Backup completo del registro (JSON) ----
// betLog vive solo en localStorage: limpiar datos del navegador = perder meses
// de calibración. Exporta TODO (sin filtrar) e importa con merge por ts+label.
function exportBetLogJSON() {
  if (!betLog.length) return;
  const blob = new Blob([JSON.stringify({ v: 1, exported: Date.now(), betLog }, null, 1)], {type:'application/json'});
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = `backup_rendimiento_${new Date().toISOString().slice(0,10)}.json`;
  link.click();
}
function importBetLogJSON(input) {
  const file = input.files && input.files[0];
  input.value = '';
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const data = JSON.parse(reader.result);
      const rows = Array.isArray(data) ? data : (data && Array.isArray(data.betLog) ? data.betLog : null);
      if (!rows) throw new Error('formato');
      const valid = rows.filter(r => r && typeof r.ts === 'number' && typeof r.prob === 'number'
        && typeof r.hit === 'boolean' && r.label && r.market && r.team1 && r.team2);
      if (!valid.length) throw new Error('vacío');
      // Merge sin duplicados (clave ts+label)
      const seen = new Set(betLog.map(r => r.ts + '§' + r.label));
      let added = 0;
      valid.forEach(r => {
        const k = r.ts + '§' + r.label;
        if (!seen.has(k)) { betLog.push({ ts:r.ts, team1:r.team1, team2:r.team2,
          league:r.league||'', market:r.market, icon:r.icon||'🎯', label:r.label,
          prob:Math.min(1,Math.max(0,r.prob)), hit:!!r.hit }); seen.add(k); added++; }
      });
      saveBetLog();
      regFlash = added ? `✅ Backup importado: ${added} apuestas añadidas (${valid.length - added} ya existían).`
                       : 'ℹ️ El backup no contenía apuestas nuevas.';
    } catch(e) {
      regFlash = '⚠️ No se pudo leer el backup (JSON inválido o formato desconocido).';
    }
    renderValidation();
  };
  reader.readAsText(file);
}

// ---- Render de la pestaña ----
// #7 Curva de fiabilidad: puntos (esperado, real) por franja + diagonal ideal.
function relCurveSVG(buckets) {
  const W = 320, H = 230, P = 34; // viewBox + padding
  const x = v => P + v * (W - P - 12);
  const y = v => (H - P) - v * (H - P - 12);
  const maxN = Math.max(...buckets.map(b => b.n));
  const pts = buckets.map(b => {
    const r = 3 + 7 * Math.sqrt(b.n / maxN);
    const off = Math.abs(b.real - b.exp);
    const col = off < 0.08 ? 'var(--accent)' : off < 0.18 ? 'var(--warn)' : 'var(--bad)';
    return `<circle cx="${x(b.exp).toFixed(1)}" cy="${y(b.real).toFixed(1)}" r="${r.toFixed(1)}" fill="${col}" fill-opacity=".55" stroke="${col}" stroke-width="1.5"><title>${b.lo}–${b.hi}%: esperado ${Math.round(b.exp*100)}% · real ${Math.round(b.real*100)}% · n=${b.n}</title></circle>`;
  }).join('');
  const ticks = [0, .25, .5, .75, 1].map(t => `
    <line x1="${x(t)}" y1="${H-P}" x2="${x(t)}" y2="${H-P+4}" stroke="var(--line)"/>
    <text x="${x(t)}" y="${H-P+15}" text-anchor="middle" font-size="9" fill="var(--text-3)">${Math.round(t*100)}</text>
    <line x1="${P-4}" y1="${y(t)}" x2="${P}" y2="${y(t)}" stroke="var(--line)"/>
    <text x="${P-7}" y="${y(t)+3}" text-anchor="end" font-size="9" fill="var(--text-3)">${Math.round(t*100)}</text>`).join('');
  return `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Curva de fiabilidad">
    <rect x="${P}" y="12" width="${W-P-12}" height="${H-P-12}" fill="none" stroke="var(--line-soft)"/>
    <line x1="${x(0)}" y1="${y(0)}" x2="${x(1)}" y2="${y(1)}" stroke="var(--text-3)" stroke-dasharray="4 4"/>
    ${ticks}
    <text x="${(P+W-12)/2}" y="${H-4}" text-anchor="middle" font-size="9" fill="var(--text-3)">Probabilidad prometida (%)</text>
    <text x="10" y="${(H-P+12)/2}" text-anchor="middle" font-size="9" fill="var(--text-3)" transform="rotate(-90 10 ${(H-P+12)/2})">Acierto real (%)</text>
    ${pts}
  </svg>`;
}

function renderValidation() {
  const el = document.getElementById('validation-content');
  if (!el) return;
  if (!state.team1 || !state.team2) {
    el.className = 'no-data';
    el.innerHTML = '<div style="font-size:36px">📊</div><p>Carga los datos de ambos equipos para registrar resultados</p>';
    return;
  }
  el.className = '';

  const rows = filteredBetLog();
  const totalN = rows.length;
  const totalHits = rows.filter(r => r.hit).length;
  const avgProb = totalN ? rows.reduce((s,r)=>s+r.prob,0)/totalN : 0;
  const hitRate = totalN ? totalHits/totalN : 0;

  // --- Brier score y log loss: calidad REAL de las probabilidades ---
  // Brier = media de (p - resultado)². 0 = perfecto; 0.25 = tirar moneda al 50%.
  // Log loss penaliza más la sobreconfianza fallida.
  const clampP = p => Math.min(1-1e-6, Math.max(1e-6, p));
  const brier = totalN ? rows.reduce((s,r)=>s+Math.pow(r.prob-(r.hit?1:0),2),0)/totalN : 0;
  const logloss = totalN ? rows.reduce((s,r)=>{const p=clampP(r.prob);return s-(r.hit?Math.log(p):Math.log(1-p));},0)/totalN : 0;
  // Referencia: Brier de un predictor "plano" que siempre dijera la prob media.
  const brierRef = totalN ? avgProb*(1-avgProb) + Math.pow(avgProb-hitRate,2) : 0;
  const brierCol = brier < brierRef-0.01 ? 'var(--accent)' : brier > brierRef+0.01 ? 'var(--bad)' : 'var(--warn)';

  // --- Intervalo de Wilson (95%) para el acierto de cada franja ---
  const wilson = (h, n) => {
    if (!n) return [0,1];
    const z = 1.96, p = h/n, z2 = z*z;
    const den = 1 + z2/n;
    const c = (p + z2/(2*n)) / den;
    const half = (z * Math.sqrt(p*(1-p)/n + z2/(4*n*n))) / den;
    return [Math.max(0,c-half), Math.min(1,c+half)];
  };

  // --- Calibración por franja de probabilidad (deciles, solo con datos) ---
  const buckets = [];
  for (let lo=0; lo<100; lo+=10) {
    const hi = lo+10;
    const inB = rows.filter(r => { const p=r.prob*100; return p>=lo && (hi===100? p<=hi : p<hi); });
    if (!inB.length) continue;
    const h = inB.filter(r=>r.hit).length;
    const exp = inB.reduce((s,r)=>s+r.prob,0)/inB.length;
    buckets.push({ lo, hi, n:inB.length, hits:h, real:h/inB.length, exp });
  }

  // --- Por mercado ---
  const byMarket = {};
  rows.forEach(r => {
    const M = (byMarket[r.market] = byMarket[r.market] || { icon:r.icon, n:0, hits:0, sump:0, labels:{} });
    M.n++; if (r.hit) M.hits++; M.sump += r.prob;
    const L = (M.labels[r.label] = M.labels[r.label] || { n:0, hits:0, sump:0 });
    L.n++; if (r.hit) L.hits++; L.sump += r.prob;
  });
  const markets = Object.keys(byMarket).sort((a,b)=>{
    const ia=MARKET_ORDER.indexOf(a), ib=MARKET_ORDER.indexOf(b);
    return (ia<0?99:ia)-(ib<0?99:ib);
  });

  // --- Partidos registrados (agrupados por ts) ---
  const matchesMap = {};
  betLog.forEach(r => {
    const k = r.ts;
    (matchesMap[k] = matchesMap[k] || { ts:r.ts, date:r.date||null, team1:r.team1, team2:r.team2, league:r.league, n:0, hits:0, mine:0 });
    matchesMap[k].n++; if (r.hit) matchesMap[k].hits++; if (r.mine) matchesMap[k].mine++;
  });
  const matches = Object.values(matchesMap).sort((a,b)=>{
    const ta = a.date ? Date.parse(a.date+'T12:00:00') : a.ts;
    const tb = b.date ? Date.parse(b.date+'T12:00:00') : b.ts;
    return tb - ta || b.ts - a.ts;
  });

  // --- Opciones de filtro (combinables) ---
  const teams = [...new Set(betLog.flatMap(r=>[r.team1,r.team2]))].filter(Boolean).sort();
  const leagues = [...new Set(betLog.map(r=>r.league))].filter(Boolean).sort();
  const marketsAll = [...new Set(betLog.map(r=>r.market))].filter(Boolean).sort((a,b)=>{
    const ia=MARKET_ORDER.indexOf(a), ib=MARKET_ORDER.indexOf(b);
    return (ia<0?99:ia)-(ib<0?99:ib);
  });
  const opt = (v, txt, cur) => `<option value="${v}"${cur===v?' selected':''}>${txt}</option>`;
  const selTeam = `<select onchange="setBetLogF('team',this.value)">${opt('all','⚽ Equipo: todos',betLogFilter.team)}${teams.map(t=>opt(t,t,betLogFilter.team)).join('')}</select>`;
  const selLeague = `<select onchange="setBetLogF('league',this.value)">${opt('all','🏆 Liga: todas',betLogFilter.league)}${leagues.map(l=>opt(l,l,betLogFilter.league)).join('')}</select>`;
  const selMarket = `<select onchange="setBetLogF('market',this.value)">${opt('all','🎯 Mercado: todos',betLogFilter.market)}${marketsAll.map(mk=>opt(mk,mk,betLogFilter.market)).join('')}</select>`;
  const selPeriod = `<select onchange="setBetLogF('period',this.value)">${opt('all','📅 Siempre',betLogFilter.period)}${opt('d30','Últimos 30 días',betLogFilter.period)}${opt('d90','Últimos 90 días',betLogFilter.period)}${opt('d365','Último año',betLogFilter.period)}</select>`;

  // --- #1/#5 Mis apuestas: solo las que marcaste "Apuesta hecha" ---
  const mine = rows.filter(r => r.mine);
  const mineOdds = mine.filter(r => r.odds);
  const mineHits = mine.filter(r => r.hit).length;
  const pl = mineOdds.reduce((s,r) => s + (r.hit ? r.odds - 1 : -1), 0); // stake plano 1u
  const roi = mineOdds.length ? pl / mineOdds.length : 0;
  const avgEV = mineOdds.length ? mineOdds.reduce((s,r)=>s+(r.prob*r.odds-1),0)/mineOdds.length : 0;

  // --- HTML ---
  const calColor = (real, exp) => { const d=Math.abs(real-exp); return d<0.08?'var(--accent)':d<0.18?'var(--warn)':'var(--bad)'; };

  const calRows = buckets.map(b => {
    const col = calColor(b.real, b.exp);
    const [lo95, hi95] = wilson(b.hits, b.n);
    const lowN = b.n < 20;
    // Si el esperado cae DENTRO del intervalo de Wilson, la desviación no es
    // estadísticamente distinguible del ruido de muestra.
    const inCI = b.exp >= lo95 && b.exp <= hi95;
    return `<div class="cal-row${lowN ? ' cal-lown' : ''}" title="IC 95% del acierto real: ${Math.round(lo95*100)}–${Math.round(hi95*100)}%${inCI ? ' · el esperado cae dentro: desvío compatible con ruido' : ' · desvío significativo'}">
      <div class="cal-range">${b.lo}–${b.hi}%</div>
      <div class="cal-bartrack">
        <div class="cal-barfill" style="width:${Math.round(b.real*100)}%;background:${col}"></div>
        <div class="cal-expmark" style="left:${Math.round(b.exp*100)}%" title="Esperado ${Math.round(b.exp*100)}%"></div>
      </div>
      <div class="cal-nums"><strong style="color:${col}">${Math.round(b.real*100)}%</strong> <span>real</span></div>
      <div class="cal-meta">${b.hits}/${b.n} · esp. ${Math.round(b.exp*100)}%${lowN ? ' · <span style="color:var(--warn)">n bajo</span>' : ''}</div>
    </div>`;
  }).join('');

  const mktRows = markets.map(m => {
    const d = byMarket[m]; const real=d.hits/d.n; const exp=d.sump/d.n; const delta=real-exp;
    const dCol = delta>0.05?'var(--accent)':delta<-0.05?'var(--bad)':'var(--text-2)';
    const dTxt = (delta>=0?'+':'')+Math.round(delta*100);
    const open = !!mktExpanded[m];
    const labels = Object.keys(d.labels);
    // Sub-filas: cada línea/selección concreta, ordenada de más probable a menos.
    const subs = labels.map(lbl => {
      const L = d.labels[lbl];
      return { lbl, n:L.n, hits:L.hits, real:L.hits/L.n, exp:L.sump/L.n };
    }).sort((a,b)=>{
      const na=lineVal(a.lbl), nb=lineVal(b.lbl);
      if (na!=null && nb!=null) { if (na!==nb) return na-nb; return b.exp-a.exp; }
      if (na!=null) return -1;   // las líneas numéricas van primero, ascendentes
      if (nb!=null) return 1;
      return b.exp-a.exp;        // sin número (1X2, BTTS): por prob desc
    });
    const subHTML = subs.map(s => {
      const dl = s.real - s.exp;
      const c = dl>0.05?'var(--accent)':dl<-0.05?'var(--bad)':'var(--text-2)';
      return `<div class="mkt-subrow">
        <div class="mkt-subname">${s.lbl}</div>
        <div class="mkt-bartrack sm"><div class="mkt-barfill" style="width:${Math.round(s.real*100)}%"></div></div>
        <div class="mkt-rate sm">${Math.round(s.real*100)}%</div>
        <div class="mkt-meta sm">${s.hits}/${s.n}</div>
        <div class="mkt-delta sm" style="color:${c}">${(dl>=0?'+':'')+Math.round(dl*100)}</div>
      </div>`;
    }).join('');
    return `<div class="mkt-block ${open?'open':''}">
      <div class="mkt-row clickable" onclick="toggleMktRow('${m}')">
        <div class="mkt-name"><span class="mkt-chev">▶</span> ${d.icon||'🎯'} ${m} <span class="mkt-count">${labels.length}</span></div>
        <div class="mkt-bartrack"><div class="mkt-barfill" style="width:${Math.round(real*100)}%"></div></div>
        <div class="mkt-rate">${Math.round(real*100)}%</div>
        <div class="mkt-meta">${d.hits}/${d.n}</div>
        <div class="mkt-delta" style="color:${dCol}" title="Acierto real menos probabilidad media: positivo = el modelo lo subestima (posible valor); negativo = lo sobrestima">${dTxt}</div>
      </div>
      <div class="mkt-sub">${subHTML}</div>
    </div>`;
  }).join('');

  const matchRows = matches.slice(0,40).map(m => `
    <div class="reglog-row" data-search="${(m.team1+' '+m.team2+' '+(m.league||'')).toLowerCase().replace(/"/g,'')}">
      <div class="reglog-info">
        <span class="reglog-teams">${m.team1} vs ${m.team2}</span>
        <span class="reglog-sub">${m.league?m.league+' · ':''}${m.date ? new Date(m.date+'T12:00:00').toLocaleDateString('es',{day:'2-digit',month:'short',year:'2-digit'}) : new Date(m.ts).toLocaleDateString('es',{day:'2-digit',month:'short',year:'2-digit'})} · ${m.hits}/${m.n} aciertos${m.mine?` · 🎫 ${m.mine} tuya${m.mine>1?'s':''}`:''}</span>
      </div>
      ${betLogMeta[m.ts] ? `<button class="reglog-edit" onclick="editRegMatch(${m.ts})" title="Editar este registro (corrige datos y reevalúa)">✎</button>` : ''}
      <button class="reglog-del" onclick="deleteBetLogMatch(${m.ts})" title="Eliminar este partido del registro">✕</button>
    </div>`).join('');

  el.innerHTML = `
  <div class="val-intro">
    <h4>📊 Rendimiento de apuestas</h4>
    <p>Simula un partido en <strong>Apuestas</strong>, espera a que se juegue de verdad y aquí introduces el <strong>resultado real</strong>. El sistema evalúa <strong>todas</strong> las apuestas que generó el modelo (acierto/fallo) y las acumula. Con el tiempo verás dos cosas: si una probabilidad del <strong>X%</strong> se cumple de verdad el X% de las veces (<strong>calibración</strong>) y <strong>qué mercados</strong> se te cumplen más. Además, a partir de ${CALIB_MIN_N} apuestas registradas el historial <strong>corrige automáticamente</strong> las probabilidades nuevas, mercado por mercado. Solo necesitas el marcador; el resto de campos es opcional (sin ellos, esos mercados no se evalúan).</p>
  </div>

  ${regFlash ? `<div class="reg-flash">${regFlash}</div>` : ''}
  ${regEditTs != null ? `<div class="reg-editing">✏️ <strong>Editando registro</strong> del ${betLogMeta[regEditTs] ? betLogMeta[regEditTs].date : ''} — corrige los datos y pulsa "Actualizar". <a onclick="cancelEditReg()">Cancelar edición</a></div>` : ''}

  <div class="reg-form">
    <div class="reg-form-title">${regEditTs != null ? 'Corregir resultado' : 'Registrar resultado real'} · <strong>${names.team1}</strong> vs <strong>${names.team2}</strong></div>
    <div class="reg-grid">
      <div class="reg-col-head"></div><div class="reg-col-head">${names.team1}</div><div class="reg-col-head">${names.team2}</div>
      <div class="reg-rowlabel">Goles <span class="reg-req">obligatorio</span></div>
        <input id="reg-gf" type="number" min="0" step="1" placeholder="—">
        <input id="reg-gc" type="number" min="0" step="1" placeholder="—">
      <div class="reg-rowlabel">Córners</div>
        <input id="reg-cf" type="number" min="0" step="1" placeholder="—">
        <input id="reg-cc" type="number" min="0" step="1" placeholder="—">
      <div class="reg-rowlabel">Tiros a puerta</div>
        <input id="reg-tf" type="number" min="0" step="1" placeholder="—">
        <input id="reg-tc" type="number" min="0" step="1" placeholder="—">
      <div class="reg-rowlabel">Tiros (totales)</div>
        <input id="reg-sf" type="number" min="0" step="1" placeholder="—">
        <input id="reg-sc" type="number" min="0" step="1" placeholder="—">
      <div class="reg-rowlabel">Goles 1ª parte</div>
        <input id="reg-g1f" type="number" min="0" step="1" placeholder="—">
        <input id="reg-g1c" type="number" min="0" step="1" placeholder="—">
    </div>
    <div class="reg-single">
      <div class="reg-single-item"><label>Fecha del partido</label><input id="reg-date" type="date" value="${new Date().toISOString().slice(0,10)}"></div>
      <div class="reg-single-item"><label>Tarjetas totales del partido</label><input id="reg-cards" type="number" min="0" step="1" placeholder="—"></div>
      <div class="reg-single-item"><label>Liga / competición (opcional)</label><input id="reg-league" type="text" placeholder="ej. Mundial 2026"></div>
    </div>
    <button class="val-add-btn" onclick="registerMatchResult()">${regEditTs != null ? '💾 Actualizar registro' : '➕ Registrar y evaluar apuestas'}</button>
  </div>

  ${totalN === 0
    ? `<div class="val-empty">Aún no hay apuestas registradas${!betFilterIsAll()?' para esta combinación de filtros':''}. ${betLog.length && !betFilterIsAll() ? 'Prueba a relajar los filtros. 🔎' : 'Registra tu primer resultado arriba. 👆'}</div>
       ${betLog.length && !betFilterIsAll() ? `<div class="reg-filterbar"><span>Ver:</span>${selTeam}${selLeague}${selMarket}${selPeriod}</div>` : ''}`
    : `
  <div class="reg-filterbar">
    <span>Ver:</span>
    ${selTeam}${selLeague}${selMarket}${selPeriod}
    <span class="reg-filter-count">${totalN} apuestas · ${matches.length} partido${matches.length>1?'s':''}</span>
  </div>

  <div class="val-summary">
    <div class="val-summary-title">Resumen ${betFilterIsAll()?'global':'filtrado'}</div>
    <div class="val-metrics">
      <div class="val-metric"><div class="vm-val">${totalN}</div><div class="vm-lbl">Apuestas<br>registradas</div></div>
      <div class="val-metric"><div class="vm-val" style="color:var(--accent)">${Math.round(hitRate*100)}%</div><div class="vm-lbl">Acierto<br>global</div></div>
      <div class="val-metric"><div class="vm-val" style="color:${Math.abs(hitRate-avgProb)<0.06?'var(--accent)':Math.abs(hitRate-avgProb)<0.12?'var(--warn)':'var(--bad)'}">${(hitRate-avgProb>=0?'+':'')}${Math.round((hitRate-avgProb)*100)}</div><div class="vm-lbl">Calibración<br>(real − esperado)</div></div>
      <div class="val-metric" title="Media de (prob − resultado)². 0 = perfecto · 0.25 = azar al 50%. Referencia de un predictor plano con estos datos: ${brierRef.toFixed(3)}"><div class="vm-val" style="color:${brierCol}">${brier.toFixed(3)}</div><div class="vm-lbl">Brier<br>score</div></div>
      <div class="val-metric" title="Penaliza fuerte la sobreconfianza fallida. Menor = mejor. 0.693 = azar al 50%."><div class="vm-val" style="color:${logloss<0.60?'var(--accent)':logloss<0.72?'var(--warn)':'var(--bad)'}">${logloss.toFixed(3)}</div><div class="vm-lbl">Log<br>loss</div></div>
    </div>
    <div class="cal-hint">El acierto global por sí solo no dice mucho (sube si registras apuestas seguras). Lo que importa es la <strong>calibración</strong>: que el acierto real coincida con la probabilidad que el modelo prometía.</div>
  </div>

  <div class="bets-section-title">🎫 Mis apuestas (marcadas como hechas)</div>
  ${mine.length === 0
    ? `<div class="cal-legend">Ninguna todavía. En la pestaña <strong>Apuestas</strong>, marca "Apuesta hecha" en las que juegues de verdad y ponles la <strong>cuota</strong>; al registrar el resultado aparecerán aquí con tu ROI real.</div>`
    : `
  <div class="val-summary">
    <div class="val-metrics">
      <div class="val-metric"><div class="vm-val">${mine.length}</div><div class="vm-lbl">Apuestas<br>tuyas</div></div>
      <div class="val-metric"><div class="vm-val" style="color:var(--accent)">${Math.round(mineHits/mine.length*100)}%</div><div class="vm-lbl">Acierto</div></div>
      <div class="val-metric" title="Ganancia/pérdida acumulada a stake plano de 1 unidad por apuesta (solo las que tienen cuota: ${mineOdds.length})"><div class="vm-val" style="color:${pl>=0?'var(--accent)':'var(--bad)'}">${(pl>=0?'+':'')}${pl.toFixed(2)}u</div><div class="vm-lbl">P/L<br>(stake 1u)</div></div>
      <div class="val-metric" title="Retorno sobre lo apostado. LA métrica que importa: se puede acertar mucho y perder dinero con cuotas malas."><div class="vm-val" style="color:${roi>=0?'var(--accent)':'var(--bad)'}">${(roi>=0?'+':'')}${Math.round(roi*100)}%</div><div class="vm-lbl">ROI<br>real</div></div>
      <div class="val-metric" title="EV medio que el modelo veía al apostar (prob × cuota − 1). Si tu ROI real queda sistemáticamente por debajo, el modelo es optimista."><div class="vm-val" style="color:${avgEV>=0?'var(--accent)':'var(--warn)'}">${(avgEV>=0?'+':'')}${Math.round(avgEV*100)}%</div><div class="vm-lbl">EV medio<br>esperado</div></div>
    </div>
    <div class="mybets-list">
      ${mine.slice(-15).reverse().map(r => `
      <div class="mybets-row">
        <span class="mybets-res">${r.hit?'✅':'❌'}</span>
        <span class="mybets-lbl">${r.icon||'🎯'} ${r.label} <span style="color:var(--text-2)">· ${r.team1} vs ${r.team2}</span></span>
        <span class="mybets-odds">${r.odds ? '@'+r.odds.toFixed(2) : '—'}</span>
        <span class="mybets-odds" style="color:${r.odds ? (r.hit?'var(--accent)':'var(--bad)') : 'var(--text-3)'}">${r.odds ? (r.hit ? '+'+(r.odds-1).toFixed(2) : '−1.00') : ''}</span>
      </div>`).join('')}
    </div>
  </div>`}

  <div class="bets-section-title">🎯 Calibración por franja de probabilidad</div>
  <div class="cal-legend">Barra = acierto real · línea blanca = lo que el modelo prometía. Cuanto más cerca, mejor calibrado.${calibFit() ? ' Tu historial <strong>ya corrige</strong> las probabilidades nuevas en Apuestas con un ajuste suave por mercado (verás "ajust. X%" junto a la cruda).' : betLog.length ? ` A partir de ${CALIB_MIN_N} apuestas registradas (llevas ${betLog.length}) el historial corregirá automáticamente las probabilidades nuevas.` : ''}</div>
  <div class="cal-table">${calRows}</div>
  ${buckets.length >= 3 ? `
  <div class="rel-curve">
    <div class="cal-legend" style="margin-bottom:6px">Curva de fiabilidad: cada punto es una franja (x = prob. prometida, y = acierto real). Sobre la diagonal = calibración perfecta; tamaño = nº de apuestas.</div>
    ${relCurveSVG(buckets)}
  </div>` : ''}

  ${(() => {
    const fit = calibFit();
    if (!fit) return '';
    const cv = calibCV();
    let cvHTML = '';
    if (cv) {
      const diff = cv.brierRaw - cv.brierCal;
      const rel = cv.brierRaw > 0 ? diff / cv.brierRaw : 0;
      cvHTML = diff > 0.0005
        ? `<div class="cal-legend">🧪 <strong>Validación cruzada</strong> (5 folds, partidos completos, n=${cv.n}): Brier crudo <strong>${cv.brierRaw.toFixed(3)}</strong> → calibrado <strong style="color:var(--accent)">${cv.brierCal.toFixed(3)}</strong> (mejora ${(rel*100).toFixed(1)}%). La corrección <strong>sí mejora</strong> la predicción sobre partidos que el ajuste no había visto.</div>`
        : `<div class="cal-legend">🧪 <strong>Validación cruzada</strong> (n=${cv.n}): Brier crudo ${cv.brierRaw.toFixed(3)} vs calibrado ${cv.brierCal.toFixed(3)} — de momento la corrección <strong>no supera</strong> al modelo crudo (muestra pequeña o modelo ya bien calibrado). El tope de ±${Math.round(CALIB_MAX_SHIFT*100)} pts y el prior la mantienen prudente mientras acumulas registros.</div>`;
    }
    const chips = Object.keys(fit.mkt)
      .sort((x,y)=>{const ix=MARKET_ORDER.indexOf(x), iy=MARKET_ORDER.indexOf(y); return (ix<0?99:ix)-(iy<0?99:iy);})
      .map(m => {
        const d0 = byMarket[m];
        const pRef = d0 ? d0.sump / d0.n : 0.6;
        const adjP = _applyCalib(fit, pRef, m);
        const dpts = Math.round((adjP - pRef) * 100);
        const col = Math.abs(dpts) < 2 ? 'var(--text-2)' : dpts < 0 ? 'var(--bad)' : 'var(--accent)';
        return `<span class="calib-chip" title="Con ${fit.mkt[m].n} registros de ${m}: una probabilidad típica del ${Math.round(pRef*100)}% queda ajustada al ${Math.round(adjP*100)}%">${m} <strong style="color:${col}">${dpts===0?'±0':(dpts>0?'+':'')+dpts} pts</strong> <span class="calib-chip-n">n=${fit.mkt[m].n}</span></span>`;
      }).join('');
    return `<div class="bets-section-title">🔧 Corrección activa por mercado</div>
    ${cvHTML}
    <div class="cal-legend">Desplazamiento que se aplica ahora mismo en <strong>Apuestas</strong>, evaluado en la probabilidad media registrada de cada mercado. Los mercados con pocos registros heredan la corrección global; los que tienen muchos imponen su propio sesgo.</div>
    <div class="calib-chiprow">${chips}</div>`;
  })()}

  <div class="bets-section-title">📋 Acierto por mercado</div>
  <div class="cal-legend">Última columna = acierto real − probabilidad media. <span style="color:var(--accent)">Positivo</span> = el modelo subestima ese mercado (posible valor); <span style="color:var(--bad)">negativo</span> = lo sobrestima.</div>
  <div class="mkt-table">${mktRows}</div>

  <div class="val-summary-actions">
    <span class="val-export-btn" onclick="exportBetLog()">⬇ Exportar registro a CSV</span>
    <span class="val-export-btn" onclick="exportBetLogJSON()" title="Backup completo del registro (todas las apuestas, sin filtrar). Guárdalo: localStorage se pierde al limpiar datos del navegador.">💾 Backup JSON</span>
    <span class="val-export-btn" onclick="document.getElementById('betlog-import').click()" title="Restaurar un backup JSON. Hace merge: no duplica lo que ya existe.">📥 Importar backup</span>
    <input id="betlog-import" type="file" accept=".json,application/json" style="display:none" onchange="importBetLogJSON(this)">
    <button class="val-promote-all-btn" onclick="clearBetLog()" title="Borrar todo el registro acumulado">🗑 Borrar registro</button>
  </div>

  <div class="bets-section-title">🗂 Partidos registrados</div>
  <input id="reglog-search" class="reglog-search" type="text" placeholder="🔎 Buscar por equipo o liga…" oninput="filterRegLog(this.value)">
  <div class="reglog-list" id="reglog-list">${matchRows}</div>
  <div class="reglog-noresults" id="reglog-noresults" style="display:none">Sin partidos que coincidan.</div>
  `}
  `;
}

// ============================================================
//  DESCARGA CSV DE EJEMPLO JUGADORES
// ============================================================
function downloadPlayerSample() {
  const csv = `jugador,equipo,posicion,partido,minutos,goles,asistencias,tiros,tiros_puerta,tarjetas_a,tarjetas_r
R. Jimenez,Mi Equipo,FW,1,90,1,0,4,2,0,0
R. Jimenez,Mi Equipo,FW,2,90,0,1,3,1,1,0
R. Jimenez,Mi Equipo,FW,3,76,1,0,5,3,0,0
H. Lozano,Mi Equipo,FW,1,85,0,1,2,1,0,0
H. Lozano,Mi Equipo,FW,2,90,1,0,3,2,0,0
E. Herrera,Mi Equipo,MF,1,90,0,0,1,0,1,0
E. Herrera,Mi Equipo,MF,2,90,0,1,2,1,0,0
C. Montes,Mi Equipo,DF,1,90,0,0,0,0,1,0
C. Montes,Mi Equipo,DF,2,90,0,0,1,0,0,0
G. Ochoa,Mi Equipo,GK,1,90,0,0,0,0,0,0`;
  const blob = new Blob([csv], {type:'text/csv'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'plantilla_jugadores.csv';
  a.click();
}

// ============================================================
//  DESCARGA CSV DE EJEMPLO
// ============================================================
function downloadSample() {
  const csv = `fecha,equipo,rival,sede,goles_f,goles_c,goles_1t_f,goles_1t_c,goles_2t_f,goles_2t_c,tiros,tiros_rival,tiros_puerta,tiros_puerta_rival,corners,corners_rival,tarjetas_a,tarjetas_r,asistencias,resultado,xg_f,xg_c,xgot_f,xgot_c,ppda_f,ppda_c
2024-04-01,Mi Equipo,Rival A,local,3,1,2,0,1,1,14,8,6,3,8,4,1,0,2,W,2.41,0.88,1.95,0.62,9.1,12.8
2024-03-25,Mi Equipo,Rival B,visitante,2,0,1,0,1,0,11,6,4,2,6,3,2,0,2,W,1.73,0.52,1.40,0.38,10.2,13.1
2024-03-18,Mi Equipo,Rival C,local,1,1,0,1,1,0,9,9,3,3,5,5,1,0,1,D,1.12,1.34,0.88,1.05,11.4,11.0
2024-03-10,Mi Equipo,Rival D,visitante,2,2,1,1,1,1,10,11,4,4,5,6,3,0,2,D,1.55,1.97,1.22,1.60,12.0,10.4
2024-03-03,Mi Equipo,Rival E,local,4,1,2,0,2,1,16,7,7,3,9,3,1,0,3,W,3.02,0.74,2.55,0.50,8.4,13.9
2024-02-24,Mi Equipo,Rival F,visitante,0,1,0,0,0,1,7,9,2,4,3,6,2,0,0,L,0.61,1.48,0.45,1.18,13.1,9.8
2024-02-17,Mi Equipo,Rival G,local,2,0,1,0,1,0,12,6,5,2,7,3,1,0,2,W,1.89,0.43,1.55,0.30,9.6,12.5
2024-02-10,Mi Equipo,Rival H,visitante,1,1,0,1,1,0,9,9,3,3,4,4,2,0,1,D,1.07,1.21,0.82,0.95,11.8,10.9
2024-02-03,Mi Equipo,Rival I,local,3,2,1,1,2,1,13,10,5,4,8,5,1,1,2,W,2.18,1.66,1.78,1.34,9.9,11.7
2024-01-27,Mi Equipo,Rival J,visitante,2,0,1,0,1,0,11,7,4,2,6,4,1,0,2,W,1.64,0.59,1.30,0.44,10.6,12.2`;
  const blob = new Blob([csv], {type:'text/csv'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'plantilla_completa.csv';
  a.click();
}

// ============================================================
//  INICIALIZACIÓN
//  loadLibrary() y loadBetLog() ahora leen de MySQL (asíncrono):
//  se esperan ambas antes de renderizar para no pintar con datos vacíos.
// ============================================================
(async function iniciarDatos() {
  await loadLibrary();
  await loadBetLog();
  renderLibrary();
  restoreSession(); // recupera el último enfrentamiento, pestaña y acordeones
  // Si el Panel de administración enlaza con ?tab=history o ?tab=validation, abrir esa pestaña
  try {
    const tabUrl = new URLSearchParams(window.location.search).get('tab');
    if (tabUrl) showTab(tabUrl);
  } catch (e) { /* URL inválida: ignorar */ }
})();

// ============================================================
//  ATAJOS DE TECLADO
//  1-6 → cambiar de pestaña · Esc → cerrar modales abiertos
// ============================================================
const TAB_KEYS = ['data','analysis','bets','players','history','validation'];
document.addEventListener('keydown', (e) => {
  const editOpen = document.getElementById('edit-modal-bg')?.classList.contains('show');
  const libOpen  = document.getElementById('lib-modal-bg')?.classList.contains('show');

  // Esc cierra cualquier modal abierto
  if (e.key === 'Escape') {
    if (editOpen) { closeEditModal(); e.preventDefault(); return; }
    if (libOpen)  { resolveLibConflict('cancel'); e.preventDefault(); return; }
  }

  // Si hay un modal abierto o el foco está en un campo de texto, no cambiar pestaña
  const typing = ['INPUT','SELECT','TEXTAREA'].includes(document.activeElement?.tagName);
  if (editOpen || libOpen || typing) return;

  // 1-6 → pestañas
  if (e.key >= '1' && e.key <= '6') {
    const idx = parseInt(e.key, 10) - 1;
    if (TAB_KEYS[idx]) { showTab(TAB_KEYS[idx]); e.preventDefault(); }
  }
});

// ============================================================
//  ENTER avanza al siguiente campo en el modal de añadir/editar
//  En el último campo, Enter guarda el partido.
// ============================================================
(function setupEditModalEnter() {
  const modal = document.querySelector('#edit-modal-bg .edit-modal');
  if (!modal) return;
  modal.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    const target = e.target;
    // En selects, Enter abre el desplegable; lo dejamos pasar salvo que queramos avanzar
    if (target.tagName === 'TEXTAREA') return;
    e.preventDefault();
    // Lista de campos enfocables en orden de aparición en el DOM
    const fields = Array.from(modal.querySelectorAll('input, select'));
    const i = fields.indexOf(target);
    if (i === -1) return;
    if (i < fields.length - 1) {
      const next = fields[i + 1];
      next.focus();
      if (next.select) try { next.select(); } catch (_) {}
    } else {
      // Último campo → guardar
      saveEditHist();
    }
  });
})();

// La pantalla de bienvenida (el balon con "Analizador de Futbol") se
// quito: al entrar se va derecho a la herramienta sin esa espera.