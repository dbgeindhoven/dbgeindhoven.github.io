"""De opnamelijst machine in Word, uit wat de monteur in de app invulde (opnamelijsten[].digitaal).

Zelfde opbouw als de opnamelijsten op papier: kop met logo en bonnummer, vakken A tot en met I met een zwarte kopbalk
als eerste rij van elke tabel (losse tabellen direct onder elkaar plakt Word samen), en achterin de fotobijlage.
De foto's zelf staan niet in deze repository: de geplande taak haalt ze uit Drive en geeft de map mee."""
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ZWART, GRIJS, LIJN = "15181D", RGBColor(0x64, 0x6B, 0x79), "CBD0D6"
AAN, UIT = "☒", "☐"
STAAT = {"G": "G", "M": "M", "S": "S"}
BRONNEN = ["Elektrisch", "Perslucht", "Hydrauliek", "Stoom", "Water", "Zwaartekracht", "Veerspanning"]
FOTOSOORT = ["Typeplaatje", "Overzicht machine", "Aandrijving", "Typeplaatjes componenten"]


def _schaduw(cel, kleur):
    p = cel._tc.get_or_add_tcPr()
    s = OxmlElement("w:shd")
    s.set(qn("w:val"), "clear")
    s.set(qn("w:color"), "auto")
    s.set(qn("w:fill"), kleur)
    p.append(s)


def _randen(tabel):
    t = tabel._tbl.tblPr
    b = OxmlElement("w:tblBorders")
    for k in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement("w:" + k)
        e.set(qn("w:val"), "single")
        e.set(qn("w:sz"), "4")
        e.set(qn("w:color"), LIJN)
        b.append(e)
    t.append(b)


def _tekst(cel, tekst, vet=False, grootte=8.5, kleur=None, midden=False, cursief=False):
    p = cel.paragraphs[0]
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(1)
    if midden:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    regels = str(tekst if tekst is not None else "").split("\n")
    for i, regel in enumerate(regels):
        r = p.add_run(regel)
        r.bold, r.italic = vet, cursief
        r.font.size = Pt(grootte)
        if kleur is not None:
            r.font.color.rgb = kleur
        if i < len(regels) - 1:
            r.add_break()
    return p


def _breedtes(tabel, cm):
    """Word kijkt naar de cellen, LibreOffice naar het raster van de tabel: zet ze allebei."""
    tabel.autofit = False
    grid = tabel._tbl.tblGrid
    for gc, w in zip(grid.findall(qn("w:gridCol")), cm):
        gc.set(qn("w:w"), str(int(w * 567)))
    pr = tabel._tbl.tblPr
    lay = OxmlElement("w:tblLayout")
    lay.set(qn("w:type"), "fixed")
    pr.append(lay)
    for rij in tabel.rows:
        for cel, w in zip(rij.cells, cm):
            cel.width = Cm(w)


def _vak(doc, titel, kop, rijen, cm, midden=(), noot=None):
    """Een vak: de zwarte kopbalk is de eerste rij van de tabel, daarna de kolomkoppen en de regels."""
    n = len(cm)
    t = doc.add_table(rows=0, cols=n)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    _randen(t)
    balk = t.add_row().cells
    c = balk[0].merge(balk[-1]) if n > 1 else balk[0]
    _schaduw(c, ZWART)
    _tekst(c, titel, vet=True, grootte=9.5, kleur=RGBColor(0xFF, 0xFF, 0xFF))
    if kop:
        r = t.add_row().cells
        for i, k in enumerate(kop):
            _schaduw(r[i], "EEF0F3")
            _tekst(r[i], k, vet=True, grootte=8, midden=i in midden)
    for regel in rijen:
        r = t.add_row().cells
        for i, w in enumerate(regel):
            if isinstance(w, tuple):
                _tekst(r[i], w[0], vet=True)
                if w[1]:
                    q = r[i].add_paragraph()
                    q.paragraph_format.space_after = Pt(1)
                    x = q.add_run(w[1])
                    x.italic, x.font.size, x.font.color.rgb = True, Pt(7.5), GRIJS
            else:
                _tekst(r[i], w, midden=i in midden)
    if noot:
        r = t.add_row().cells
        c = r[0].merge(r[-1]) if n > 1 else r[0]
        _tekst(c, noot, grootte=7.5, kleur=GRIJS, cursief=True)
    _breedtes(t, cm)
    tussen = doc.add_paragraph()
    tussen.paragraph_format.space_after = Pt(0)
    tussen.paragraph_format.space_before = Pt(0)
    tussen.paragraph_format.line_spacing = Pt(8)
    return t


def _velden(doc, titel, paren, breed=18.6):
    """Een vak met label en waarde, twee paren naast elkaar."""
    rijen = []
    for i in range(0, len(paren), 2):
        a = paren[i]
        b = paren[i + 1] if i + 1 < len(paren) else ("", "")
        rijen.append([a[0], a[1], b[0], b[1]])
    t = _vak(doc, titel, None, rijen, [3.4, 5.9, 3.4, 5.9])
    for rij in t.rows[1:]:
        for i in (0, 2):
            for r in rij.cells[i].paragraphs[0].runs:
                r.font.color.rgb = GRIJS
    return t


def _vink(lijst, gekozen):
    gekozen = set(gekozen or [])
    return "   ".join((AAN if x in gekozen else UIT) + " " + x for x in lijst + sorted(gekozen - set(lijst)))


def fotolijst(g):
    """Alle foto's met een bijschrift, in de volgorde van de lijst. Ook de geplande taak gebruikt dit om te weten welke foto's hij moet ophalen."""
    uit = []
    a = g.get("A") or {}
    uit += [(f, "Typeplaat machine") for f in a.get("fotos") or []]
    for x in g.get("B") or []:
        uit += [(f, "Component: " + (x.get("c") or "")) for f in x.get("fotos") or []]
    f_ = g.get("F") or {}
    uit += [(f, "LOTO-punt") for f in f_.get("fotos") or []]
    uit += [(f, "Overige foto") for f in (g.get("G") or {}).get("fotos") or []]
    return [(f, t) for f, t in uit if isinstance(f, str) and f and not f.startswith("tmp:")]


def maak(ol, g, logo, fotomap, pad):
    """ol: de regel uit opnamelijsten; g: de gegevens uit de app; logo: png-bytes of None; fotomap: map met <id>.jpg."""
    doc = Document()
    s = doc.sections[0]
    s.orientation = WD_ORIENT.PORTRAIT
    s.page_width, s.page_height = Cm(21), Cm(29.7)
    s.left_margin = s.right_margin = Cm(1.2)
    s.top_margin, s.bottom_margin = Cm(1.1), Cm(1.2)
    st = doc.styles["Normal"]
    st.font.name = "Arial"
    st.font.size = Pt(8.5)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "Arial")

    kop = doc.add_table(rows=1, cols=3)
    _randen(kop)
    c = kop.rows[0].cells
    if logo:
        tmp = Path(pad).with_suffix(".logo.png")
        tmp.write_bytes(logo)
        c[0].paragraphs[0].add_run().add_picture(str(tmp), width=Cm(3.6))
        tmp.unlink()
    else:
        _tekst(c[0], "dutchbakery", vet=True, grootte=12)
    _tekst(c[1], "OPNAMELIJST MACHINE", vet=True, grootte=13, midden=True)
    _tekst(c[2], "Bonnr.\n" + str(ol.get("ol") or ""), vet=True, grootte=11, midden=True)
    _breedtes(kop, [5.2, 8.6, 4.8])
    doc.add_paragraph().paragraph_format.space_after = Pt(0)

    dag = str(g.get("_tijd") or "")[:10]
    _velden(doc, "ALGEMEEN", [("Lijn", ol.get("lijn")), ("Machine", ol.get("machine")), ("PM-code", ol.get("pm_code")), ("Datum opname", dag), ("Opgenomen door", g.get("wie") or g.get("_door")), ("Ingevuld in", "TD Hub, monteursapp")])

    a = g.get("A") or {}
    _velden(doc, "A   MACHINEGEGEVENS (TYPEPLAAT)", [
        ("Fabrikant", a.get("fabrikant")), ("Type / model", a.get("type")), ("Serienummer", a.get("serie")), ("Bouwjaar", a.get("bouwjaar")),
        ("Leverancier", a.get("leverancier")), ("Ultimo-nummer", a.get("ultimo")), ("Spanning", a.get("spanning")), ("Vermogen", a.get("vermogen")),
        ("Aanwezig", ", ".join(a.get("aanwezig") or []) or "—"), ("Foto typeplaat", "Ja, zie bijlage" if a.get("fotos") else "Nee")])

    b = [x for x in g.get("B") or [] if x.get("c")]
    _vak(doc, "B   COMPONENTEN", ["#", "Component", "Aantal", "Merk / type", "Maat / artikelnr.", "Staat"],
         [[str(i + 1), (x.get("c"), x.get("opm") or ""), x.get("aantal") or "", x.get("type") or "", x.get("maat") or "", STAAT.get(x.get("staat"), "–")] for i, x in enumerate(b)] or [["", "Geen componenten ingevuld", "", "", "", ""]],
         [0.7, 5.0, 1.3, 4.0, 5.6, 2.0], midden=(0, 2, 5), noot="Staat: G = goed, M = matig (volgen), S = slecht (vervangen / correctieve bon). – = niet beoordeeld.")

    cc = [x for x in g.get("C") or [] if x.get("p")]
    _vak(doc, "C   SMEERPUNTEN", ["#", "Smeerpunt", "Aantal", "Smeermiddel", "Hoeveelheid", "Methode", "Interval"],
         [[str(i + 1), x.get("p"), x.get("aantal") or "", x.get("middel") or "", x.get("hoeveel") or "", x.get("methode") or "", x.get("interval") or ""] for i, x in enumerate(cc)] or [["", "Geen smeerpunten gevonden" if g.get("Cgeen") else "Niet ingevuld", "", "", "", "", ""]],
         [0.7, 5.2, 1.4, 3.4, 2.4, 2.8, 2.7], midden=(0, 2))

    d = [x for x in g.get("D") or [] if x.get("s") or x.get("opm")]
    rijen = [[str(i + 1), x.get("taak") + (" (" + x["id"] + ")" if x.get("id") else ""), AAN if x.get("s") == "OK" else UIT, AAN if x.get("s") == "NOK" else UIT, x.get("opm") or ""] for i, x in enumerate(d)]
    rijen.append([str(len(d) + 1), "Overige bijzonderheden", "", "", g.get("Dopm") or "Geen"])
    nb = len([x for x in g.get("D") or [] if not x.get("s")])
    _vak(doc, "D   INSPECTIE – BESTAANDE PM-TAKEN", ["#", "Controlepunt", "OK", "NOK", "Opmerking / actie"], rijen,
         [0.7, 8.8, 1.2, 1.2, 6.7], midden=(0, 2, 3), noot=("%d PM-punten niet beoordeeld en hier weggelaten." % nb) if nb else None)

    e = [x for x in g.get("E") or [] if x.get("o")]
    vr = lambda v: (AAN if v == "J" else UIT) + " J  " + (AAN if v == "N" else UIT) + " N"
    _vak(doc, "E   KRITISCHE RESERVEONDERDELEN", ["#", "Onderdeel", "Artikelnr. / type", "Leverancier", "Op voorraad", "Min."],
         [[str(i + 1), x.get("o"), x.get("art") or "", x.get("lev") or "", vr(x.get("voorraad")), x.get("min") or ""] for i, x in enumerate(e)] or [["", "Geen ingevuld", "", "", "", ""]],
         [0.7, 5.0, 4.4, 3.4, 2.6, 2.5], midden=(0, 4, 5))

    f = g.get("F") or {}
    _vak(doc, "F   VEILIGHEID", None, [["Energiebronnen", _vink(BRONNEN, f.get("bronnen"))], ["LOTO-punt", (f.get("loto") or "Niet ingevuld") + ("  (foto in bijlage)" if f.get("fotos") else "")], ["Risico's", f.get("risico") or "Niet ingevuld"]], [3.6, 15.0])

    fotos = fotolijst(g)
    gg = g.get("G") or {}
    _vak(doc, "G   FOTO'S", None, [["Gemaakt", _vink(FOTOSOORT, gg.get("gemaakt"))], ["Opgeslagen", "TD Hub (Drive), %d foto's, zie fotobijlage" % len(fotos) if fotos else "Geen foto's"]], [3.6, 15.0])

    h = g.get("H") or {}
    jn = lambda v: (AAN if v == "Ja" else UIT) + " JA   " + (AAN if v == "Nee" else UIT) + " NEE"
    _vak(doc, "H   AFRONDING", None, [["Opname compleet", jn(h.get("compleet"))], ["Correctieve bon nodig", jn(h.get("correctief")) + ("   " + h["wat"] if h.get("wat") else "")]], [4.4, 14.2])

    _vak(doc, "I   NOTITIES", None, [[g.get("I") or "Geen"]], [18.6])

    if fotos:
        p = doc.add_paragraph()
        p.add_run().add_break(WD_BREAK.PAGE)
        r = p.add_run("FOTOBIJLAGE – " + str(ol.get("ol") or "") + " " + str(ol.get("machine") or ""))
        r.bold, r.font.size = True, Pt(12)
        t = doc.add_table(rows=0, cols=2)
        _randen(t)
        rij = None
        for i, (fid, bij) in enumerate(fotos):
            if i % 2 == 0:
                rij = t.add_row().cells
            cel = rij[i % 2]
            bestand = Path(fotomap) / (fid + ".jpg")
            if bestand.exists():
                cel.paragraphs[0].add_run().add_picture(str(bestand), width=Cm(8.6))
                cel.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
                q = cel.add_paragraph()
            else:
                q = cel.paragraphs[0]
            x = q.add_run("%d. %s" % (i + 1, bij) + ("" if bestand.exists() else " (foto niet opgehaald)"))
            x.font.size, x.italic = Pt(8), True
        _breedtes(t, [9.3, 9.3])
    doc.save(pad)
    return pad
