// TD Hub meldingen, versie 28: ontvangt meldingen van de site en bewaart ze in de Google Sheet.
// Versie 26: de externe ploeg op zaterdag meldt bonnen af met een eigen sleutel (actie extern, tabblad Extern), met handtekening en foto's.
// Versie 25: meer foto's per storing en per afgekeurd PM-punt (veld fotos). In de kolom foto staan de Drive-id's met een komma ertussen;
// de eerste foto komt op de CM-bon, de rest als bijlage achter de bon. De monteursapp leest ook het rooster uit de wachtrij (rij.rooster, rij.roostermensen).
// Versie 24: opnamelijsten in de monteursapp (tabblad Opnamelijst, acties olopname en olfoto).
// Versie 22: het tabblad Productie voor de productie-app (pilot), met een eigen sleutel.
// De echte waarden van SHEET_ID en SLEUTEL staan niet in deze repository.
const SHEET_ID = '__SHEET_ID__';
const SLEUTEL = '__SLEUTEL__';
const MELDSLEUTEL = '__MELDSLEUTEL__';
const MONTEURSLEUTEL = '__MONTEURSLEUTEL__';
const WVSLEUTEL = '__WVSLEUTEL__';
const KIJKSLEUTEL = '__KIJKSLEUTEL__';
const OUTPUTSLEUTEL = '__OUTPUTSLEUTEL__';
const PMSLEUTEL = '__PMSLEUTEL__';
const PRODUCTIESLEUTEL = '__PRODUCTIESLEUTEL__';
const EXTERNSLEUTEL = '__EXTERNSLEUTEL__';
const EXTMONTEURSLEUTEL = '__EXTMONTEURSLEUTEL__';
const WACHTRIJ = '__WACHTRIJ__';
// voortgang (kolom 21, vanaf versie 21): Bezig of leeg, voor een actie op het SQD-bord en in de actielijst.
const KOP = ['id', 'tijd', 'letter', 'melding', 'lijn', 'machine', 'melder', 'actiehouder', 'datum', 'bon_nodig', 'status', 'gereed_op', 'gereed_door', 'oplossing', 'foto', 'risico', 'vervolg', 'code', 'wachtrij', 'prio', 'voortgang'];
const ZONE = 'Europe/Amsterdam';
const MAP = "TD Hub foto's";
const MAX_FOTO = 8000000;
// De statussen van een bon. De oude statussen blijven geldig voor een pagina die nog open staat: de site en de geplande taak zetten ze om.
const BONSTATUS = ['Open', 'Te plannen', 'Uitzoeken voor bestelling', 'Besteld', 'Leverdatum', 'Gepland', 'Uitgevoerd', 'Vervallen', 'Bestellen', 'Deels uitgevoerd', 'On hold', 'Gereed', 'Dubbel'];
const VERVOLG = ['Gereed', 'Overdragen aan volgende dienst', 'Onderdeel bestellen', 'Plannen voor onderhoudstop'];

const PLOEGEN = ['ochtend', 'middag', 'nacht a', 'nacht b'];
const LIJNEN = ['Lijn 1', 'Lijn 2', 'Lijn 3'];
const OUTKOP = ['datum', 'ploeg', 'lijn', 'output', 'opmerking', 'door', 'tijd'];
const PMKOP = ['nr', 'datum', 'status', 'taken', 'opmerking', 'door', 'tijd', 'reg'];
const PMSTATUS = ['Uitgevoerd', 'Deels uitgevoerd'];
const BEVKOP = ['id', 'nr', 'punt', 'naam', 'opmerking', 'foto', 'bon', 'door', 'tijd'];
const OPNAMEKOP = ['nr', 'status', 'regels', 'opmerking', 'foto', 'door', 'tijd'];
const OPNAMESTATUS = ['Bestellen', 'Deels uitgevoerd'];
// Externe ploeg op zaterdag: per afmelding één regel. Handtekening en foto's staan in Drive, de rest als JSON in gegevens.
const EXTERNKOP = ['nr', 'status', 'uitvoerder', 'uren', 'teamleider', 'handtekening', 'fotos', 'gegevens', 'tijd'];
// Werkverdeling van de externe ploeg (vanaf versie 28): per bon of PM-taak van een zaterdag welke monteur hem doet en hoe ver hij is.
const EXTWERKKOP = ['sleutel', 'datum', 'monteur', 'naam', 'status', 'gegevens', 'reden', 'tijd', 'log'];
const EXTWERKSTATUS = ['Niet toegewezen', 'Toegewezen', 'Klaar voor controle', 'Teruggestuurd', 'Afgetekend'];
const EXTSLEUTEL_RE = /^(CM\d+|SQDM-\d+|PM-\d+\|PM-\d{6}-\d{1,2})$/;
const EXTERNSTATUS = ['Uitgevoerd', 'Onderdeel bestellen', 'Deels uitgevoerd'];
// Opnamelijst in de monteursapp: per opnamelijst één regel. Alles wat de monteur invulde staat als JSON in de kolom gegevens.
const OLKOP = ['ol', 'status', 'gegevens', 'door', 'tijd'];
const OLSTATUS = ['Deels', 'Opgenomen'];
const OLMAX = 45000;
const LOGKOP = ['tijd', 'door', 'van', 'nr', 'status', 'rij'];
// Productie-app (pilot): per datum, dienst en afdeling één regel. De gegevens van de dienst staan als JSON in de kolom gegevens.
const PRODKOP = ['id', 'datum', 'dienst', 'afdeling', 'status', 'gegevens', 'door', 'tijd', 'gecontroleerd_door', 'gecontroleerd_op', 'log'];
const PRODDIENST = ['Ochtend', 'Middag', 'Nacht'];
const PRODAFDELING = ['Bakkerij', 'Inpak en ompak'];
const PRODSTATUS = ['Ingevuld', 'Onvolledig', 'Gecontroleerd'];
const PRODMAX = 45000;
// Welke sleutel de wijziging stuurde: wv, td, monteur, pm, output, productie of melden. Komt in elk wachtrijbestand en in het logboek, nooit uit wat de browser invult.
let VAN_ = '';

function blad_() {
  return SpreadsheetApp.openById(SHEET_ID).getSheets()[0];
}
function uit_(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}
function schoon_(s) {
  return String(s == null ? '' : s).slice(0, 1000).replace(/^[=+\-@]/, "'$&");
}
function nu_() {
  return Utilities.formatDate(new Date(), ZONE, 'dd-MM-yyyy HH:mm');
}

function map_() {
  const m = DriveApp.getFoldersByName(MAP);
  return m.hasNext() ? m.next() : DriveApp.createFolder(MAP);
}

function prio_(p) {
  return ['1', '2', '3'].includes(String(p)) ? String(p) : '';
}

function object_(r) {
  const o = {};
  KOP.forEach((k, i) => { o[k] = r[i]; });
  return o;
}

// Productiemeldingen krijgen een eigen doorlopend nummer. Dit draait binnen de lock, dus nooit dubbel.
function code_(b) {
  const n = b.getLastRow();
  let hoogste = 0;
  if (n > 1) b.getRange(2, 18, n - 1, 1).getDisplayValues().forEach(r => {
    const m = /^SQDM-(\d+)$/.exec(r[0]);
    if (m) hoogste = Math.max(hoogste, Number(m[1]));
  });
  return 'SQDM-' + (hoogste + 1);
}

// Elke regel die een bon moet worden krijgt één tekstbestand in de wachtrijmap.
// De geplande taak leest die map en gooit een bestand weg zodra de bon klaar is.
function wachtrij_(b) {
  const map = DriveApp.getFolderById(WACHTRIJ);
  b.getDataRange().getDisplayValues().forEach((r, i) => {
    if (i === 0 || r[18] || r[10] === 'Verwijderd' || (r[2] !== 'TD' && r[9] !== 'Ja')) return;
    map.createFile('bon-' + r[0] + '.txt', JSON.stringify(object_(r)), MimeType.PLAIN_TEXT);
    b.getRange(i + 1, 19).setValue(nu_());
  });
}

// Een melding kan zo vaak op de wachtrij als iemand het vinkje aan en uit zet; de taak slaat bestaande bonnen over.
function uitWachtrij_(b, rij, id) {
  if (!b.getRange(rij, 19).getDisplayValue()) return;
  const f = DriveApp.getFolderById(WACHTRIJ).getFilesByName('bon-' + id + '.txt');
  while (f.hasNext()) f.next().setTrashed(true);
  b.getRange(rij, 19).setValue('');
}

// Een fout in Drive mag een melding nooit tegenhouden. De regel gaat dan mee bij de volgende melding.
function naarWachtrij_(b) {
  try {
    wachtrij_(b);
  } catch (f) {
    console.error(f);
  }
}

// Een bonstatus staat tot de geplande taak hem verwerkt als status-<nr>.txt in de wachtrijmap.
// Een nieuwere wijziging voor dezelfde bon vult de oude aan: wat alleen in de oude stond blijft bewaard.
// Zo verdwijnt een afmelding van een monteur niet als de werkvoorbereider daarna de status aanpast. Een verwijderde bon blijft verwijderd.
// Alleen bonnen (CM- en SQDM-nummers) worden zo aangevuld. Andere bestanden, zoals STOP- met stop of stopweg, vervangen het oude bestand.
function zetBonstatus_(nr, status, rij, door) {
  const map = DriveApp.getFolderById(WACHTRIJ);
  const naam = 'status-' + nr + '.txt';
  const isBon = /^(CM\d+|SQDM-\d+)$/.test(String(nr));
  const nieuw = rij && typeof rij === 'object' && !Array.isArray(rij) ? rij : null;
  const oud = [];
  const f = map.getFilesByName(naam);
  while (f.hasNext()) {
    const x = f.next();
    if (x.isTrashed()) continue;
    let o = null;
    try {
      o = JSON.parse(x.getBlob().getDataAsString());
    } catch (e) {
      console.error(e);
    }
    oud.push({ bestand: x, inhoud: o });
  }
  if (isBon && status !== 'Verwijderd' && oud.some(x => x.inhoud && x.inhoud.status === 'Verwijderd')) {
    log_(nr, 'Genegeerd: al verwijderd', nieuw, door);
    return;
  }
  let samen = nieuw;
  if (isBon && status !== 'Verwijderd') oud.forEach(x => {
    const r = x.inhoud && x.inhoud.rij;
    if (r && typeof r === 'object' && !Array.isArray(r)) samen = Object.assign({}, r, samen || {});
  });
  else if (status === 'Verwijderd') samen = null;
  oud.forEach(x => x.bestand.setTrashed(true));
  map.createFile(naam, JSON.stringify({ nr: nr, status: status, rij: samen, tijd: nu_(), door: schoon_(door), van: VAN_ }), MimeType.PLAIN_TEXT);
  log_(nr, status, nieuw, door);
}

// Het logboek vult alleen aan: tijd, door, welke sleutel, nummer, status en de wijziging zelf. Een fout hier mag een wijziging nooit tegenhouden.
function log_(nr, status, rij, door) {
  try {
    const s = SpreadsheetApp.openById(SHEET_ID);
    let t = s.getSheetByName('Logboek');
    if (!t) {
      t = s.insertSheet('Logboek', s.getNumSheets());
      t.getRange('A:F').setNumberFormat('@');
      t.getRange(1, 1, 1, LOGKOP.length).setValues([LOGKOP]);
    }
    t.appendRow([nu_(), schoon_(door), VAN_, schoon_(nr), schoon_(status), rij ? JSON.stringify(rij).slice(0, 5000) : '']);
  } catch (e) {
    console.error(e);
  }
}

// Wijzigingen die nog niet in het overzicht staan. Zo ziet iedereen een nieuwe status meteen.
function bonstatus_() {
  const uit = [];
  try {
    const f = DriveApp.getFolderById(WACHTRIJ).searchFiles('trashed = false');
    while (f.hasNext()) {
      const x = f.next();
      if (x.getName().startsWith('status-')) uit.push(JSON.parse(x.getBlob().getDataAsString()));
    }
  } catch (e) {
    console.error(e);
  }
  return uit;
}

// De regel blijft als Verwijderd in de Sheet staan. Zo komt een SQDM-nummer nooit dubbel uit en blijft zichtbaar wie hem weghaalde.
function verwijder_(b, rij, r, d) {
  if (d.bon) zetBonstatus_(d.bon, 'Verwijderd', null, d.door);
  uitWachtrij_(b, rij, r[0]);
  b.getRange(rij, 11, 1, 3).setValues([['Verwijderd', nu_(), schoon_(d.door)]]);
  if (!r[14]) return;
  try {
    DriveApp.getFileById(r[14]).setTrashed(true);
  } catch (f) {
    console.error(f);
  }
}

// Een volgende dienst past het vervolg van een storing aan of meldt hem af. De tekst komt achter wat er al stond, zodat zichtbaar blijft wie wat deed.
// Elke wijziging krijgt een eigen bestand: de geplande taak zet ze op volgorde op de bon en zoekt de bon zelf op, ook als die nog gemaakt moet worden.
function zetRapport_(b, d) {
  const rijen = b.getDataRange().getDisplayValues();
  const i = rijen.findIndex((r, n) => n > 0 && r[0] === d.id && r[2] === 'TD' && r[10] !== 'Verwijderd');
  if (i < 0) return { fout: 'melding niet gevonden' };
  const r = rijen[i];
  if (r[16] === 'Gereed') return { ok: true, al: true };
  const door = String(d.door == null ? '' : d.door).trim().slice(0, 100);
  const tekst = String(d.tekst == null ? '' : d.tekst).trim().slice(0, 1000);
  const oplossing = (tekst ? [r[13], (door ? door + ': ' : '') + tekst].filter(Boolean).join(' · ') : r[13]).slice(-1000);
  const tijd = nu_();
  const gereed = d.vervolg === 'Gereed';
  zetBonstatus_('VV-' + d.id + '-' + Date.now(), d.vervolg, { vervolg: { id: d.id, vervolg: d.vervolg, tekst: tekst, door: door } }, door);
  b.getRange(i + 1, 14).setValue(schoon_(oplossing));
  b.getRange(i + 1, 17).setValue(d.vervolg);
  const af = b.getRange(i + 1, 12, 1, 2);
  af.setNumberFormat('@');
  af.setValues([[gereed ? tijd : '', gereed ? schoon_(door) : '']]);
  return { ok: true, tijd: tijd, oplossing: oplossing };
}

// Output staat op een eigen tabblad, per datum, ploeg en lijn één regel. Opnieuw invullen vervangt die regel.
function outputRijen_() {
  const b = SpreadsheetApp.openById(SHEET_ID).getSheetByName('Output');
  if (!b || b.getLastRow() < 2) return [];
  return b.getRange(2, 1, b.getLastRow() - 1, OUTKOP.length).getValues().slice(-500).map(r => {
    const o = {};
    OUTKOP.forEach((k, i) => { o[k] = r[i]; });
    return o;
  });
}

function zetOutput_(d) {
  const s = SpreadsheetApp.openById(SHEET_ID);
  const b = s.getSheetByName('Output') || s.insertSheet('Output', s.getNumSheets());
  b.getRange('A:C').setNumberFormat('@');
  b.getRange('G:G').setNumberFormat('@');
  b.getRange(1, 1, 1, OUTKOP.length).setValues([OUTKOP]);
  const n = b.getLastRow();
  const sleutels = n > 1 ? b.getRange(2, 1, n - 1, 3).getValues() : [];
  const i = sleutels.findIndex(r => r[0] === d.datum && r[1] === d.ploeg && r[2] === d.lijn);
  const rij = [d.datum, d.ploeg, d.lijn, Number(d.output), schoon_(d.opmerking), schoon_(d.door), nu_()];
  if (i >= 0) b.getRange(i + 2, 1, 1, rij.length).setValues([rij]);
  else b.appendRow(rij);
  return i >= 0;
}

// Afgemelde PM-bonnen staan op een eigen tabblad, per bon één regel. Opnieuw afmelden vervangt die regel.
function pmRijen_() {
  const b = SpreadsheetApp.openById(SHEET_ID).getSheetByName('PM');
  if (!b || b.getLastRow() < 2) return [];
  return b.getRange(2, 1, b.getLastRow() - 1, PMKOP.length).getValues().slice(-3000).map(r => {
    const o = {};
    PMKOP.forEach((k, i) => { o[k] = String(r[i]); });
    return o;
  });
}

// Een of meer foto's naar Drive: foto en eventueel fotos (een lijst), samen hooguit 4. Geeft de id's met een komma ertussen, of null als een foto te groot is.
function fotosOp_(d, naam) {
  const lijst = [d.foto].concat(Array.isArray(d.fotos) ? d.fotos : []).filter(Boolean).slice(0, 4);
  if (lijst.some(f => String(f).length > MAX_FOTO)) return null;
  return lijst.map((f, i) => map_().createFile(Utilities.newBlob(Utilities.base64Decode(f), 'image/jpeg', naam + (i ? '-' + (i + 1) : '') + '.jpg')).getId()).join(',');
}

// Hoort dit Drive-id bij de waarde in een kolom foto (een of meer id's met een komma ertussen)?
function heeftFoto_(waarde, id) {
  return String(waarde || '').split(',').indexOf(id) >= 0;
}

// Bevindingen bij controlepunten van PM-bonnen staan op een eigen tabblad.
function bevRijen_() {
  const b = SpreadsheetApp.openById(SHEET_ID).getSheetByName('Bevindingen');
  if (!b || b.getLastRow() < 2) return [];
  return b.getRange(2, 1, b.getLastRow() - 1, BEVKOP.length).getValues().slice(-3000).map(r => {
    const o = {};
    BEVKOP.forEach((k, i) => { o[k] = String(r[i]); });
    return o;
  });
}

// Is er een CM-bon nodig, dan komt de bevinding ook in het dienstrapport. De geplande taak maakt er dan een bon van, net als van een storing.
function zetBevinding_(b, d) {
  const id = Utilities.getUuid().slice(0, 8);
  const tijd = nu_();
  const foto = fotosOp_(d, 'bevinding-' + id);
  if (foto === null) return { fout: 'foto te groot' };
  const s = SpreadsheetApp.openById(SHEET_ID);
  const t = s.getSheetByName('Bevindingen') || s.insertSheet('Bevindingen', s.getNumSheets());
  t.getRange('A:I').setNumberFormat('@');
  t.getRange(1, 1, 1, BEVKOP.length).setValues([BEVKOP]);
  const bon = d.bon === 'Ja' ? 'Ja' : 'Nee';
  t.appendRow([id, d.nr, d.punt, schoon_(d.naam), schoon_(d.opmerking), foto, bon, schoon_(d.door), tijd]);
  if (bon === 'Ja') {
    b.getRange(1, 1, 1, KOP.length).setValues([KOP]);
    b.appendRow([id, tijd, 'TD', schoon_('PM-bevinding ' + d.nr + ', ' + d.naam + ': ' + d.opmerking), schoon_(d.lijn), schoon_(d.machine), schoon_(d.door), '', '', 'Nee', 'Rapport', '', '', '', foto, '', VERVOLG[3], '', '', '']);
    naarWachtrij_(b);
  }
  return { ok: true, id: id, tijd: tijd, foto: foto };
}

// Opnames van onderdelen staan op een eigen tabblad, per afmelding één regel.
function opnameRijen_() {
  const b = SpreadsheetApp.openById(SHEET_ID).getSheetByName('Opname');
  if (!b || b.getLastRow() < 2) return [];
  return b.getRange(2, 1, b.getLastRow() - 1, OPNAMEKOP.length).getValues().slice(-3000).map(r => {
    const o = {};
    OPNAMEKOP.forEach((k, i) => { o[k] = String(r[i]); });
    return o;
  });
}

// De monteur noteert bij een opnamebon de specificaties van de onderdelen en maakt een foto. Een opname die klaar is zet de bon op Bestellen.
// Elke afmelding krijgt een eigen wachtrijbestand: een statuswijziging op dezelfde bon mag de specificaties niet overschrijven.
function zetOpname_(d) {
  const regels = (Array.isArray(d.regels) ? d.regels : []).slice(0, 30).map(x => ({
    id: /^B\d+$/.test(x.id) ? x.id : '',
    onderdeel: String(x.onderdeel == null ? '' : x.onderdeel).trim().slice(0, 200),
    spec: String(x.spec == null ? '' : x.spec).trim().slice(0, 300),
    aantal: String(x.aantal == null ? '' : x.aantal).trim().slice(0, 20),
  }));
  if (d.status === 'Bestellen' && (!d.foto || !regels.length || regels.some(x => !x.spec))) return { fout: 'onjuiste invoer' };
  const tijd = nu_();
  const nu = Date.now();
  let foto = '';
  if (d.foto) {
    if (d.foto.length > MAX_FOTO) return { fout: 'foto te groot' };
    foto = map_().createFile(Utilities.newBlob(Utilities.base64Decode(d.foto), 'image/jpeg', 'opname-' + d.nr + '-' + nu + '.jpg')).getId();
  }
  const s = SpreadsheetApp.openById(SHEET_ID);
  const t = s.getSheetByName('Opname') || s.insertSheet('Opname', s.getNumSheets());
  t.getRange('A:G').setNumberFormat('@');
  t.getRange(1, 1, 1, OPNAMEKOP.length).setValues([OPNAMEKOP]);
  t.appendRow([d.nr, d.status, schoon_(regels.filter(x => x.spec).map(x => x.onderdeel + ': ' + x.spec + (x.aantal ? ', ' + x.aantal + ' stuks' : '')).join('; ')), schoon_(d.tekst), foto, schoon_(d.door), tijd]);
  zetBonstatus_('OPN-' + d.nr + '-' + nu, d.status, { opname: { nr: d.nr, tekst: String(d.tekst == null ? '' : d.tekst).slice(0, 1000), door: schoon_(d.door), foto: foto, regels: regels } }, d.door);
  return { ok: true, tijd: tijd, foto: foto };
}

// Opnamelijsten in de monteursapp. Een collega kan verder waar de vorige stopte, dus de laatste stand staat altijd in de Sheet.
function externRijen_() {
  const b = SpreadsheetApp.openById(SHEET_ID).getSheetByName('Extern');
  if (!b || b.getLastRow() < 2) return [];
  return b.getRange(2, 1, b.getLastRow() - 1, EXTERNKOP.length).getDisplayValues().slice(-500).map(r => {
    const o = {};
    EXTERNKOP.forEach((k, i) => { o[k] = r[i]; });
    try { o.gegevens = JSON.parse(o.gegevens || '{}'); } catch (f) { o.gegevens = {}; }
    return o;
  });
}

// De teamleider van de externe ploeg meldt een bon van de zaterdag af. Uitvoerder, uren, status en handtekening zijn verplicht;
// bij Onderdeel bestellen per onderdeel een naam en een foto, bij Deels uitgevoerd wat er gedaan is en wat er nog moet.
// Elke afmelding krijgt een eigen wachtrijbestand: de geplande taak zet het op de bon, het plan en de bestellijst.
function zetExtern_(d) {
  const t = x => String(x == null ? '' : x).trim();
  const uren = Number(String(d.uren).replace(',', '.'));
  const ond = (Array.isArray(d.onderdelen) ? d.onderdelen : []).slice(0, 6).map(x => ({ onderdeel: t(x.onderdeel).slice(0, 200), spec: t(x.spec).slice(0, 300), foto: x.foto || '' }));
  const pm = /^PM-\d+$/.test(d.nr);
  if (pm && !/^PM-\d{6}-\d{1,2}$/.test(d.pmbon)) return { fout: 'onjuiste invoer' };
  if (!(pm || /^(CM\d+|SQDM-\d+)$/.test(d.nr)) || !EXTERNSTATUS.includes(d.status) || !t(d.uitvoerder) || !(uren > 0 && uren <= 200) || !t(d.teamleider) || !d.handtekening) return { fout: 'onjuiste invoer' };
  if (d.status === 'Onderdeel bestellen' && (!ond.length || ond.some(x => !x.onderdeel || !x.foto))) return { fout: 'onjuiste invoer' };
  if (d.status === 'Deels uitgevoerd' && (!t(d.gedaan) || !t(d.nog))) return { fout: 'onjuiste invoer' };
  const isId = f => /^[\w-]{20,80}$/.test(String(f));
  if (String(d.handtekening).length > 600000 || ond.some(x => String(x.foto).length > MAX_FOTO) || [].concat(d.fotos || []).some(f => String(f).length > MAX_FOTO)) return { fout: 'foto te groot' };
  const nu = Date.now();
  const tijd = nu_();
  const hand = map_().createFile(Utilities.newBlob(Utilities.base64Decode(d.handtekening), 'image/png', 'handtekening-' + d.nr + '-' + nu + '.png')).getId();
  ond.forEach((x, i) => { if (isId(x.foto)) return; x.foto = map_().createFile(Utilities.newBlob(Utilities.base64Decode(x.foto), 'image/jpeg', 'extern-' + d.nr + '-' + nu + '-' + (i + 1) + '.jpg')).getId(); });
  const extra = [].concat(d.fotos || []).filter(Boolean).slice(0, 2).map((f, i) => map_().createFile(Utilities.newBlob(Utilities.base64Decode(f), 'image/jpeg', 'extern-' + d.nr + '-' + nu + '-f' + (i + 1) + '.jpg')).getId());
  const g = { pmbon: pm ? d.pmbon : '', gedaan: t(d.gedaan).slice(0, 1000), nog: t(d.nog).slice(0, 1000), opmerking: t(d.opmerking).slice(0, 1000), veegschoon: !!d.veegschoon, vrij: !!d.vrij, onderdelen: ond, fotos: extra };
  const fotos = ond.map(x => x.foto).concat(extra).join(',');
  const s = SpreadsheetApp.openById(SHEET_ID);
  const b = s.getSheetByName('Extern') || s.insertSheet('Extern', s.getNumSheets());
  b.getRange('A:I').setNumberFormat('@');
  b.getRange(1, 1, 1, EXTERNKOP.length).setValues([EXTERNKOP]);
  b.appendRow([d.nr, d.status, schoon_(d.uitvoerder).slice(0, 200), String(uren), schoon_(d.teamleider).slice(0, 100), hand, fotos, JSON.stringify(g), tijd]);
  if (/^\d{2}-\d{2}-\d{4}$/.test(String(d.datum || ''))) zetExtWerk_(d.nr + (pm ? '|' + d.pmbon : ''), d.datum, x => { x.status = 'Afgetekend'; x.reden = ''; }, 'afgetekend door ' + t(d.teamleider));
  zetBonstatus_('EXT-' + d.nr + '-' + nu, 'Open', { extern: Object.assign({ nr: d.nr, status: d.status, uitvoerder: t(d.uitvoerder).slice(0, 200), uren: uren, teamleider: t(d.teamleider).slice(0, 100), handtekening: hand, tijd: tijd }, g) }, d.teamleider);
  return { ok: true, tijd: tijd, handtekening: hand, fotos: fotos };
}

// De werkvoorbereider keurt een afgemelde PM-taak van de externe ploeg goed (vanaf versie 27). De taak komt bij de taken van de PM-bon;
// zijn alle taken van de bon gedaan, dan krijgt hij zijn registratienummer. Onderdeel bestellen zet een storing in het dienstrapport, waar de geplande taak een CM-bon van maakt.
function extWerkBlad_() {
  const s = SpreadsheetApp.openById(SHEET_ID);
  const b = s.getSheetByName('ExternWerk') || s.insertSheet('ExternWerk', s.getNumSheets());
  b.getRange('A:I').setNumberFormat('@');
  b.getRange(1, 1, 1, EXTWERKKOP.length).setValues([EXTWERKKOP]);
  return b;
}
// Alle regels, of alleen die van één monteur (1 tot en met 8): een monteur leest alleen zijn eigen bonnen.
function extWerkRijen_(monteur) {
  const b = SpreadsheetApp.openById(SHEET_ID).getSheetByName('ExternWerk');
  if (!b || b.getLastRow() < 2) return [];
  return b.getRange(2, 1, b.getLastRow() - 1, EXTWERKKOP.length).getDisplayValues().slice(-800).map(r => {
    const o = {};
    EXTWERKKOP.forEach((k, i) => { o[k] = r[i]; });
    try { o.gegevens = JSON.parse(o.gegevens || '{}'); } catch (f) { o.gegevens = {}; }
    delete o.log;
    return o;
  }).filter(o => !monteur || o.monteur === String(monteur));
}
// Past de regel van een bon op een zaterdag aan, of maakt hem. pas(x) zet de velden; het logboek in de regel vult alleen aan.
function zetExtWerk_(sleutel, datum, pas, logtekst) {
  const b = extWerkBlad_();
  const n = b.getLastRow();
  const rijen = n > 1 ? b.getRange(2, 1, n - 1, EXTWERKKOP.length).getValues() : [];
  const i = rijen.findIndex(r => r[0] === sleutel && r[1] === datum);
  const x = {};
  EXTWERKKOP.forEach((k, j) => { x[k] = i >= 0 ? String(rijen[i][j]) : ''; });
  x.sleutel = sleutel; x.datum = datum;
  if (!x.status) x.status = 'Niet toegewezen';
  if (pas(x) === false) return null;
  x.tijd = nu_();
  x.log = (x.log ? x.log + '\n' : '') + x.tijd + ' ' + schoon_(logtekst).slice(0, 200);
  const rij = EXTWERKKOP.map(k => k === 'gegevens' && typeof x[k] !== 'string' ? JSON.stringify(x[k]) : String(x[k] == null ? '' : x[k]));
  if (i >= 0) b.getRange(i + 2, 1, 1, rij.length).setValues([rij]);
  else b.appendRow(rij);
  return x;
}
// De teamleider wijst bonnen toe aan monteur 1 tot en met 8, of haalt de monteur eraf. Een afgetekende bon blijft zoals hij is.
function zetExtToewijs_(d) {
  if (!/^\d{2}-\d{2}-\d{4}$/.test(d.datum) || !Array.isArray(d.lijst) || !d.lijst.length) return { fout: 'onjuiste invoer' };
  const uit = [];
  d.lijst.slice(0, 80).forEach(y => {
    const m = String(y.monteur || '');
    if (!EXTSLEUTEL_RE.test(String(y.sleutel)) || !/^[1-8]?$/.test(m)) return;
    const x = zetExtWerk_(String(y.sleutel), d.datum, x => {
      if (x.status === 'Afgetekend') return false;
      if (x.monteur !== m) { x.monteur = m; x.status = m ? 'Toegewezen' : 'Niet toegewezen'; x.reden = ''; }
    }, m ? 'toegewezen aan monteur ' + m : 'monteur eraf gehaald');
    if (x) uit.push({ sleutel: x.sleutel, monteur: x.monteur, status: x.status, tijd: x.tijd });
  });
  return { ok: true, werk: uit };
}
// De teamleider stuurt een bon terug naar de monteur, met een reden.
function zetExtTerug_(d) {
  const reden = String(d.reden == null ? '' : d.reden).trim();
  if (!EXTSLEUTEL_RE.test(String(d.sleutel)) || !/^\d{2}-\d{2}-\d{4}$/.test(d.datum) || !reden) return { fout: 'onjuiste invoer' };
  const x = zetExtWerk_(d.sleutel, d.datum, x => { if (x.status === 'Afgetekend' || !x.monteur) return false; x.status = 'Teruggestuurd'; x.reden = reden.slice(0, 500); }, 'teruggestuurd: ' + reden);
  return x ? { ok: true, status: x.status, tijd: x.tijd } : { fout: 'kan niet terug' };
}
// De monteur zet zijn werk klaar voor controle. Hij tekent niet: dat doet de teamleider. Foto's van onderdelen gaan meteen naar Drive.
function zetExtKlaar_(d) {
  const t = x => String(x == null ? '' : x).trim();
  const m = String(d.monteur || ''), uren = Number(String(d.uren).replace(',', '.'));
  const ond = (Array.isArray(d.onderdelen) ? d.onderdelen : []).slice(0, 6).map(x => ({ onderdeel: t(x.onderdeel).slice(0, 200), spec: t(x.spec).slice(0, 300), foto: x.foto || '' }));
  if (!EXTSLEUTEL_RE.test(String(d.sleutel)) || !/^\d{2}-\d{2}-\d{4}$/.test(d.datum) || !/^[1-8]$/.test(m) || !t(d.naam) || !EXTERNSTATUS.includes(d.status) || !t(d.uitvoerder) || !(uren > 0 && uren <= 200)) return { fout: 'onjuiste invoer' };
  if (d.status === 'Onderdeel bestellen' && (!ond.length || ond.some(x => !x.onderdeel || !x.foto))) return { fout: 'onjuiste invoer' };
  if (d.status === 'Deels uitgevoerd' && (!t(d.gedaan) || !t(d.nog))) return { fout: 'onjuiste invoer' };
  if (ond.some(x => String(x.foto).length > MAX_FOTO)) return { fout: 'foto te groot' };
  const b = SpreadsheetApp.openById(SHEET_ID).getSheetByName('ExternWerk');
  const n = b ? b.getLastRow() : 0;
  const rij = n > 1 ? b.getRange(2, 1, n - 1, EXTWERKKOP.length).getValues().find(r => r[0] === d.sleutel && r[1] === d.datum) : null;
  if (!rij || String(rij[2]) !== m || rij[4] === 'Afgetekend') return { fout: 'niet toegewezen' };
  const nu = Date.now();
  ond.forEach((x, i) => { if (/^[\w-]{20,80}$/.test(String(x.foto))) return; x.foto = map_().createFile(Utilities.newBlob(Utilities.base64Decode(x.foto), 'image/jpeg', 'extern-' + d.sleutel.replace('|', '-') + '-' + nu + '-' + (i + 1) + '.jpg')).getId(); });
  const g = { status: d.status, uitvoerder: t(d.uitvoerder).slice(0, 200), uren: uren, gedaan: t(d.gedaan).slice(0, 1000), nog: t(d.nog).slice(0, 1000), opmerking: t(d.opmerking).slice(0, 1000), veegschoon: !!d.veegschoon, vrij: !!d.vrij, onderdelen: ond };
  const x = zetExtWerk_(d.sleutel, d.datum, x => { x.naam = t(d.naam).slice(0, 100); x.status = 'Klaar voor controle'; x.reden = ''; x.gegevens = g; }, 'klaar voor controle door ' + t(d.naam));
  return { ok: true, tijd: x.tijd, gegevens: g };
}

function zetExternPm_(b, d) {
  const t = x => String(x == null ? '' : x).trim();
  const s = SpreadsheetApp.openById(SHEET_ID);
  const p = s.getSheetByName('PM');
  const n = p ? p.getLastRow() : 0;
  const rij = n > 1 ? p.getRange(2, 1, n - 1, PMKOP.length).getValues().find(r => r[0] === d.pmbon) : null;
  if (rij && rij[7]) return { ok: true, al: true, reg: rij[7] };
  const taken = rij ? String(rij[3]).split(',').filter(x => /^PM-\d+$/.test(x)) : [];
  if (d.status === 'Uitgevoerd' && taken.indexOf(d.taak) < 0) taken.push(d.taak);
  const alle = String(d.alle).split(',').filter(x => /^PM-\d+$/.test(x));
  const klaar = alle.length > 0 && alle.every(x => taken.indexOf(x) >= 0);
  const regel = 'Externe ploeg ' + d.taak + ': ' + d.status.toLowerCase() + ', ' + t(d.uitvoerder).slice(0, 200) + ', ' + String(d.uren) + ' uur' + (t(d.opmerking) ? ', ' + t(d.opmerking).slice(0, 600) : '') + '. Afgetekend door ' + t(d.teamleider).slice(0, 100) + '.';
  const opm = [rij ? String(rij[4]) : '', regel].filter(Boolean).join(' ');
  const datum = /^\d{2}-\d{2}-\d{4}$/.test(d.datum) ? d.datum : rij ? String(rij[1]) : '';
  const uit = zetPm_({ nr: d.pmbon, datum: datum, status: klaar ? 'Uitgevoerd' : 'Deels uitgevoerd', taken: taken.join(','), opmerking: opm, door: t(d.teamleider).slice(0, 100) + ' (externe ploeg)' });
  if (d.status === 'Onderdeel bestellen') {
    const ond = (Array.isArray(d.onderdelen) ? d.onderdelen : []).slice(0, 6);
    const foto = ond.map(x => t(x.foto)).filter(x => /^[\w-]{10,80}$/.test(x)).join(',');
    const id = Utilities.getUuid().slice(0, 8);
    b.getRange(1, 1, 1, KOP.length).setValues([KOP]);
    b.appendRow([id, nu_(), 'TD', schoon_('Externe ploeg, PM-taak ' + d.taak + ' (' + d.pmbon + '): onderdeel bestellen: ' + ond.map(x => t(x.onderdeel) + (t(x.spec) ? ' (' + t(x.spec) + ')' : '')).join('; ')), schoon_(d.lijn), schoon_(d.machine), schoon_(t(d.teamleider) + ' (externe ploeg)'), '', '', 'Nee', 'Rapport', '', '', '', foto, '', VERVOLG[2], '', '', '']);
    naarWachtrij_(b);
  }
  return Object.assign({ ok: true }, uit);
}

function olRijen_() {
  const b = SpreadsheetApp.openById(SHEET_ID).getSheetByName('Opnamelijst');
  if (!b || b.getLastRow() < 2) return [];
  return b.getRange(2, 1, b.getLastRow() - 1, OLKOP.length).getValues().map(r => {
    const o = {};
    OLKOP.forEach((k, i) => { o[k] = String(r[i]); });
    return o;
  });
}

// Een foto gaat meteen naar Drive. In de gegevens staat daarna alleen het id.
function zetOlFoto_(d) {
  if (!d.foto || d.foto.length > MAX_FOTO) return { fout: 'foto te groot' };
  const id = map_().createFile(Utilities.newBlob(Utilities.base64Decode(d.foto), 'image/jpeg', 'opnamelijst-' + d.ol + '-' + Date.now() + '.jpg')).getId();
  return { ok: true, foto: id };
}

// Opslaan (Deels) of afmelden (Opgenomen). Afmelden zet ook een bestand in de wachtrij: daarvan maakt de geplande taak de opnamelijst in Word en PDF.
function zetOl_(d) {
  const g = d.gegevens && typeof d.gegevens === 'object' && !Array.isArray(d.gegevens) ? d.gegevens : null;
  if (!g) return { fout: 'onjuiste invoer' };
  const tekst = JSON.stringify(g);
  if (tekst.length > OLMAX) return { fout: 'te veel tekst' };
  const s = SpreadsheetApp.openById(SHEET_ID);
  const t = s.getSheetByName('Opnamelijst') || s.insertSheet('Opnamelijst', s.getNumSheets());
  t.getRange('A:E').setNumberFormat('@');
  t.getRange(1, 1, 1, OLKOP.length).setValues([OLKOP]);
  const tijd = nu_();
  const rij = [d.ol, d.status, tekst, schoon_(d.door).slice(0, 200), tijd];
  const n = t.getLastRow();
  const ols = n > 1 ? t.getRange(2, 1, n - 1, 1).getDisplayValues().map(r => r[0]) : [];
  const i = ols.indexOf(d.ol);
  if (i >= 0) t.getRange(i + 2, 1, 1, rij.length).setValues([rij]);
  else t.appendRow(rij);
  if (d.status === 'Opgenomen') zetBonstatus_('OLA-' + d.ol.replace('.', '-') + '-' + Date.now(), 'Open', { olopname: { ol: d.ol, status: d.status, door: schoon_(d.door), tijd: tijd, gegevens: g } }, d.door);
  return { ok: true, tijd: tijd };
}

// Een bon die helemaal is afgemeld krijgt een doorlopend registratienummer en een bestand voor de geplande taak, die de registratiebon maakt.
// Dit draait binnen de lock, dus nooit dubbel. Met een nummer ligt de regel vast.
function zetPm_(d) {
  const s = SpreadsheetApp.openById(SHEET_ID);
  const b = s.getSheetByName('PM') || s.insertSheet('PM', s.getNumSheets());
  b.getRange('A:H').setNumberFormat('@');
  b.getRange(1, 1, 1, PMKOP.length).setValues([PMKOP]);
  const n = b.getLastRow();
  const rijen = n > 1 ? b.getRange(2, 1, n - 1, PMKOP.length).getValues() : [];
  const i = rijen.findIndex(r => r[0] === d.nr);
  if (i >= 0 && rijen[i][7]) return { tijd: rijen[i][6], reg: rijen[i][7], al: true };
  const tijd = nu_();
  let reg = '';
  if (d.status === 'Uitgevoerd') {
    const hoogste = rijen.reduce((h, r) => Math.max(h, Number((/^PMR-(\d+)$/.exec(r[7]) || [0, 0])[1])), 0);
    reg = 'PMR-' + (hoogste + 1);
    const punten = bevRijen_().filter(x => x.nr === d.nr).map(x => ({ naam: x.naam, opmerking: x.opmerking, bon: x.bon }));
    zetBonstatus_(reg, d.status, { pmreg: { reg: reg, nr: d.nr, opmerking: String(d.opmerking == null ? '' : d.opmerking).slice(0, 1000), door: schoon_(d.door), tijd: tijd, punten: punten } }, d.door);
  }
  const rij = [d.nr, d.datum, d.status, d.taken, schoon_(d.opmerking), schoon_(d.door), tijd, reg];
  if (i >= 0) b.getRange(i + 2, 1, 1, rij.length).setValues([rij]);
  else b.appendRow(rij);
  return { tijd: tijd, reg: reg };
}

// Productie-app (pilot). De teamleider vult per dienst in, de werkvoorbereider verbetert en zet hem op Gecontroleerd.
// Een gecontroleerde dienst kan de productiesleutel niet meer aanpassen. Het logboek vult alleen aan.
function prodBlad_() {
  const s = SpreadsheetApp.openById(SHEET_ID);
  const b = s.getSheetByName('Productie') || s.insertSheet('Productie', s.getNumSheets());
  b.getRange('A:K').setNumberFormat('@');
  b.getRange(1, 1, 1, PRODKOP.length).setValues([PRODKOP]);
  return b;
}
function prodDag_(t) {
  const m = /^(\d{2})-(\d{2})-(\d{4})$/.exec(String(t || ''));
  return m ? new Date(Number(m[3]), Number(m[2]) - 1, Number(m[1])) : null;
}
function prodRijen_(dagen) {
  const b = SpreadsheetApp.openById(SHEET_ID).getSheetByName('Productie');
  if (!b || b.getLastRow() < 2) return [];
  const grens = new Date(Date.now() - dagen * 864e5);
  return b.getRange(2, 1, b.getLastRow() - 1, PRODKOP.length).getDisplayValues().filter(r => {
    const d = prodDag_(r[1]);
    return d && d >= grens;
  }).map(r => {
    const o = {};
    PRODKOP.forEach((k, i) => { o[k] = r[i]; });
    try { o.gegevens = JSON.parse(r[5] || '{}'); } catch (f) { o.gegevens = {}; }
    return o;
  });
}
function zetProductie_(d) {
  const wv = d.k === WVSLEUTEL;
  const tekst = JSON.stringify(d.gegevens && typeof d.gegevens === 'object' && !Array.isArray(d.gegevens) ? d.gegevens : {});
  if (!prodDag_(d.datum) || !PRODDIENST.includes(d.dienst) || !PRODAFDELING.includes(d.afdeling) || !PRODSTATUS.includes(d.status) || tekst.length > PRODMAX) return { fout: 'onjuiste invoer' };
  if (d.status === 'Gecontroleerd' && !wv) return { fout: 'geen toegang' };
  const b = prodBlad_();
  const n = b.getLastRow();
  const rijen = n > 1 ? b.getRange(2, 1, n - 1, PRODKOP.length).getDisplayValues() : [];
  const i = rijen.findIndex(r => r[1] === d.datum && r[2] === d.dienst && r[3] === d.afdeling);
  const oud = i >= 0 ? rijen[i] : null;
  if (oud && oud[4] === 'Gecontroleerd' && !wv) return { fout: 'gecontroleerd', status: 'Gecontroleerd' };
  const tijd = nu_();
  const door = schoon_(d.door).slice(0, 100);
  const wat = d.status === 'Gecontroleerd' ? (oud && oud[4] === 'Gecontroleerd' ? 'paste de gecontroleerde dienst aan' : 'zette de dienst op Gecontroleerd') : wv ? (oud && oud[4] === 'Gecontroleerd' ? 'haalde de controle weg' : 'verbeterde de dienst') : oud ? 'paste de dienst aan' : 'verstuurde de dienst';
  const log = ((oud ? oud[10] + '\n' : '') + tijd + ' ' + (door || (wv ? 'Werkvoorbereider' : 'Productie')) + ' ' + wat + (d.status === 'Onvolledig' ? ' (onvolledig)' : '') + '.').slice(-5000);
  const gecontroleerd = d.status === 'Gecontroleerd' ? [oud && oud[4] === 'Gecontroleerd' ? oud[8] : door, oud && oud[4] === 'Gecontroleerd' ? oud[9] : tijd] : ['', ''];
  const id = oud ? oud[0] : Utilities.getUuid().slice(0, 8);
  // Wie de dienst verstuurde blijft staan als de werkvoorbereider verbetert.
  const rij = [id, d.datum, d.dienst, d.afdeling, d.status, tekst, wv && oud ? oud[6] : door, wv && oud ? oud[7] : tijd, gecontroleerd[0], gecontroleerd[1], log];
  if (oud) b.getRange(i + 2, 1, 1, rij.length).setValues([rij]);
  else b.appendRow(rij);
  return { ok: true, id: id, tijd: tijd, status: d.status, log: log, door: rij[6], verstuurd: rij[7], gecontroleerd_door: rij[8], gecontroleerd_op: rij[9] };
}

function doGet(e) {
  const p = e.parameter || {};
  const monteur = p.k === MONTEURSLEUTEL;
  if (p.k === OUTPUTSLEUTEL) return uit_({ output: outputRijen_() });
  // Productie-app: de diensten van de laatste drie weken. De werkvoorbereider leest ze los van de rest, met zijn eigen sleutel.
  if (p.k === PRODUCTIESLEUTEL) return uit_({ productie: prodRijen_(21) });
  // De externe ploeg leest alleen zijn eigen afmeldingen, verder niets.
  if (p.k === EXTERNSLEUTEL && !p.foto) return uit_({ extern: externRijen_(), werk: extWerkRijen_() });
  // Een monteur van de externe ploeg leest alleen zijn eigen bonnen (vanaf versie 28).
  if (p.k === EXTMONTEURSLEUTEL && EXTMONTEURSLEUTEL.length > 20 && !p.foto) return uit_({ werk: extWerkRijen_(/^[1-8]$/.test(String(p.m)) ? p.m : '0') });
  if ((p.k === EXTERNSLEUTEL || (p.k === EXTMONTEURSLEUTEL && EXTMONTEURSLEUTEL.length > 20)) && p.foto) {
    const ploeg = p.k === EXTERNSLEUTEL;
    const werk = extWerkRijen_(ploeg ? '' : (/^[1-8]$/.test(String(p.m)) ? p.m : '0')).some(x => (x.gegevens.onderdelen || []).some(o => o.foto === p.foto));
    const af = ploeg && externRijen_().some(x => x.handtekening === p.foto || heeftFoto_(x.fotos, p.foto));
    if (!werk && !af) return uit_({ fout: 'foto niet gevonden' });
    return uit_({ foto: Utilities.base64Encode(DriveApp.getFileById(p.foto).getBlob().getBytes()) });
  }
  if (p.k === WVSLEUTEL && p.productie) return uit_({ productie: prodRijen_(70) });
  const pm = p.k === PMSLEUTEL;
  if (pm && !p.foto) return uit_({ pm: pmRijen_(), bevindingen: bevRijen_() });
  // De kijkinlog leest hetzelfde als de TD-sleutel. In doPost bestaat deze sleutel niet, dus opslaan kan niet.
  if (p.k !== SLEUTEL && p.k !== KIJKSLEUTEL && !monteur && !pm) return uit_({ fout: 'geen toegang' });
  const rijen = blad_().getDataRange().getDisplayValues().slice(1).filter(r => r[10] !== 'Verwijderd');
  if (p.foto) {
    // Alleen foto's die bij een regel horen, nooit andere bestanden uit Drive. De PM-inlog ziet alleen foto's van bevindingen.
    const bevinding = !monteur && bevRijen_().some(x => heeftFoto_(x.foto, p.foto));
    const opname = !pm && opnameRijen_().some(x => x.foto === p.foto);
    const ol = !pm && !opname && String(p.foto).length > 15 && olRijen_().some(x => x.gegevens.indexOf('"' + p.foto + '"') >= 0);
    const ext = !pm && !monteur && (externRijen_().some(x => x.handtekening === p.foto || heeftFoto_(x.fotos, p.foto)) || extWerkRijen_().some(x => (x.gegevens.onderdelen || []).some(o => o.foto === p.foto)));
    if (!bevinding && !opname && !ol && !ext && (pm || !rijen.some(r => heeftFoto_(r[14], p.foto) && (!monteur || r[2] === 'TD')))) return uit_({ fout: 'foto niet gevonden' });
    return uit_({ foto: Utilities.base64Encode(DriveApp.getFileById(p.foto).getBlob().getBytes()) });
  }
  if (monteur || p.rapport) {
    const rapport = rijen.filter(r => r[2] === 'TD').slice(-500).map(object_);
    // De monteur ziet aangevinkte en afgemelde bonnen meteen, verder niets uit de wachtrij.
    if (monteur) return uit_({ rapport: rapport, olopname: olRijen_(), bonstatus: bonstatus_().filter(x => x.rij && (x.rij.week || x.rij.weekaf || x.rij.opname || x.rij.opdrachtaf || x.rij.olplan || x.rij.olopname || x.rij.rooster || x.rij.roostermensen)).map(x => ({ nr: x.nr, status: x.status, tijd: x.tijd, door: x.door, rij: { week: x.rij.week, weekaf: x.rij.weekaf, opname: x.rij.opname, opdrachtaf: x.rij.opdrachtaf, olplan: x.rij.olplan, rooster: x.rij.rooster, roostermensen: x.rij.roostermensen, olopname: x.rij.olopname && { ol: x.rij.olopname.ol, status: x.rij.olopname.status, door: x.rij.olopname.door, tijd: x.rij.olopname.tijd } } })) });
    return uit_({ rapport: rapport });
  }
  return uit_({ meldingen: rijen.filter(r => r[10] === 'Open').map(object_), bonstatus: bonstatus_(), output: outputRijen_(), pm: pmRijen_(), bevindingen: bevRijen_(), olopname: olRijen_(), extern: externRijen_(), werk: extWerkRijen_() });
}

function doPost(e) {
  const d = JSON.parse(e.postData.contents);
  // De meldinlog mag alleen nieuwe meldingen versturen, nooit iets lezen of wijzigen.
  const melder = d.k === MELDSLEUTEL && d.actie === 'nieuw' && d.letter === '';
  const monteur = d.k === MONTEURSLEUTEL && d.actie === 'nieuw' && d.letter === 'TD';
  // Verwijderen en een bonstatus aanpassen kan alleen met de sleutel van de werkvoorbereider. Die sleutel kan verder niets.
  const wvActie = d.actie === 'verwijder' || d.actie === 'bonstatus' || d.actie === 'externpm';
  // De ploegen kunnen alleen hun output invullen.
  const ploeg = d.k === OUTPUTSLEUTEL && d.actie === 'output';
  // De PM-inlog kan alleen PM-bonnen afmelden en bevindingen bij controlepunten vastleggen.
  const pm = d.k === PMSLEUTEL && (d.actie === 'pm' || d.actie === 'pmbev');
  // Elke dienst kan het vervolg van een storing in het dienstrapport aanpassen, verder niets.
  const rapport = d.k === MONTEURSLEUTEL && d.actie === 'rapport';
  // De monteur meldt een uitvoerbare bon af. Meer dan afmelden kan deze actie niet.
  const weekbon = d.k === MONTEURSLEUTEL && d.actie === 'weekbon';
  // De monteur meldt een opnamebon af: specificaties en foto, meer niet.
  const opname = d.k === MONTEURSLEUTEL && d.actie === 'opname';
  // De monteur meldt de opdracht van de werkvoorbereider af (vanaf versie 23). De bon zelf blijft open.
  const opdracht = d.k === MONTEURSLEUTEL && d.actie === 'opdracht';
  // Productie-app: de teamleider vult zijn dienst in. De werkvoorbereider verbetert en zet hem op Gecontroleerd.
  const productie = (d.k === PRODUCTIESLEUTEL || d.k === WVSLEUTEL) && d.actie === 'productie';
  // De monteur vult een opnamelijst in en slaat hem op of meldt hem af (vanaf versie 24). Meer kan deze actie niet.
  const ol = d.k === MONTEURSLEUTEL && (d.actie === 'olopname' || d.actie === 'olfoto');
  // De externe ploeg meldt alleen bonnen van de zaterdag af (vanaf versie 26). Meer kan deze sleutel niet.
  // Vanaf versie 28 wijst de teamleider ook bonnen toe en stuurt hij een bon terug naar de monteur.
  const extern = d.k === EXTERNSLEUTEL && EXTERNSLEUTEL.length > 20 && ['extern', 'exttoewijs', 'extterug'].includes(d.actie);
  // Een monteur van de externe ploeg zet alleen zijn eigen werk klaar voor controle (vanaf versie 28).
  const extmonteur = d.k === EXTMONTEURSLEUTEL && EXTMONTEURSLEUTEL.length > 20 && d.actie === 'extklaar';
  if (wvActie ? d.k !== WVSLEUTEL : d.k !== SLEUTEL && !melder && !monteur && !ploeg && !pm && !rapport && !weekbon && !opname && !opdracht && !productie && !ol && !extern && !extmonteur) return uit_({ fout: 'geen toegang' });
  VAN_ = d.k === WVSLEUTEL ? 'wv' : d.k === SLEUTEL ? 'td' : d.k === MONTEURSLEUTEL ? 'monteur' : d.k === PMSLEUTEL ? 'pm' : d.k === OUTPUTSLEUTEL ? 'output' : d.k === PRODUCTIESLEUTEL ? 'productie' : d.k === EXTERNSLEUTEL ? 'extern' : d.k === EXTMONTEURSLEUTEL ? 'extmonteur' : 'melden';
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const b = blad_();
    b.getRange('B:B').setNumberFormat('@');
    if (d.actie === 'nieuw') {
      const id = Utilities.getUuid().slice(0, 8);
      const tijd = nu_();
      b.getRange(1, 1, 1, KOP.length).setValues([KOP]);
      const code = d.letter === '' ? code_(b) : '';
      const foto = fotosOp_(d, 'melding-' + id);
      if (foto === null) return uit_({ fout: 'foto te groot' });
      b.appendRow([id, tijd, schoon_(d.letter), schoon_(d.melding), schoon_(d.lijn), schoon_(d.machine), schoon_(d.melder), schoon_(d.actiehouder), schoon_(d.datum), d.bon_nodig ? 'Ja' : 'Nee', d.letter === 'TD' ? 'Rapport' : 'Open', '', '', schoon_(d.oplossing), foto, schoon_(d.risico), schoon_(d.vervolg), code, '', prio_(d.prio)]);
      naarWachtrij_(b);
      return uit_({ ok: true, id: id, tijd: tijd, foto: foto, code: code });
    }
    if (d.actie === 'output') {
      const kg = Number(d.output);
      if (!/^\d{2}-\d{2}-\d{4}$/.test(d.datum) || !PLOEGEN.includes(d.ploeg) || !LIJNEN.includes(d.lijn) || d.output === '' || !(kg >= 0 && kg < 10000000)) return uit_({ fout: 'onjuiste invoer' });
      return uit_({ ok: true, vervangen: zetOutput_(d) });
    }
    if (d.actie === 'productie') return uit_(zetProductie_(d));
    if (d.actie === 'pm') {
      if (!/^PM-\d{6}-\d{1,2}$/.test(d.nr) || !/^\d{2}-\d{2}-\d{4}$/.test(d.datum) || !PMSTATUS.includes(d.status) || !/^PM-\d+(,PM-\d+)*$/.test(d.taken)) return uit_({ fout: 'onjuiste invoer' });
      return uit_(Object.assign({ ok: true }, zetPm_(d)));
    }
    if (d.actie === 'pmbev') {
      if (!/^PM-\d{6}-\d{1,2}$/.test(d.nr) || !/^PM-\d+$/.test(d.punt) || !String(d.opmerking == null ? '' : d.opmerking).trim()) return uit_({ fout: 'onjuiste invoer' });
      return uit_(zetBevinding_(b, d));
    }
    if (d.actie === 'rapport') {
      if (!VERVOLG.includes(d.vervolg)) return uit_({ fout: 'onjuiste invoer' });
      return uit_(zetRapport_(b, d));
    }
    if (d.actie === 'weekbon') {
      if (!/^(CM\d+|SQDM-\d+)$/.test(d.nr) || !['Uitgevoerd', 'Deels uitgevoerd'].includes(d.status)) return uit_({ fout: 'onjuiste invoer' });
      zetBonstatus_(d.nr, d.status, { weekaf: { tekst: String(d.tekst == null ? '' : d.tekst).slice(0, 1000), door: schoon_(d.door), status: d.status, tijd: nu_() } }, d.door);
      return uit_({ ok: true, tijd: nu_() });
    }
    if (d.actie === 'opdracht') {
      // Een eigen wachtrijbestand per afmelding: de registratie mag een statuswijziging op de bon niet overschrijven, en andersom.
      const tekst = String(d.tekst == null ? '' : d.tekst).trim();
      if (!/^(CM\d+|SQDM-\d+)$/.test(d.nr) || !tekst) return uit_({ fout: 'onjuiste invoer' });
      const tijd = nu_();
      zetBonstatus_('OPD-' + d.nr + '-' + Date.now(), 'Open', { opdrachtaf: { nr: d.nr, opdracht: String(d.opdracht == null ? '' : d.opdracht).slice(0, 1000), tekst: tekst.slice(0, 1000), door: schoon_(d.door), tijd: tijd } }, d.door);
      return uit_({ ok: true, tijd: tijd });
    }
    if (d.actie === 'extern') return uit_(zetExtern_(d));
    if (d.actie === 'exttoewijs') return uit_(zetExtToewijs_(d));
    if (d.actie === 'extterug') return uit_(zetExtTerug_(d));
    if (d.actie === 'extklaar') return uit_(zetExtKlaar_(d));
    if (d.actie === 'externpm') {
      if (!/^PM-\d{6}-\d{1,2}$/.test(d.pmbon) || !/^PM-\d+$/.test(d.taak) || !EXTERNSTATUS.includes(d.status)) return uit_({ fout: 'onjuiste invoer' });
      return uit_(zetExternPm_(b, d));
    }
    if (d.actie === 'opname') {
      if (!/^(CM\d+|SQDM-\d+)$/.test(d.nr) || !OPNAMESTATUS.includes(d.status)) return uit_({ fout: 'onjuiste invoer' });
      return uit_(zetOpname_(d));
    }
    if (d.actie === 'olfoto' || d.actie === 'olopname') {
      if (!/^OL\d{1,2}\.\d{1,3}$/.test(d.ol) || (d.actie === 'olopname' && !OLSTATUS.includes(d.status))) return uit_({ fout: 'onjuiste invoer' });
      return uit_(d.actie === 'olfoto' ? zetOlFoto_(d) : zetOl_(d));
    }
    if (d.actie === 'verwijder') {
      if (d.bon && !/^[A-Za-z0-9-]{1,20}$/.test(d.bon)) return uit_({ fout: 'onbekende bon' });
      const rijen = b.getDataRange().getDisplayValues();
      const i = rijen.findIndex((r, n) => n > 0 && r[0] === d.id);
      if (i < 0) return uit_({ fout: 'melding niet gevonden' });
      verwijder_(b, i + 1, rijen[i], d);
      return uit_({ ok: true });
    }
    if (d.actie === 'bonstatus') {
      if (!/^[A-Za-z0-9-]{1,20}$/.test(d.nr) || !BONSTATUS.includes(d.status)) return uit_({ fout: 'onbekende status' });
      zetBonstatus_(d.nr, d.status, d.rij, d.door);
      return uit_({ ok: true });
    }
    if (d.actie === 'prio') {
      b.getRange(1, 1, 1, KOP.length).setValues([KOP]);
      const ids = b.getRange(1, 1, b.getLastRow(), 1).getDisplayValues().map(r => r[0]);
      (d.lijst || []).forEach(x => {
        const i = ids.indexOf(x.id);
        if (i > 0) b.getRange(i + 1, 20).setValue(prio_(x.prio));
      });
      return uit_({ ok: true });
    }
    // Een actie staat op Bezig of weer op Open. Alleen deze kolom verandert, de opvolging blijft zoals hij is.
    if (d.actie === 'voortgang') {
      const ids = b.getRange(1, 1, b.getLastRow(), 1).getDisplayValues();
      for (let i = 1; i < ids.length; i++) {
        if (ids[i][0] === d.id) {
          b.getRange(1, 1, 1, KOP.length).setValues([KOP]);
          b.getRange(i + 1, 21).setValue(d.voortgang === 'Bezig' ? 'Bezig' : '');
          return uit_({ ok: true });
        }
      }
      return uit_({ fout: 'melding niet gevonden' });
    }
    if (d.actie === 'gereed' || d.actie === 'verplaats' || d.actie === 'bijwerken') {
      const ids = b.getRange(1, 1, b.getLastRow(), 1).getDisplayValues();
      for (let i = 1; i < ids.length; i++) {
        if (ids[i][0] === d.id) {
          if (d.actie === 'gereed') {
            b.getRange(i + 1, 11, 1, 3).setValues([['Afgehandeld', nu_(), schoon_(d.door)]]);
            // De bon hoort bij de melding en gaat tegelijk op Uitgevoerd. Alleen de status: wat er al in de wachtrij stond, blijft bewaard.
            if (d.bon && /^[A-Za-z0-9-]{1,20}$/.test(d.bon)) zetBonstatus_(d.bon, 'Uitgevoerd', null, d.door);
          }
          else if (d.actie === 'verplaats') b.getRange(i + 1, 3).setValue(['S', 'Q', 'D'].includes(d.letter) ? d.letter : '');
          else {
            b.getRange(i + 1, 5, 1, 2).setValues([[schoon_(d.lijn), schoon_(d.machine)]]);
            b.getRange(i + 1, 8, 1, 3).setValues([[schoon_(d.actiehouder), schoon_(d.datum), d.bon_nodig ? 'Ja' : 'Nee']]);
            b.getRange(i + 1, 14).setValue(schoon_(d.oplossing));
            if (d.prio !== undefined) b.getRange(i + 1, 20).setValue(prio_(d.prio));
            if (!d.bon_nodig) uitWachtrij_(b, i + 1, d.id);
            naarWachtrij_(b);
          }
          return uit_({ ok: true });
        }
      }
      return uit_({ fout: 'melding niet gevonden' });
    }
    return uit_({ fout: 'onbekende actie' });
  } finally {
    lock.releaseLock();
  }
}
