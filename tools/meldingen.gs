// TD Hub meldingen, versie 24: ontvangt meldingen van de site en bewaart ze in de Google Sheet.
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
  let foto = '';
  if (d.foto) {
    if (d.foto.length > MAX_FOTO) return { fout: 'foto te groot' };
    foto = map_().createFile(Utilities.newBlob(Utilities.base64Decode(d.foto), 'image/jpeg', 'bevinding-' + id + '.jpg')).getId();
  }
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
  if (p.k === WVSLEUTEL && p.productie) return uit_({ productie: prodRijen_(70) });
  const pm = p.k === PMSLEUTEL;
  if (pm && !p.foto) return uit_({ pm: pmRijen_(), bevindingen: bevRijen_() });
  // De kijkinlog leest hetzelfde als de TD-sleutel. In doPost bestaat deze sleutel niet, dus opslaan kan niet.
  if (p.k !== SLEUTEL && p.k !== KIJKSLEUTEL && !monteur && !pm) return uit_({ fout: 'geen toegang' });
  const rijen = blad_().getDataRange().getDisplayValues().slice(1).filter(r => r[10] !== 'Verwijderd');
  if (p.foto) {
    // Alleen foto's die bij een regel horen, nooit andere bestanden uit Drive. De PM-inlog ziet alleen foto's van bevindingen.
    const bevinding = !monteur && bevRijen_().some(x => x.foto === p.foto);
    const opname = !pm && opnameRijen_().some(x => x.foto === p.foto);
    const ol = !pm && !opname && String(p.foto).length > 15 && olRijen_().some(x => x.gegevens.indexOf('"' + p.foto + '"') >= 0);
    if (!bevinding && !opname && !ol && (pm || !rijen.some(r => r[14] === p.foto && (!monteur || r[2] === 'TD')))) return uit_({ fout: 'foto niet gevonden' });
    return uit_({ foto: Utilities.base64Encode(DriveApp.getFileById(p.foto).getBlob().getBytes()) });
  }
  if (monteur || p.rapport) {
    const rapport = rijen.filter(r => r[2] === 'TD').slice(-500).map(object_);
    // De monteur ziet aangevinkte en afgemelde bonnen meteen, verder niets uit de wachtrij.
    if (monteur) return uit_({ rapport: rapport, olopname: olRijen_(), bonstatus: bonstatus_().filter(x => x.rij && (x.rij.week || x.rij.weekaf || x.rij.opname || x.rij.opdrachtaf || x.rij.olplan || x.rij.olopname)).map(x => ({ nr: x.nr, status: x.status, tijd: x.tijd, door: x.door, rij: { week: x.rij.week, weekaf: x.rij.weekaf, opname: x.rij.opname, opdrachtaf: x.rij.opdrachtaf, olplan: x.rij.olplan, olopname: x.rij.olopname && { ol: x.rij.olopname.ol, status: x.rij.olopname.status, door: x.rij.olopname.door, tijd: x.rij.olopname.tijd } } })) });
    return uit_({ rapport: rapport });
  }
  return uit_({ meldingen: rijen.filter(r => r[10] === 'Open').map(object_), bonstatus: bonstatus_(), output: outputRijen_(), pm: pmRijen_(), bevindingen: bevRijen_(), olopname: olRijen_() });
}

function doPost(e) {
  const d = JSON.parse(e.postData.contents);
  // De meldinlog mag alleen nieuwe meldingen versturen, nooit iets lezen of wijzigen.
  const melder = d.k === MELDSLEUTEL && d.actie === 'nieuw' && d.letter === '';
  const monteur = d.k === MONTEURSLEUTEL && d.actie === 'nieuw' && d.letter === 'TD';
  // Verwijderen en een bonstatus aanpassen kan alleen met de sleutel van de werkvoorbereider. Die sleutel kan verder niets.
  const wvActie = d.actie === 'verwijder' || d.actie === 'bonstatus';
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
  if (wvActie ? d.k !== WVSLEUTEL : d.k !== SLEUTEL && !melder && !monteur && !ploeg && !pm && !rapport && !weekbon && !opname && !opdracht && !productie && !ol) return uit_({ fout: 'geen toegang' });
  VAN_ = d.k === WVSLEUTEL ? 'wv' : d.k === SLEUTEL ? 'td' : d.k === MONTEURSLEUTEL ? 'monteur' : d.k === PMSLEUTEL ? 'pm' : d.k === OUTPUTSLEUTEL ? 'output' : d.k === PRODUCTIESLEUTEL ? 'productie' : 'melden';
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
      let foto = '';
      if (d.foto) {
        if (d.foto.length > MAX_FOTO) return uit_({ fout: 'foto te groot' });
        foto = map_().createFile(Utilities.newBlob(Utilities.base64Decode(d.foto), 'image/jpeg', 'melding-' + id + '.jpg')).getId();
      }
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
