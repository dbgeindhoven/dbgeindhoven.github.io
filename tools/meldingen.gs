// TD Hub meldingen: ontvangt meldingen van de site en bewaart ze in de Google Sheet.
// De echte waarden van SHEET_ID en SLEUTEL staan niet in deze repository.
const SHEET_ID = '__SHEET_ID__';
const SLEUTEL = '__SLEUTEL__';
const MELDSLEUTEL = '__MELDSLEUTEL__';
const MONTEURSLEUTEL = '__MONTEURSLEUTEL__';
const WVSLEUTEL = '__WVSLEUTEL__';
const KIJKSLEUTEL = '__KIJKSLEUTEL__';
const OUTPUTSLEUTEL = '__OUTPUTSLEUTEL__';
const PMSLEUTEL = '__PMSLEUTEL__';
const WACHTRIJ = '__WACHTRIJ__';
const KOP = ['id', 'tijd', 'letter', 'melding', 'lijn', 'machine', 'melder', 'actiehouder', 'datum', 'bon_nodig', 'status', 'gereed_op', 'gereed_door', 'oplossing', 'foto', 'risico', 'vervolg', 'code', 'wachtrij', 'prio'];
const ZONE = 'Europe/Amsterdam';
const MAP = "TD Hub foto's";
const MAX_FOTO = 8000000;
const BONSTATUS = ['Open', 'Gepland', 'Bestellen', 'Besteld', 'Deels uitgevoerd', 'On hold', 'Uitgevoerd', 'Gereed', 'Dubbel', 'Vervallen'];
const VERVOLG = ['Gereed', 'Overdragen aan volgende dienst', 'Onderdeel bestellen', 'Plannen voor onderhoudstop'];

const PLOEGEN = ['ochtend', 'middag', 'nacht a', 'nacht b'];
const LIJNEN = ['Lijn 1', 'Lijn 2', 'Lijn 3'];
const OUTKOP = ['datum', 'ploeg', 'lijn', 'output', 'opmerking', 'door', 'tijd'];
const PMKOP = ['nr', 'datum', 'status', 'taken', 'opmerking', 'door', 'tijd', 'reg'];
const PMSTATUS = ['Uitgevoerd', 'Deels uitgevoerd'];
const BEVKOP = ['id', 'nr', 'punt', 'naam', 'opmerking', 'foto', 'bon', 'door', 'tijd'];
const OPNAMEKOP = ['nr', 'status', 'regels', 'opmerking', 'foto', 'door', 'tijd'];
const OPNAMESTATUS = ['Bestellen', 'Deels uitgevoerd'];

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
// Een nieuwere wijziging voor dezelfde bon vervangt de oude.
function zetBonstatus_(nr, status, rij, door) {
  const map = DriveApp.getFolderById(WACHTRIJ);
  const naam = 'status-' + nr + '.txt';
  const oud = map.getFilesByName(naam);
  while (oud.hasNext()) oud.next().setTrashed(true);
  map.createFile(naam, JSON.stringify({ nr: nr, status: status, rij: rij || null, tijd: nu_(), door: schoon_(door) }), MimeType.PLAIN_TEXT);
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

function doGet(e) {
  const p = e.parameter || {};
  const monteur = p.k === MONTEURSLEUTEL;
  if (p.k === OUTPUTSLEUTEL) return uit_({ output: outputRijen_() });
  const pm = p.k === PMSLEUTEL;
  if (pm && !p.foto) return uit_({ pm: pmRijen_(), bevindingen: bevRijen_() });
  // De kijkinlog leest hetzelfde als de TD-sleutel. In doPost bestaat deze sleutel niet, dus opslaan kan niet.
  if (p.k !== SLEUTEL && p.k !== KIJKSLEUTEL && !monteur && !pm) return uit_({ fout: 'geen toegang' });
  const rijen = blad_().getDataRange().getDisplayValues().slice(1).filter(r => r[10] !== 'Verwijderd');
  if (p.foto) {
    // Alleen foto's die bij een regel horen, nooit andere bestanden uit Drive. De PM-inlog ziet alleen foto's van bevindingen.
    const bevinding = !monteur && bevRijen_().some(x => x.foto === p.foto);
    const opname = !pm && opnameRijen_().some(x => x.foto === p.foto);
    if (!bevinding && !opname && (pm || !rijen.some(r => r[14] === p.foto && (!monteur || r[2] === 'TD')))) return uit_({ fout: 'foto niet gevonden' });
    return uit_({ foto: Utilities.base64Encode(DriveApp.getFileById(p.foto).getBlob().getBytes()) });
  }
  if (monteur || p.rapport) {
    const rapport = rijen.filter(r => r[2] === 'TD').slice(-500).map(object_);
    // De monteur ziet aangevinkte en afgemelde bonnen meteen, verder niets uit de wachtrij.
    if (monteur) return uit_({ rapport: rapport, bonstatus: bonstatus_().filter(x => x.rij && (x.rij.week || x.rij.weekaf || x.rij.opname)) });
    return uit_({ rapport: rapport });
  }
  return uit_({ meldingen: rijen.filter(r => r[10] === 'Open').map(object_), bonstatus: bonstatus_(), output: outputRijen_(), pm: pmRijen_(), bevindingen: bevRijen_() });
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
  if (wvActie ? d.k !== WVSLEUTEL : d.k !== SLEUTEL && !melder && !monteur && !ploeg && !pm && !rapport && !weekbon && !opname) return uit_({ fout: 'geen toegang' });
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
      zetBonstatus_(d.nr, d.status, { weekaf: { tekst: String(d.tekst == null ? '' : d.tekst).slice(0, 1000), door: schoon_(d.door) } }, d.door);
      return uit_({ ok: true, tijd: nu_() });
    }
    if (d.actie === 'opname') {
      if (!/^(CM\d+|SQDM-\d+)$/.test(d.nr) || !OPNAMESTATUS.includes(d.status)) return uit_({ fout: 'onjuiste invoer' });
      return uit_(zetOpname_(d));
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
    if (d.actie === 'gereed' || d.actie === 'verplaats' || d.actie === 'bijwerken') {
      const ids = b.getRange(1, 1, b.getLastRow(), 1).getDisplayValues();
      for (let i = 1; i < ids.length; i++) {
        if (ids[i][0] === d.id) {
          if (d.actie === 'gereed') {
            b.getRange(i + 1, 11, 1, 3).setValues([['Afgehandeld', nu_(), schoon_(d.door)]]);
            // De bon hoort bij de melding en gaat tegelijk op Uitgevoerd.
            if (d.bon && /^[A-Za-z0-9-]{1,20}$/.test(d.bon)) zetBonstatus_(d.bon, 'Uitgevoerd', d.rij, d.door);
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
