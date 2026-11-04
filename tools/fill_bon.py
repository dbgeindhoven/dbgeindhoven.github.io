#!/usr/bin/env python3
"""Vult het lege Word-template F.95.602 Werkbon TD met de gegevens uit een spec-bestand.

  fill_bon.py <spec.json> <template.docx> <uit.docx>

Alleen word/document.xml krijgt tekst erbij. De rest van het template blijft ongewijzigd,
op de foto na (word/media, en de verwijzing daarnaar). Het template zelf staat niet in deze
repository. De velden van de spec staan in tools/bonnen.md.
"""
import copy, io, json, re, sys, zipfile

from lxml import etree
from PIL import Image

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML = "{http://www.w3.org/XML/1998/namespace}space"
MAX_B, MAX_H = 2900000, 2300000  # fotovak in EMU
VELDEN = {
    "Uitvoeren op": "uitvoeren_op", "Lijn / machine": "lijn_machine", "Werkbon nr.": "werkbon_nr",
    "Melder": "melder", "Installatie": "installatie", "Afdeling": "afdeling",
    "Uitvoerder": "uitvoerder", "Leverancier": "leverancier", "Onderdelen": "onderdelen",
}
FOTO_XML = (
    '<w:r xmlns:w="' + W + '" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    '<w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>'
    '<wp:docPr id="901" name="Foto"/><a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
    '<pic:pic><pic:nvPicPr><pic:cNvPr id="901" name="foto_bon.jpg"/><pic:cNvPicPr/></pic:nvPicPr>'
    '<pic:blipFill><a:blip r:embed="rIdFoto1"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
    '<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
    '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic>'
    "</wp:inline></w:drawing></w:r>"
)


def q(t):
    return "{%s}%s" % (W, t)


def tekst(el):
    return "".join(el.itertext()).strip()


def run(t, sz=16, b=False, i=False, kleur=None):
    r = etree.Element(q("r"))
    rp = etree.SubElement(r, q("rPr"))
    if b:
        etree.SubElement(rp, q("b"))
    if i:
        etree.SubElement(rp, q("i"))
    if kleur:
        etree.SubElement(rp, q("color")).set(q("val"), kleur)
    etree.SubElement(rp, q("sz")).set(q("val"), str(sz))
    etree.SubElement(rp, q("szCs")).set(q("val"), str(sz))
    tt = etree.SubElement(r, q("t"))
    tt.text = t
    tt.set(XML, "preserve")
    return r


def volgende_cel(tc):
    n = tc.getnext()
    while n is not None and n.tag != q("tc"):
        n = n.getnext()
    return n


def alinea(root, begin):
    for p in root.iter(q("p")):
        if tekst(p).startswith(begin):
            return p
    raise SystemExit("Template wijkt af: geen regel die begint met '%s'." % begin)


def vul_velden(root, spec):
    cellen = list(root.iter(q("tc")))
    for label, veld in VELDEN.items():
        if not spec.get(veld):
            continue
        cel = next((volgende_cel(tc) for tc in cellen if tekst(tc) == label), None)
        if cel is None:
            raise SystemExit("Template wijkt af: geen veld '%s'." % label)
        cel.find(q("p")).append(run(spec[veld]))


def vul_stappen(root, stappen):
    """Zet de taakstappen op de lege regel onder de eerste vaste stap, met de opmaak van die regel."""
    eerste = alinea(root, "Stop de machine")
    leeg = eerste.getnext()
    if leeg is None or leeg.tag != q("p") or tekst(leeg):
        raise SystemExit("Template wijkt af: geen lege regel onder de eerste stap.")
    voorbeeld = eerste.find(q("r"))
    opmaak = leeg.find(q("pPr"))
    for t in reversed(stappen):
        p = etree.Element(q("p"))
        if opmaak is not None:
            p.append(copy.deepcopy(opmaak))
        r = copy.deepcopy(voorbeeld)
        r.find(q("t")).text = t
        p.append(r)
        leeg.addnext(p)
    leeg.getparent().remove(leeg)
    return eerste.getparent()


def vul_opmerkingen(root, regels):
    kop = next(tc for tc in root.iter(q("tc")) if "OPMERKINGEN" in tekst(tc))
    leeg, rij = [], kop.getparent().getnext()
    while rij is not None and len(leeg) < 4:
        if rij.tag == q("tr"):
            c = rij.find(q("tc"))
            if c is not None and not tekst(c):
                leeg.append(c)
        rij = rij.getnext()
    for c, t in zip(leeg, regels):
        c.find(q("p")).append(run(t, 16, i=True))


def zet_foto(cel, spec, delen):
    p = cel.find(q("p"))
    if not spec.get("foto"):
        if spec.get("foto_tekst"):
            p.append(run(spec["foto_tekst"], 16, i=True, kleur="808080"))
        return
    im = Image.open(spec["foto"]).convert("RGB")
    im.thumbnail((1000, 1000))
    uit = io.BytesIO()
    im.save(uit, "JPEG", quality=78)
    delen["word/media/foto_bon.jpg"] = uit.getvalue()
    w, h = im.size
    schaal = min(MAX_B / w, spec.get("foto_maxh", MAX_H) / h)
    p.append(etree.fromstring(FOTO_XML.format(cx=int(w * schaal), cy=int(h * schaal))))
    if spec.get("foto_bijschrift"):
        s = etree.Element(q("p"))
        s.append(run(spec["foto_bijschrift"], 14, i=True, kleur="808080"))
        p.addnext(s)
    rels = delen["word/_rels/document.xml.rels"].decode("utf-8")
    delen["word/_rels/document.xml.rels"] = rels.replace(
        "</Relationships>",
        '<Relationship Id="rIdFoto1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
        'Target="media/foto_bon.jpg"/></Relationships>',
    ).encode("utf-8")
    ct = delen["[Content_Types].xml"].decode("utf-8")
    if 'Extension="jpg"' not in ct:
        ct = ct.replace("<Default ", '<Default Extension="jpg" ContentType="image/jpeg"/><Default ', 1)
    delen["[Content_Types].xml"] = ct.encode("utf-8")


def maak(spec, template, uit):
    with zipfile.ZipFile(template) as z:
        namen = z.namelist()
        delen = {n: z.read(n) for n in namen}
    root = etree.fromstring(delen["word/document.xml"])
    vul_velden(root, spec)
    alinea(root, "Omschrijving:").append(run(" " + spec["omschrijving"], 18, b=True, kleur="FFFFFF"))
    cel = vul_stappen(root, spec["stappen"])
    if spec.get("let_op"):
        alinea(root, "⚠ Let op").append(run(" " + spec["let_op"]))
    vul_opmerkingen(root, spec.get("opmerking", []))
    zet_foto(volgende_cel(cel), spec, delen)
    delen["word/document.xml"] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    with zipfile.ZipFile(uit, "w", zipfile.ZIP_DEFLATED) as z:
        for n in namen + [n for n in delen if n not in namen]:
            z.writestr(n, delen[n])


def zet_veld(root, label, waarde):
    """Vervangt de tekst in het vak naast een label."""
    cel = next((volgende_cel(tc) for tc in root.iter(q("tc")) if tekst(tc) == label), None)
    if cel is None:
        raise SystemExit("Template wijkt af: geen veld '%s'." % label)
    p, *rest = cel.findall(q("p"))
    for x in rest:
        cel.remove(x)
    for r in p.findall(q("r")):
        p.remove(r)
    if waarde:
        p.append(run(waarde))


def zet_prio(root, prio):
    t = next(x for x in root.iter(q("t")) if (x.text or "").startswith("Prio:"))
    t.text = re.sub(r"[☐☒]\s*([123])", lambda m: ("☒ " if str(prio) == m.group(1) else "☐ ") + m.group(1), t.text)


def lees_zip(inhoud):
    with zipfile.ZipFile(io.BytesIO(inhoud)) as z:
        return {n: z.read(n) for n in z.namelist()}


def schrijf_zip(delen):
    uit = io.BytesIO()
    with zipfile.ZipFile(uit, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in delen.items():
            z.writestr(n, d)
    return uit.getvalue()


def zet_zaterdag(inhoud, prio, uitvoerder, uitvoeren):
    """Geeft een Word-bon terug met deze prio, uitvoerder en datum. De site doet hetzelfde in de browser."""
    delen = lees_zip(inhoud)
    root = etree.fromstring(delen["word/document.xml"])
    zet_veld(root, "Uitvoeren op", uitvoeren)
    zet_veld(root, "Uitvoerder", uitvoerder)
    zet_prio(root, prio)
    delen["word/document.xml"] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    return schrijf_zip(delen)


def zaterdaglijst(inhoud, datum, lijsten):
    """Vult het lege Word-format. Elke regel is (nr, werkzaamheid, lijn en machine, prio, uitvoerder, gereed). De site doet hetzelfde in de browser."""
    delen = lees_zip(inhoud)
    root = etree.fromstring(delen["word/document.xml"])
    for t in root.iter(q("t")):
        if t.text == "__DATUM__":
            t.text = datum
    tabellen = [t for t in root.iter(q("tbl")) if "Werkzaamheid" in tekst(t)]
    for tabel, regels in zip(tabellen, lijsten):
        leeg = tabel.findall(q("tr"))[2:-1]
        while len(leeg) < len(regels):
            kopie = copy.deepcopy(leeg[0])
            leeg[-1].addnext(kopie)
            leeg.append(kopie)
        for rij, regel in zip(leeg, regels):
            cellen = rij.findall(q("tc"))
            for cel, waarde in zip(cellen, regel[:5]):
                cel.find(".//" + q("t")).text = str(waarde or "")
            if regel[5]:
                cellen[5].find(".//" + q("t")).text = "☒"
    delen["word/document.xml"] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    return schrijf_zip(delen)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    maak(json.load(open(sys.argv[1], encoding="utf-8")), sys.argv[2], sys.argv[3])
