// TD Hub meldingen: ontvangt meldingen van de site en bewaart ze in de Google Sheet.
// De echte waarden van SHEET_ID en SLEUTEL staan niet in deze repository.
const SHEET_ID = '__SHEET_ID__';
const SLEUTEL = '__SLEUTEL__';
const MELDSLEUTEL = '__MELDSLEUTEL__';
const MONTEURSLEUTEL = '__MONTEURSLEUTEL__';
const WACHTRIJ = '__WACHTRIJ__';
const START_URL = '__START_URL__';
const START_TOKEN = '__START_TOKEN__';
const KOP = ['id', 'tijd', 'letter', 'melding', 'lijn', 'machine', 'melder', 'actiehouder', 'datum', 'bon_nodig', 'status', 'gereed_op', 'gereed_door', 'oplossing', 'foto', 'risico', 'vervolg', 'code', 'wachtrij'];
const ZONE = 'Europe/Amsterdam';
const MAP = "TD Hub foto's";
const MAX_FOTO = 8000000;
const START_RUST = 600000; // Hooguit één start van de bonnentaak per tien minuten.

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
  let nieuw = 0;
  b.getDataRange().getDisplayValues().forEach((r, i) => {
    if (i === 0 || r[18] || (r[2] !== 'TD' && r[9] !== 'Ja')) return;
    map.createFile('bon-' + r[0] + '.txt', JSON.stringify(object_(r)), MimeType.PLAIN_TEXT);
    b.getRange(i + 1, 19).setValue(nu_());
    nieuw++;
  });
  return nieuw;
}

// Start de bonnentaak meteen. Wat binnenkomt terwijl de taak loopt, pakt de taak zelf mee.
function startBonnen_() {
  const p = PropertiesService.getScriptProperties();
  const nu = Date.now();
  if (nu - Number(p.getProperty('gestart') || 0) < START_RUST) return;
  p.setProperty('gestart', String(nu));
  UrlFetchApp.fetch(START_URL, {
    method: 'post',
    contentType: 'application/json',
    payload: '{}',
    muteHttpExceptions: true,
    headers: { Authorization: 'Bearer ' + START_TOKEN, 'anthropic-beta': 'experimental-cc-routine-2026-04-01', 'anthropic-version': '2023-06-01' },
  });
}

// Lijn en machine die bij de opvolging zijn ingevuld, gaan mee zolang de bon nog niet is gemaakt.
function verversWachtrij_(b, rij, id) {
  const r = b.getRange(rij, 1, 1, KOP.length).getDisplayValues()[0];
  if (!r[18]) return;
  const f = DriveApp.getFolderById(WACHTRIJ).getFilesByName('bon-' + id + '.txt');
  while (f.hasNext()) {
    const x = f.next();
    if (!x.isTrashed()) x.setContent(JSON.stringify(object_(r)));
  }
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
    if (wachtrij_(b)) startBonnen_();
  } catch (f) {
    console.error(f);
  }
}

function doGet(e) {
  const p = e.parameter || {};
  const monteur = p.k === MONTEURSLEUTEL;
  if (p.k !== SLEUTEL && !monteur) return uit_({ fout: 'geen toegang' });
  const rijen = blad_().getDataRange().getDisplayValues().slice(1);
  if (p.foto) {
    // Alleen foto's die bij een regel horen, nooit andere bestanden uit Drive.
    if (!rijen.some(r => r[14] === p.foto && (!monteur || r[2] === 'TD'))) return uit_({ fout: 'foto niet gevonden' });
    return uit_({ foto: Utilities.base64Encode(DriveApp.getFileById(p.foto).getBlob().getBytes()) });
  }
  if (monteur || p.rapport) {
    return uit_({ rapport: rijen.filter(r => r[2] === 'TD').slice(-500).map(object_) });
  }
  return uit_({ meldingen: rijen.filter(r => r[10] === 'Open').map(object_) });
}

function doPost(e) {
  const d = JSON.parse(e.postData.contents);
  // De meldinlog mag alleen nieuwe meldingen versturen, nooit iets lezen of wijzigen.
  const melder = d.k === MELDSLEUTEL && d.actie === 'nieuw' && d.letter === '';
  const monteur = d.k === MONTEURSLEUTEL && d.actie === 'nieuw' && d.letter === 'TD';
  if (d.k !== SLEUTEL && !melder && !monteur) return uit_({ fout: 'geen toegang' });
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
      b.appendRow([id, tijd, schoon_(d.letter), schoon_(d.melding), schoon_(d.lijn), schoon_(d.machine), schoon_(d.melder), schoon_(d.actiehouder), schoon_(d.datum), d.bon_nodig ? 'Ja' : 'Nee', d.letter === 'TD' ? 'Rapport' : 'Open', '', '', schoon_(d.oplossing), foto, schoon_(d.risico), schoon_(d.vervolg), code, '']);
      naarWachtrij_(b);
      return uit_({ ok: true, id: id, tijd: tijd, foto: foto, code: code });
    }
    if (d.actie === 'gereed' || d.actie === 'verplaats' || d.actie === 'bijwerken') {
      const ids = b.getRange(1, 1, b.getLastRow(), 1).getDisplayValues();
      for (let i = 1; i < ids.length; i++) {
        if (ids[i][0] === d.id) {
          if (d.actie === 'gereed') b.getRange(i + 1, 11, 1, 3).setValues([['Afgehandeld', nu_(), schoon_(d.door)]]);
          else if (d.actie === 'verplaats') b.getRange(i + 1, 3).setValue(['S', 'Q', 'D'].includes(d.letter) ? d.letter : '');
          else {
            b.getRange(i + 1, 5, 1, 2).setValues([[schoon_(d.lijn), schoon_(d.machine)]]);
            b.getRange(i + 1, 8, 1, 3).setValues([[schoon_(d.actiehouder), schoon_(d.datum), d.bon_nodig ? 'Ja' : 'Nee']]);
            b.getRange(i + 1, 14).setValue(schoon_(d.oplossing));
            try {
              if (d.bon_nodig) verversWachtrij_(b, i + 1, d.id);
              else uitWachtrij_(b, i + 1, d.id);
            } catch (f) {
              console.error(f);
            }
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
