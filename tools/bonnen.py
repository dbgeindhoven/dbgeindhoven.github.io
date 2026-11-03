#!/usr/bin/env python3
"""Verwerkt de wachtrij met meldingen tot bonnen. De werkwijze staat in tools/bonnen.md.

  bonnen.py template   <site.json> <template.docx>   Versleutelt het Word-template naar bonnen/.
  bonnen.py nummer     <site.json> <werkmap> [--laatste-cm N]
  bonnen.py maak       <site.json> <werkmap>
  bonnen.py registreer <site.json> <werkmap>
  bonnen.py beelden    <site.json>                  Maakt de afbeelding voor bonnen die er nog geen hebben.

In de werkmap staat werk.json: een lijst met de inhoud van de wachtrijbestanden, elk aangevuld
met drive_id. Per bon staat daar <nr>.json met de tekst van de bon; maak zet er <nr>.docx en
<nr>.pdf en <nr>-bon.jpg (de afbeelding waarmee de bon op de site opent) naast. De leesbare bonnen en het template komen nooit in deze repository, alleen
versleuteld in bonnen/.
"""
import argparse, base64, json, re, secrets, subprocess, sys, tempfile
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fill_bon

REPO = Path(__file__).resolve().parent.parent
MAP = REPO / "bonnen"
TEMPLATE = "template.bin"
LEEG = {"melder": None, "uitvoeren": None, "onderdelen": None, "opmerking": None, "uitgevoerd_op": None, "monteur": None, "afgetekend": None, "prio": None}


def laad(p):
    return json.loads(Path(p).read_text("utf-8"))


def bewaar(p, d):
    Path(p).write_text(json.dumps(d, ensure_ascii=False, indent=1), "utf-8")


def stand(data):
    b = data["meta"].setdefault("bonnen", {})
    if not b.get("sleutel"):
        b["sleutel"] = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
    b.setdefault("verwerkt", {})
    b.setdefault("laatste_cm", 0)
    return b


def versleutel(inhoud, sleutel, naam=None):
    """Schrijft iv + versleutelde inhoud naar bonnen/ en geeft het pad voor de site terug."""
    MAP.mkdir(exist_ok=True)
    naam = naam or secrets.token_hex(8) + ".bin"
    iv = secrets.token_bytes(12)
    (MAP / naam).write_bytes(iv + AESGCM(base64.b64decode(sleutel)).encrypt(iv, inhoud, None))
    return "bonnen/" + naam


def afbeelding(pdf):
    """Pagina 1 van de bon als afbeelding, die de site zelf toont. Geeft het pad naar de jpg terug."""
    pdf = Path(pdf)
    doel = pdf.with_name(pdf.stem + "-bon")
    subprocess.run(["pdftoppm", "-r", "150", "-jpeg", "-jpegopt", "quality=80", "-singlefile", "-f", "1", "-l", "1", str(pdf), str(doel)], check=True, capture_output=True)
    return doel.with_suffix(".jpg")


def ontsleutel(naam, sleutel):
    r = (MAP / naam).read_bytes()
    return AESGCM(base64.b64decode(sleutel)).decrypt(r[:12], r[12:], None)


def template(a):
    data = laad(a.site)
    versleutel(Path(a.docx).read_bytes(), stand(data)["sleutel"], TEMPLATE)
    bewaar(a.site, data)


def nummer(a):
    """Productiemeldingen houden hun SQDM-code. Monteurstoringen krijgen het volgende CM-nummer."""
    data = laad(a.site)
    b = stand(data)
    bestand = Path(a.map) / "werk.json"
    werk = laad(bestand)
    bekend = [int(m.group(1)) for r in data.get("cm", []) for m in [re.fullmatch(r"CM(\d+)", str(r.get("nr")))] if m]
    hoogste = max(bekend + [b["laatste_cm"], a.laatste_cm])
    for w in werk:
        w.pop("overslaan", None)
        if w["id"] in b["verwerkt"]:
            w["nr"], w["overslaan"] = b["verwerkt"][w["id"]], True
        elif w.get("code"):
            w["nr"] = w["code"]
        else:
            hoogste += 1
            w["nr"] = "CM%d" % hoogste
        print(w["id"], w["nr"], "al gemaakt, alleen uit de wachtrij halen" if w.get("overslaan") else w.get("vervolg") or "productiemelding")
    bewaar(bestand, werk)


def maak(a):
    """Maakt van elke tekst in de werkmap een Word- en PDF-bon en meldt het aantal pagina's."""
    wm = Path(a.map)
    if not (MAP / TEMPLATE).exists():
        raise SystemExit("Er staat nog geen template in bonnen/.")
    sjabloon = wm / "template.docx"
    sjabloon.write_bytes(ontsleutel(TEMPLATE, stand(laad(a.site))["sleutel"]))
    for w in laad(wm / "werk.json"):
        if w.get("overslaan"):
            continue
        docx = wm / (w["nr"] + ".docx")
        fill_bon.maak(laad(wm / (w["nr"] + ".json")), sjabloon, docx)
        subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(wm), str(docx)], check=True, capture_output=True, timeout=180)
        info = subprocess.run(["pdfinfo", str(docx.with_suffix(".pdf"))], check=True, capture_output=True, text=True).stdout
        paginas = int(re.search(r"Pages:\s+(\d+)", info).group(1))
        afbeelding(docx.with_suffix(".pdf"))
        print(w["nr"], "1 pagina" if paginas == 1 else "%d pagina's: maak de tekst korter" % paginas)


def rij_voor(w, spec, datum):
    monteur = w.get("letter") == "TD"
    gereed = monteur and w.get("vervolg") == "Gereed"
    regels = ["Automatisch gemaakt uit de melding van " + str(w.get("tijd")) + "."]
    if w.get("risico"):
        regels.append("Risico: " + w["risico"] + ".")
    if w.get("oplossing"):
        regels.append(("Oplossing: " if gereed else "Al gedaan: ") + w["oplossing"].rstrip(". ") + ".")
    if not gereed:
        regels.append("Concept: nog controleren.")
    return dict(
        LEEG, nr=w["nr"], lijn=w.get("lijn") or None, machine=w.get("machine") or None,
        omschrijving=spec["kort"], melder=w.get("melder") or None, uitvoeren=spec.get("uitvoeren_op"),
        onderdelen=spec.get("onderdelen"), status="Uitgevoerd" if gereed else "Open", opmerking=" ".join(regels),
        uitgevoerd_op=datum if gereed else None, monteur=w.get("melder") if monteur else None,
        actiehouder=w.get("actiehouder") or None, bron="CM-overzicht, uit melding van " + datum,
        herkomst="Monteur" if monteur else "Productie", risico=w.get("risico") or None, melding=w["id"],
    )


def registreer(a):
    """Zet de bonnen in het CM-overzicht, de onderdelen op de bestellijst en de bestanden versleuteld in bonnen/."""
    data = laad(a.site)
    b = stand(data)
    wm = Path(a.map)
    for w in laad(wm / "werk.json"):
        if w.get("overslaan"):
            continue
        spec = laad(wm / (w["nr"] + ".json"))
        datum = str(w.get("tijd"))[:10]
        rij = rij_voor(w, spec, datum)
        rij["bon"] = {
            "naam": spec["naam"],
            "docx": versleutel((wm / (w["nr"] + ".docx")).read_bytes(), b["sleutel"]),
            "pdf": versleutel((wm / (w["nr"] + ".pdf")).read_bytes(), b["sleutel"]),
            "beeld": versleutel((wm / (w["nr"] + "-bon.jpg")).read_bytes(), b["sleutel"]),
        }
        data["cm"].append(rij)
        if w.get("vervolg") == "Onderdeel bestellen":
            data["bestellijst"].append({
                "cm": w["nr"], "onderdeel": spec.get("onderdelen") or "Zie bon", "specificatie": None, "aantal": None,
                "leverancier": None, "status": "Nee", "link": None, "groep": "Nog niet besteld", "toelichting": None,
                "opmerking": "Uit storing van " + datum + ", monteur " + str(w.get("melder")) + ". Foto op de bon.",
            })
        b["verwerkt"][w["id"]] = w["nr"]
        m = re.fullmatch(r"CM(\d+)", w["nr"])
        if m:
            b["laatste_cm"] = max(b["laatste_cm"], int(m.group(1)))
    bewaar(a.site, data)


def beelden(a):
    data = laad(a.site)
    sleutel = stand(data)["sleutel"]
    with tempfile.TemporaryDirectory() as t:
        for r in data.get("cm", []):
            if r.get("bon") and not r["bon"].get("beeld"):
                pdf = Path(t) / (r["nr"] + ".pdf")
                pdf.write_bytes(ontsleutel(Path(r["bon"]["pdf"]).name, sleutel))
                r["bon"]["beeld"] = versleutel(afbeelding(pdf).read_bytes(), sleutel)
                print(r["nr"], r["bon"]["beeld"])
    bewaar(a.site, data)


ap = argparse.ArgumentParser()
sub = ap.add_subparsers(dest="cmd", required=True)
x = sub.add_parser("template"); x.add_argument("site"); x.add_argument("docx"); x.set_defaults(fn=template)
x = sub.add_parser("nummer"); x.add_argument("site"); x.add_argument("map"); x.add_argument("--laatste-cm", type=int, default=0); x.set_defaults(fn=nummer)
x = sub.add_parser("maak"); x.add_argument("site"); x.add_argument("map"); x.set_defaults(fn=maak)
x = sub.add_parser("registreer"); x.add_argument("site"); x.add_argument("map"); x.set_defaults(fn=registreer)
x = sub.add_parser("beelden"); x.add_argument("site"); x.set_defaults(fn=beelden)
a = ap.parse_args()
a.fn(a)
