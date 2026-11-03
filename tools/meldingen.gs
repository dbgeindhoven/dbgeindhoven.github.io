// TD Hub meldingen: ontvangt meldingen van de site en bewaart ze in de Google Sheet.
// De echte waarden van SHEET_ID en SLEUTEL staan niet in deze repository.
const SHEET_ID = '__SHEET_ID__';
const SLEUTEL = '__SLEUTEL__';
const KOP = ['id', 'tijd', 'letter', 'melding', 'lijn', 'machine', 'melder', 'actiehouder', 'datum', 'bon_nodig', 'status', 'gereed_op', 'gereed_door', 'oplossing', 'foto'];
const ZONE = 'Europe/Amsterdam';
const MAP = "TD Hub foto's";
const MAX_FOTO = 8000000;

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

function doGet(e) {
  if (!e.parameter || e.parameter.k !== SLEUTEL) return uit_({ fout: 'geen toegang' });
  const rijen = blad_().getDataRange().getDisplayValues().slice(1);
  if (e.parameter.foto) {
    // Alleen foto's die bij een melding horen, nooit andere bestanden uit Drive.
    if (!rijen.some(r => r[14] === e.parameter.foto)) return uit_({ fout: 'foto niet gevonden' });
    return uit_({ foto: Utilities.base64Encode(DriveApp.getFileById(e.parameter.foto).getBlob().getBytes()) });
  }
  const open = rijen.filter(r => r[10] === 'Open').map(r => {
    const o = {};
    KOP.forEach((k, i) => { o[k] = r[i]; });
    return o;
  });
  return uit_({ meldingen: open });
}

function doPost(e) {
  const d = JSON.parse(e.postData.contents);
  if (d.k !== SLEUTEL) return uit_({ fout: 'geen toegang' });
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const b = blad_();
    b.getRange('B:B').setNumberFormat('@');
    if (d.actie === 'nieuw') {
      const id = Utilities.getUuid().slice(0, 8);
      const tijd = nu_();
      b.getRange(1, 1, 1, KOP.length).setValues([KOP]);
      let foto = '';
      if (d.foto) {
        if (d.foto.length > MAX_FOTO) return uit_({ fout: 'foto te groot' });
        foto = map_().createFile(Utilities.newBlob(Utilities.base64Decode(d.foto), 'image/jpeg', 'melding-' + id + '.jpg')).getId();
      }
      b.appendRow([id, tijd, schoon_(d.letter), schoon_(d.melding), schoon_(d.lijn), schoon_(d.machine), schoon_(d.melder), schoon_(d.actiehouder), schoon_(d.datum), d.bon_nodig ? 'Ja' : 'Nee', 'Open', '', '', schoon_(d.oplossing), foto]);
      return uit_({ ok: true, id: id, tijd: tijd, foto: foto });
    }
    if (d.actie === 'gereed') {
      const ids = b.getRange(1, 1, b.getLastRow(), 1).getDisplayValues();
      for (let i = 1; i < ids.length; i++) {
        if (ids[i][0] === d.id) {
          b.getRange(i + 1, 11, 1, 3).setValues([['Afgehandeld', nu_(), schoon_(d.door)]]);
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
