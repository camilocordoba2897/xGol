// ============================================================
//  CALCULO LOCAL DEL ANALIZADOR
//  Lo que queda aqui es el modelo local de respaldo (Poisson sobre los
//  ultimos partidos de cada equipo: se usa solo si el motor del servidor
//  no responde), las estadisticas que pintan las tarjetas de forma y el
//  registro de pronosticos evaluados que alimenta seguimiento.js.
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
let fifaRankings = {}; // { 'pais': ranking_number }

// ============================================================
//  CANCHA NEUTRAL
// ============================================================

// ¿El partido a predecir es en cancha neutral? (final, Mundial, sede única)
// Si es true, no se aplica ventaja local y se usan stats neutrales/promedio.
let neutralVenue = false;

// ============================================================
//  RANKING FIFA (selecciones nacionales)
//  Lo usa el calculo local para la fuerza del rival en partidos de
//  selecciones.
// ============================================================

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

// ============================================================
//  CONSTANTES DEL CALCULO LOCAL
// ============================================================

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
//  HELPERS DE RENDER
// ============================================================
function pct(v) { return Math.round(Math.max(0, Math.min(1, v)) * 100); }
function fmt(v) { return (+v).toFixed(1); }
function fmt2(v) { return (+v).toFixed(2); }

// ============================================================
//  CANCHA NEUTRAL (interruptor del pronostico, lo pinta vista.js)
// ============================================================
function toggleNeutral(on) {
  neutralVenue = !!on;
  renderAll();
}

// ============================================================
//  REGISTRO DE PRONOSTICOS EVALUADOS
//  seguimiento.js evalua cada partido pronosticado cuando termina y lo
//  agrega aqui. Se guarda por usuario en la base; el panel del
//  administrador lo muestra en "Seguimiento del analizador".
// ============================================================
let betLog = [];               // [{ts, date?, team1, team2, league, market, icon, label, prob, hit, mine?, odds?}]
let betLogMeta = {};           // {ts: {a, league, date, team1, team2}} → permite EDITAR registros

async function loadBetLog() {
  try {
    const resp = await fetch(API.cargarApuestas, { headers:{'X-Requested-With':'fetch'} });
    const data = await resp.json();
    betLog = data.betLog || [];
    betLogMeta = data.betLogMeta || {};
    // Solo con el registro YA cargado se puede guardar: saveBetLog reemplaza
    // en el servidor TODO el registro del usuario por lo que haya aqui, y
    // guardar sobre una lista vacia (carga lenta o fallida) lo borraba entero.
    window.XGOL_BETLOG_LISTO = true;
  } catch (e) { betLog = []; betLogMeta = {}; }
}
function saveBetLog() {
  // Persiste el registro (apuestas + metadatos) en MySQL en segundo plano.
  if (!window.XGOL_BETLOG_LISTO) return;   // ver loadBetLog
  try {
    fetch(API.guardarApuestas, {
      method:'POST',
      headers:{'Content-Type':'application/json','X-CSRFToken':getCsrf()},
      body: JSON.stringify({ betLog, betLogMeta })
    });
  } catch (e) {}
}

// Las lineas del partido como objetos RESOLUBLES contra el resultado real:
// cada una trae su probabilidad y resolve(a), que dice si se cumplio. Solo los
// mercados que salen de la matriz del motor (1X2, goles y ambos marcan), que
// son los que se muestran y los que mide seguimiento.js. Corners, tiros,
// tarjetas y mitades salian de promedios de 15 partidos o de un reparto fijo,
// no se mostraban en ningun sitio y ya no se calculan.
function buildBetSpecs(s1, s2, model) {
  const specs = [];
  const N = names;
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

  return specs;
}

// ============================================================
//  INICIALIZACION
//  Solo el registro de pronosticos evaluados (lo usa seguimiento.js). La
//  biblioteca de equipos, la sesion guardada, las pestanas y los atajos de
//  teclado eran del modo manual, que ya no existe: no se cargan.
// ============================================================
loadBetLog();
