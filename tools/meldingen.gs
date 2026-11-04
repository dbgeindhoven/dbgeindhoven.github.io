// TD Hub meldingen: ontvangt meldingen van de site en bewaart ze in de Google Sheet.
// De echte waarden van SHEET_ID en SLEUTEL staan niet in deze repository.
const SHEET_ID = '__SHEET_ID__';
const SLEUTEL = '__SLEUTEL__';
const MELDSLEUTEL = '__MELDSLEUTEL__';
const MONTEURSLEUTEL = '__MONTEURSLEUTEL__';
const WVSLEUTEL = '__WVSLEUTEL__';
const OUTPUTSLEUTEL = '__OUTPUTSLEUTEL__';
const PMSLEUTEL = '__PMSLEUTEL__';
const WACHTRIJ = '__WACHTRIJ__';
const KOP = ['id', 'tijd', 'letter', 'melding', 'lijn', 'machine', 'melder', 'actiehouder', 'datum', 'bon_nodig', 'status', 'gereed_op', 'gereed_door', 'oplossing', 'foto', 'risico', 'vervolg', 'code', 'wachtrij', 'prio'];
const ZONE = 'Europe/Amsterdam';
const MAP = "TD Hub foto's";
const MAX_FOTO = 8000000;
const BONSTATUS = ['Open', 'Gepland', 'Besteld', 'Deels uitgevoerd', 'On hold', 'Uitgevoerd', 'Gereed', 'Dubbel', 'Vervallen'];

const PLOEGEN = ['ochtend', 'middag', 'nacht a', 'nacht b'];
const LIJNEN = ['Lijn 1', 'Lijn 2', 'Lijn 3'];
const OUTKOP = ['datum', 'ploeg', 'lijn', 'output', 'opmerking', 'door', 'tijd'];
const PMKOP = ['nr', 'datum', 'status', 'taken', 'opmerking', 'door', 'tijd'];
const PMSTATUS = ['Uitgevoerd', 'Deels uitgevoerd'];

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

function zetPm_(d) {
  const s = SpreadsheetApp.openById(SHEET_ID);
  const b = s.getSheetByName('PM') || s.insertSheet('PM', s.getNumSheets());
  b.getRange('A:G').setNumberFormat('@');
  b.getRange(1, 1, 1, PMKOP.length).setValues([PMKOP]);
  const n = b.getLastRow();
  const nrs = n > 1 ? b.getRange(2, 1, n - 1, 1).getValues().map(r => r[0]) : [];
  const i = nrs.indexOf(d.nr);
  const tijd = nu_();
  const rij = [d.nr, d.datum, d.status, d.taken, schoon_(d.opmerking), schoon_(d.door), tijd];
  if (i >= 0) b.getRange(i + 2, 1, 1, rij.length).setValues([rij]);
  else b.appendRow(rij);
  return tijd;
}

function doGet(e) {
  const p = e.parameter || {};
  const monteur = p.k === MONTEURSLEUTEL;
  if (p.k === OUTPUTSLEUTEL) return uit_({ output: outputRijen_() });
  if (p.k === PMSLEUTEL) return uit_({ pm: pmRijen_() });
  if (p.k !== SLEUTEL && !monteur) return uit_({ fout: 'geen toegang' });
  const rijen = blad_().getDataRange().getDisplayValues().slice(1).filter(r => r[10] !== 'Verwijderd');
  if (p.foto) {
    // Alleen foto's die bij een regel horen, nooit andere bestanden uit Drive.
    if (!rijen.some(r => r[14] === p.foto && (!monteur || r[2] === 'TD'))) return uit_({ fout: 'foto niet gevonden' });
    return uit_({ foto: Utilities.base64Encode(DriveApp.getFileById(p.foto).getBlob().getBytes()) });
  }
  if (monteur || p.rapport) {
    return uit_({ rapport: rijen.filter(r => r[2] === 'TD').slice(-500).map(object_) });
  }
  return uit_({ meldingen: rijen.filter(r => r[10] === 'Open').map(object_), bonstatus: bonstatus_(), output: outputRijen_(), pm: pmRijen_() });
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
  // De PM-inlog kan alleen PM-bonnen afmelden.
  const pm = d.k === PMSLEUTEL && d.actie === 'pm';
  if (wvActie ? d.k !== WVSLEUTEL : d.k !== SLEUTEL && !melder && !monteur && !ploeg && !pm) return uit_({ fout: 'geen toegang' });
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
      return uit_({ ok: true, tijd: zetPm_(d) });
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
