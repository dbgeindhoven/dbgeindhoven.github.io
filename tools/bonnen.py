#!/usr/bin/env python3
"""Verwerkt de wachtrij met meldingen tot bonnen. De werkwijze staat in tools/bonnen.md.

  bonnen.py template   <site.json> <template.docx>   Versleutelt het Word-template naar bonnen/.
  bonnen.py nummer     <site.json> <werkmap> [--laatste-cm N]
  bonnen.py maak       <site.json> <werkmap>
  bonnen.py registreer <site.json> <werkmap>
  bonnen.py beelden    <site.json>                  Maakt de afbeelding voor bonnen die er nog geen hebben.
  bonnen.py wijzig     <site.json> <werkmap>        Verwerkt statuswijzigingen en verwijderde bonnen uit wijzig.json.
  bonnen.py lijst      <site.json> <leeg.docx>      Versleutelt het lege Word-format van de zaterdaglijst naar bonnen/.
  bonnen.py zaterdag   <site.json> <werkmap>        Werkt de bonnen van de zaterdaglijst en de onderhoudsstops bij en maakt per plan de PDF om te printen.
  bonnen.py pmdag      <site.json> <werkmap> --datum DD-MM-JJJJ   Maakt de PM-bonnen van die dag en zet ze samen in 1 PDF.
  bonnen.py zatbon     <site.json> <werkmap> <nr>   Maakt de Word- en PDF-bon voor een bestaande bon zonder bestanden, uit <nr>.json.
  bonnen.py zoekwerk   <site.json> [--aantal 8]     Geeft de bestelregels die opgezocht moeten worden en de leveranciers uit het leveranciersbestand.
  bonnen.py zoek       <site.json> <zoek.json>      Zet de zoekresultaten op de bestellijst.

In de werkmap staat werk.json: een lijst met de inhoud van de wachtrijbestanden, elk aangevuld
met drive_id. Per bon staat daar <nr>.json met de tekst van de bon; maak zet er <nr>.docx en
<nr>.pdf en <nr>-bon.jpg (de afbeelding waarmee de bon op de site opent) naast. De leesbare bonnen en het template komen nooit in deze repository, alleen
versleuteld in bonnen/.
"""
import argparse, base64, datetime, json, re, secrets, subprocess, sys, tempfile, textwrap
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fill_bon
import pm

REPO = Path(__file__).resolve().parent.parent
MAP = REPO / "bonnen"
TEMPLATE = "template.bin"
LIJST = "zaterdaglijst.bin"
WEEKDAGEN = ("Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag", "Zaterdag", "Zondag")
KLAAR = ("Uitgevoerd", "Gereed")
# De statussen van een bon. Besteld en Leverdatum hebben een eigen datum (besteld_op, leverdatum), Gepland de dag van zijn plan.
BONSTATUS = ("Open", "Te plannen", "Uitzoeken voor bestelling", "Besteld", "Leverdatum", "Gepland", "Uitgevoerd", "Vervallen")
# Oudere statussen uit een oude pagina of een oud wachtrijbestand. Deels uitgevoerd is ook wat de monteur kiest bij het afmelden.
OUDSTATUS = {"Bestellen": "Uitzoeken voor bestelling", "In bestelling": "Besteld", "Deels uitgevoerd": "Te plannen", "On hold": "Open", "Gereed": "Uitgevoerd", "Dubbel": "Vervallen"}
BESTELFASE = ("Uitzoeken voor bestelling", "Besteld", "Leverdatum")
# Bij deze statussen hoort een bon niet op de agenda. Uitgevoerd blijft op zijn dag staan. De site gebruikt dezelfde lijst (VAN_AGENDA).
VAN_AGENDA = ("Open", "Te plannen", "Uitzoeken voor bestelling", "Besteld", "Leverdatum", "Vervallen")
LEEG ={"melder": None, "uitvoeren": None, "onderdelen": None, "opmerking": None, "uitgevoerd_op": None, "monteur": None, "afgetekend": None, "prio": None}


def status_norm(s):
    return OUDSTATUS.get(s, s) or "Open"


def plan_datum(p):
    d, m, j = map(int, str(p["datum"]).split("-"))
    return datetime.date(j, m, d)


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
        aantal = paginas(docx.with_suffix(".pdf"))
        afbeelding(docx.with_suffix(".pdf"))
        print(w["nr"], "1 pagina" if aantal == 1 else "%d pagina's: maak de tekst korter" % aantal)


def rij_voor(w, spec, datum):
    monteur = w.get("letter") == "TD"
    werkvoorbereider = w.get("letter") == "CM"
    gereed = monteur and w.get("vervolg") == "Gereed"
    regels = [("Gemaakt op de site op " if werkvoorbereider else "Automatisch gemaakt uit de melding van ") + str(w.get("tijd")) + "."]
    if w.get("risico"):
        regels.append("Risico: " + w["risico"] + ".")
    if w.get("oplossing"):
        regels.append(("Oplossing: " if gereed else "Al gedaan: " if monteur else "" if werkvoorbereider else "Actie: ") + w["oplossing"].replace("[x] ", "Gedaan: ").rstrip(". ") + ".")
    if not gereed:
        regels.append("Concept: nog controleren.")
    return dict(
        LEEG, nr=w["nr"], lijn=w.get("lijn") or None, machine=w.get("machine") or None,
        omschrijving=spec["kort"], melder=w.get("melder") or None, uitvoeren=spec.get("uitvoeren_op"),
        onderdelen=spec.get("onderdelen"), status="Uitgevoerd" if gereed else "Open", opmerking=" ".join(regels),
        prio=int(w["prio"]) if str(w.get("prio") or "") in ("1", "2", "3") else None,
        uitgevoerd_op=datum if gereed else None, monteur=w.get("melder") if monteur else None,
        actiehouder=w.get("actiehouder") or None, bron="CM-overzicht, uit melding van " + datum,
        herkomst="Monteur" if monteur else "Werkvoorbereider" if werkvoorbereider else "Productie", risico=w.get("risico") or None, melding=w["id"],
    )


def bestelregel(nr, onderdeel, opmerking):
    return {
        "cm": nr, "onderdeel": onderdeel or "Zie bon", "specificatie": None, "aantal": None,
        "leverancier": None, "status": "Nee", "link": None, "groep": "Nog niet besteld", "toelichting": None, "opmerking": opmerking,
    }


def registreer(a):
    """Zet de bonnen in het CM-overzicht, de onderdelen op de bestellijst en de bestanden versleuteld in bonnen/."""
    data = laad(a.site)
    b = stand(data)
    wm = Path(a.map)
    # Een bon kan al op een stop staan die in dezelfde run wordt aangemaakt.
    for w in laad(wm / "wijzig.json") if (wm / "wijzig.json").exists() else []:
        if (w.get("rij") or {}).get("stop"):
            stop_nieuw(data, w["rij"]["stop"])
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
        v = str(w.get("vervolg") or "")
        z = plan_van(data, v[5:]) if v.startswith("Stop:") else data.get("zaterdag") if v == "Zaterdag" else None
        if z and w.get("datum") == z.get("datum"):
            z.setdefault("preventief" if str(spec.get("omschrijving")).lower().startswith("preventief") else "correctief", []).append(
                {"nr": w["nr"], "werkzaamheid": spec["kort"], "lijn_machine": spec.get("lijn_machine"), "prio": rij["prio"], "uitvoerder": None, "gereed": None})
            rij["status"], rij["uitvoeren"] = "Gepland", plan_dag(z)
        if w.get("vervolg") == "Onderdeel bestellen":
            data["bestellijst"].append(bestelregel(w["nr"], spec.get("onderdelen"), "Uit storing van " + datum + ", monteur " + str(w.get("melder")) + "." + (" Foto op de bon." if w.get("foto") else "")))
        b["verwerkt"][w["id"]] = w["nr"]
        m = re.fullmatch(r"CM(\d+)", w["nr"])
        if m:
            b["laatste_cm"] = max(b["laatste_cm"], int(m.group(1)))
    bewaar(a.site, data)


def plannen(data):
    """De zaterdaglijst en de onderhoudsstops. Een bon staat op één plan."""
    z = data.get("zaterdag")
    return ([z] if z else []) + list(data.get("stops") or [])


def plan_van(data, k):
    """Zonder id is het de zaterdaglijst, zo blijven oudere wachtrijbestanden geldig."""
    return next((s for s in data.get("stops") or [] if s.get("id") == k), None) if k else data.get("zaterdag")


def plan_dag(p):
    if not p.get("id"):
        return "Zaterdag " + str(p.get("datum"))
    d, m, j = map(int, str(p["datum"]).split("-"))
    return "%s %s" % (WEEKDAGEN[datetime.date(j, m, d).weekday()], p["datum"])


def plan_naam(p):
    return plan_dag(p) + (", " + str(p.get("lijn")) if p.get("id") and p.get("lijn") else "")


def plan_tekst(p):
    """Een dag buiten de zaterdag gebruikt het Word-format van de zaterdaglijst, met andere koppen. De site doet hetzelfde in STOPTEKST."""
    if not p.get("id") or plan_dag(p).startswith("Zaterdag"):
        return None
    return {
        "WERKBON TD – ZATERDAGWERK": "WERKBON TD – ONDERHOUD",
        "Overzicht zaterdagwerkzaamheden": "Overzicht onderhoudsplanning",
        "Zaterdag ": plan_dag(p).split()[0] + " ",
        "Overzicht zaterdagwerk – F.95.602 Werkbon TD – pagina ": "Overzicht onderhoudsplanning – F.95.602 Werkbon TD – pagina ",
    }


def zat_rijen(z):
    return (z.get("correctief") or []) + (z.get("preventief") or [])


def zat_weg(data, nr, alleen=None):
    for z in [alleen] if alleen else plannen(data):
        for k in ("correctief", "preventief"):
            z[k] = [r for r in z.get(k) or [] if r.get("nr") != nr]


def zat_wijzig(data, nr, rij, zat):
    """Prio, uitvoerder, verplaatsen of weghalen vanaf Zaterdagwerk of Onderhoudsstop. De prio hoort bij de bon, de uitvoerder bij dit plan."""
    z = plan_van(data, zat.get("plan"))
    if not z or zat.get("datum") != z.get("datum"):
        print(nr, "wijziging hoort bij een ander plan, overgeslagen")
        return
    nieuw = zat.get("nieuw")
    if nieuw and nr not in [r.get("nr") for r in zat_rijen(z)]:
        zat_weg(data, nr)
        z.setdefault("preventief" if nieuw.get("lijst") == "preventief" else "correctief", []).append(
            {"nr": nr, "werkzaamheid": nieuw.get("werkzaamheid"), "lijn_machine": nieuw.get("lijn_machine"), "prio": zat.get("prio"), "uitvoerder": None, "gereed": None})
    if zat.get("weg"):
        zat_weg(data, nr, z)
        if rij is not None:
            rij["uitvoeren"] = None
        print(nr, "van", plan_naam(z), "gehaald")
        return
    for r in zat_rijen(z):
        if r.get("nr") == nr:
            r["prio"], r["uitvoerder"], r["uren"] = zat.get("prio"), zat.get("uitvoerder") or None, zat.get("uren")
    if rij is not None:
        rij["prio"] = zat.get("prio")
        if nieuw:
            rij["uitvoeren"] = plan_dag(z)
    print(nr, plan_naam(z), "prio", zat.get("prio"), "uitvoerder", zat.get("uitvoerder"), "uren", zat.get("uren"))


def zat_kop(data, kop):
    """Teamleider, monteurs, LET OP en beschikbare manuren van een plan."""
    z = plan_van(data, kop.get("plan"))
    if z and kop.get("datum") == z.get("datum"):
        z.update({k: kop.get(k) for k in ("teamleider", "monteurs", "letop", "capaciteit")})
        print(plan_naam(z), "kop bijgewerkt")


def stop_nieuw(data, s):
    if not plan_van(data, s.get("id")):
        data.setdefault("stops", []).append({**s, "teamleider": None, "monteurs": None, "letop": None, "capaciteit": None, "correctief": [], "preventief": []})
        print("Stop aangemaakt:", plan_naam(s))


def stops_samen(data):
    """De agenda toont één plan per dag. Staan er twee op dezelfde dag, dan komen de bonnen op het eerste en vervalt het tweede."""
    per_dag = {}
    for s in list(data.get("stops") or []):
        eerste = per_dag.setdefault(s.get("datum"), s)
        if eerste is s:
            continue
        for k in ("correctief", "preventief"):
            eerste[k] = (eerste.get(k) or []) + (s.get(k) or [])
        for k in ("lijn", "naam", "teamleider", "monteurs", "letop", "capaciteit"):
            eerste[k] = eerste.get(k) or s.get(k)
        data["stops"].remove(s)
        print("Plannen op", s.get("datum"), "samengevoegd")


def stop_weg(data, k):
    """De bonnen blijven bestaan. Wat nog niet klaar is staat daarna nergens meer op: Gepland wordt Te plannen."""
    s = plan_van(data, k)
    if not k or not s:
        return
    cm = {r.get("nr"): r for r in data.get("cm", [])}
    for r in zat_rijen(s):
        c = cm.get(r.get("nr"))
        if c and c.get("status") not in KLAAR:
            c["uitvoeren"] = None
            if c.get("status") == "Gepland":
                c["status"] = "Te plannen"
    data["stops"].remove(s)
    print("Stop verwijderd:", plan_naam(s))


BESTELSTATUS = {"Nog niet besteld": "Nee", "Eerst opmeten of checken": "Eerst opmeten", "Opgevraagd": "Opgevraagd", "Besteld": "Besteld", "Binnen": "Binnen"}


def bestel_wijzig(data, b):
    r = next((x for x in data["bestellijst"] if x.get("id") == b.get("id")), None)
    if r is None or b.get("groep") not in BESTELSTATUS:
        print(b.get("id"), "staat niet op de bestellijst")
    else:
        r["groep"], r["status"] = b["groep"], BESTELSTATUS[b["groep"]]
        print(r.get("cm"), r.get("onderdeel"), "staat op", b["groep"])
        if b.get("zoek"):
            r.pop("zoek", None)
            r["zoekeerst"] = True


def bon_uitvoeren(data, rij, wm):
    """Zet de nieuwe tekst bij Uitvoeren op ook op de Word- en PDF-bon."""
    bon = rij.get("bon") or {}
    print(rij["nr"], "uitvoeren op", rij["uitvoeren"])
    if not bon.get("docx"):
        return
    b = stand(data)
    wm.mkdir(parents=True, exist_ok=True)
    docx = wm / (bon["naam"] + ".docx")
    docx.write_bytes(fill_bon.zet_uitvoeren(ontsleutel(Path(bon["docx"]).name, b["sleutel"]), rij["uitvoeren"], rij.get("prio") or ""))
    naar_pdf([docx], wm)
    pdf = docx.with_suffix(".pdf")
    for k in ("docx", "pdf", "beeld"):
        if bon.get(k):
            (REPO / bon[k]).unlink(missing_ok=True)
    bon.pop("stempel", None)
    bon.update(docx=versleutel(docx.read_bytes(), b["sleutel"]), pdf=versleutel(pdf.read_bytes(), b["sleutel"]), beeld=versleutel(afbeelding(pdf).read_bytes(), b["sleutel"]))


def bon_registratie(data, rij, regel, wm):
    """Zet een registratie, zoals een afgemelde opdracht, bij Opmerkingen op de Word- en PDF-bon. Prio, uitvoerder en dag blijven, dus de stempel ook."""
    bon = rij.get("bon") or {}
    if not bon.get("docx"):
        return
    b = stand(data)
    wm.mkdir(parents=True, exist_ok=True)
    docx = wm / (bon["naam"] + ".docx")
    docx.write_bytes(fill_bon.zet_registratie(ontsleutel(Path(bon["docx"]).name, b["sleutel"]), regel))
    naar_pdf([docx], wm)
    pdf = docx.with_suffix(".pdf")
    for k in ("docx", "pdf", "beeld"):
        if bon.get(k):
            (REPO / bon[k]).unlink(missing_ok=True)
    bon.update(docx=versleutel(docx.read_bytes(), b["sleutel"]), pdf=versleutel(pdf.read_bytes(), b["sleutel"]), beeld=versleutel(afbeelding(pdf).read_bytes(), b["sleutel"]))


def opdracht_af(data, o, w, wm):
    """De monteur meldde de opdracht van de werkvoorbereider af. De bon blijft open: de opdracht gaat eraf en wat de monteur schreef
    komt als registratie op de bon (opmerking, Word en PDF) en in cm[].opdrachtaf, voor Te doen en het detailpaneel."""
    nr = o.get("nr")
    rij = next((r for r in data["cm"] if r.get("nr") == nr), None)
    if rij is None:
        print(nr, "staat niet in het overzicht, opdracht overgeslagen")
        return
    af = {"opdracht": str(o.get("opdracht") or "").strip(), "tekst": str(o.get("tekst") or "").strip(), "door": o.get("door") or "Monteur", "tijd": str(o.get("tijd") or w.get("tijd"))[:16]}
    lijst = rij.setdefault("opdrachtaf", [])
    if af in lijst:
        print(nr, "opdracht al verwerkt")
        return
    lijst.append(af)
    if rij.get("opdracht") == af["opdracht"] or not af["opdracht"]:
        rij.pop("opdracht", None)
    zin = lambda t: t + ("" if t[-1:] in ".!?" else ".")
    regel = "%s, %s: opdracht %s" % (af["tijd"][:10], af["door"], ("“%s” gedaan. " % af["opdracht"].rstrip(".")) if af["opdracht"] else "gedaan. ") + zin(af["tekst"])
    rij["opmerking"] = " ".join(filter(None, (rij.get("opmerking"), regel)))
    print(nr, regel)
    try:
        bon_registratie(data, rij, regel, wm)
    except Exception as e:  # De registratie staat dan wel in de opmerking; de bon volgt bij een volgende wijziging.
        print(nr, "registratie niet op de bon gezet:", e)


UITVOEREN_VERVOLG = {"Overdragen aan volgende dienst": "Volgende dienst", "Plannen voor onderhoudstop": "Eerstvolgende onderhoudstop", "Onderdeel bestellen": "In overleg"}
UITVOEREN_LOS = (None, "", *UITVOEREN_VERVOLG.values())


def vervolg_wijzig(data, v, w, opnieuw):
    """Een volgende dienst past in het dienstrapport het vervolg van een storing aan of meldt hem af. De bon gaat mee."""
    nr = stand(data)["verwerkt"].get(v.get("id"))
    rij = next((r for r in data["cm"] if r.get("nr") == nr), None)
    if rij is None:
        print(v.get("id"), "heeft geen bon, vervolg overgeslagen")
        return
    keuze, tekst, door, dag = v.get("vervolg"), v.get("tekst"), v.get("door"), str(w.get("tijd"))[:10]
    regel = "%s, %s: %s." % (dag, door or "Monteur", keuze) + (" " + tekst.rstrip() + ("" if tekst.rstrip()[-1:] in ".!?" else ".") if tekst else "")
    rij["opmerking"] = " ".join(filter(None, (rij.get("opmerking"), regel)))
    print(nr, keuze, door)
    if rij.get("status") in KLAAR:
        return
    if keuze == "Gereed":
        rij["status"], rij["uitgevoerd_op"] = "Uitgevoerd", dag
    if keuze == "Onderdeel bestellen" and not any(r.get("cm") == nr for r in data["bestellijst"]):
        data["bestellijst"].append(bestelregel(nr, tekst or rij.get("onderdelen"), "Uit dienstrapport van " + dag + ", monteur " + str(door) + "."))
    # Een bon op een dag in de planning houdt die dag, en wat de werkvoorbereider zelf invulde blijft staan tot de bon klaar is.
    nieuw = "Uitgevoerd op " + dag if keuze == "Gereed" else UITVOEREN_VERVOLG.get(keuze) if rij.get("uitvoeren") in UITVOEREN_LOS else None
    if nieuw and nieuw != rij.get("uitvoeren") and not any(r.get("nr") == nr for z in plannen(data) for r in zat_rijen(z)):
        rij["uitvoeren"] = nieuw
        if rij not in opnieuw:
            opnieuw.append(rij)


def opname_wijzig(data, o, w, opnieuw):
    """Een monteur heeft een opnamebon afgemeld. De specificaties komen op de bestellijst en de regels gaan vooraan bij het zoeken.
    Is de opname klaar, dan gaat de bon op Uitzoeken voor bestelling en van de monteurs en de agenda af. Deels uitgevoerd laat de bon bij de monteurs staan.
    In het bestand betekent status Bestellen: opname klaar. Dat blijft zo, zodat oude telefoons met een afmelding in de wachtrij blijven werken."""
    nr, klaar, dag = o.get("nr"), w["status"] == "Bestellen", str(w.get("tijd"))[:10]
    rij = next((r for r in data["cm"] if r.get("nr") == nr), None)
    if rij is None:
        print(nr, "staat niet in het overzicht, opname overgeslagen")
        return
    regels = []
    for x in o.get("regels") or []:
        spec = str(x.get("spec") or "").strip()
        r = next((b for b in data["bestellijst"] if x.get("id") and b.get("id") == x["id"]), None)
        if r is None:
            if not (spec or x.get("onderdeel")):
                continue
            r = bestelregel(nr, x.get("onderdeel") or rij.get("onderdelen"), "Uit de opname van " + dag + ", monteur " + str(o.get("door")) + ".")
            # Meteen een nummer, anders neemt dezelfde run de regel niet mee bij het zoeken.
            r["id"] = "B%d" % (max([int(b["id"][1:]) for b in data["bestellijst"] if re.fullmatch(r"B\d+", str(b.get("id") or ""))] + [0]) + 1)
            data["bestellijst"].append(r)
        if spec:
            r["specificatie"] = spec
            if x.get("aantal"):
                r["aantal"] = x["aantal"]
            r["toelichting"] = None
            r.pop("zoek", None)
            r["zoekeerst"] = True
            if r.get("groep") == "Eerst opmeten of checken":
                r["groep"], r["status"] = "Nog niet besteld", BESTELSTATUS["Nog niet besteld"]
            regels.append({"onderdeel": r.get("onderdeel"), "spec": spec, "aantal": x.get("aantal") or None})
    oud = rij.get("opname") or {}
    fotos = (oud.get("fotos") or []) + ([o["foto"]] if o.get("foto") else [])
    tekst = (o.get("tekst") or "").rstrip()
    rij["opname"] = {"door": o.get("door"), "tijd": w.get("tijd"), "tekst": tekst, "fotos": fotos, "regels": regels or oud.get("regels") or [], "klaar": klaar}
    delen = ["%s: %s%s" % (x["onderdeel"], x["spec"], ", %s stuks" % x["aantal"] if x["aantal"] else "") for x in regels]
    regel = "%s, %s: Opname %s." % (dag, o.get("door") or "Monteur", "gedaan" if klaar else "deels gedaan") + "".join(" " + x.rstrip(". ") + "." for x in delen + [tekst] if x)
    rij["opmerking"] = " ".join(filter(None, (rij.get("opmerking"), regel)))
    print(nr, "opname", "klaar" if klaar else "deels", "; ".join(delen))
    if rij.get("status") in KLAAR or rij.get("status") in ("Dubbel", "Vervallen"):
        return
    rij["status"] = status_norm(rij.get("status"))
    if not klaar:
        # Nog bezig met uitzoeken: de bon blijft bij de monteurs.
        if rij["status"] in ("Open", "Te plannen"):
            rij["status"] = "Uitzoeken voor bestelling"
        return
    rij["week"] = False
    rij.pop("weeksoort", None)
    if rij["status"] not in ("Besteld", "Leverdatum"):
        rij["status"] = "Uitzoeken voor bestelling"
    # Net als op de site: een bon die op onderdelen wacht staat niet op de agenda.
    if any(r.get("nr") == nr for z in plannen(data) for r in zat_rijen(z)):
        zat_weg(data, nr)
        rij["uitvoeren"] = "Na levering"
        opnieuw.append(rij)
    if not any(r.get("cm") == nr for r in data["bestellijst"]):
        data["bestellijst"].append(bestelregel(nr, rij.get("onderdelen"), "Uit de opname van " + dag + "."))


def volgorde(w):
    """Een nieuwe stop eerst, bonnen kunnen er al naartoe verplaatst zijn. Het vervolg uit het dienstrapport en de opnames als laatste, op tijd: het nummer eindigt op het moment van de wijziging."""
    extra = w.get("rij") or {}
    laatst = bool(extra.get("vervolg") or extra.get("opname") or extra.get("opdrachtaf"))
    return (not extra.get("stop"), laatst, w["nr"] if laatst else "")


ZOEKSOORT = ("Exact", "Vergelijkbaar", "Geen")
ZOEKVELDEN = ("id", "cm", "onderdeel", "specificatie", "aantal", "leverancier", "link")
GOED = {"email": r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", "tel": r"\+?[0-9][0-9 ()/-]{5,20}", "site": r"https://\S+", "link": r"https://\S+"}


def zoekwerk(a):
    """Geeft de bestelregels die nog opgezocht moeten worden, de belangrijkste eerst, en de leveranciers die al bekend zijn."""
    data = laad(a.site)
    cm = {r.get("nr"): r for r in data.get("cm", [])}
    dicht = ("Uitgevoerd", "Gereed", "Dubbel", "Vervallen")
    rijen = [r for r in data.get("bestellijst", []) if r.get("id") and not r.get("zoek") and r.get("groep") not in ("Binnen", "Besteld") and (cm.get(r.get("cm")) or {}).get("status") not in dicht]
    rijen.sort(key=lambda r: (not r.get("zoekeerst"), (cm.get(r.get("cm")) or {}).get("prio") or 9, int(r["id"][1:])))
    # Het leveranciersbestand zonder inkoopbedragen: wie past bij het onderdeel, de leveranciers van Eindhoven eerst.
    bestand = sorted((data["meta"].get("levbestand") or {}).get("lijst") or [], key=lambda x: "Eindhoven" not in (x.get("locaties") or []))
    print(json.dumps({"rest": max(0, len(rijen) - a.aantal), "regels": [{k: r.get(k) for k in ZOEKVELDEN} for r in rijen[:a.aantal]], "leveranciers": [x["naam"] for x in data.get("leveranciers") or []], "bestand": [x["naam"] + (" | " + x["categorie"] if x.get("categorie") else "") + (" | Eindhoven" if "Eindhoven" in (x.get("locaties") or []) else "") for x in bestand] if rijen else []}, ensure_ascii=False, indent=1))


def zoek_goed(k, w):
    """Alleen wat eruitziet als een adres, nummer of beveiligde link komt op de site."""
    w = str(w or "").strip()
    return w if re.fullmatch(GOED[k], w) else ""


def zoek(a):
    """Zet de zoekresultaten op de bestellijst. Contactgegevens staan per leverancier één keer in leveranciers; wat er al staat blijft staan."""
    data = laad(a.site)
    werk = laad(a.bestand)
    dag = datetime.date.today().strftime("%d-%m-%Y")
    lev = data.setdefault("leveranciers", [])
    for z in werk.get("leveranciers") or []:
        naam = str(z.get("naam") or "").strip()[:60]
        if not naam:
            continue
        x = next((l for l in lev if l["naam"].lower() == naam.lower()), None)
        if x is None:
            x = {"naam": naam}
            lev.append(x)
        for k in ("email", "tel", "site"):
            if not x.get(k) and zoek_goed(k, z.get(k)):
                x[k] = zoek_goed(k, z.get(k))
    regels = {r.get("id"): r for r in data.get("bestellijst", [])}
    for z in werk.get("regels") or []:
        r = regels.get(z.get("id"))
        if r is None or z.get("soort") not in ZOEKSOORT:
            print(z.get("id"), "overgeslagen")
            continue
        link = zoek_goed("link", z.get("link"))
        r["zoek"] = {"datum": dag, "soort": z["soort"] if link or z["soort"] == "Geen" else "Geen", "bij": str(z.get("bij") or "").strip()[:60], "link": link, "tekst": str(z.get("tekst") or "").strip()[:200]}
        r.pop("zoekeerst", None)
        print(z["id"], r.get("onderdeel"), z["soort"], r["zoek"]["bij"])
    bewaar(a.site, data)


def gezien_opruimen(data, dagen=120):
    """Gezien van Te doen bewaren tot de regel allang niet meer kan terugkomen."""
    gezien = data["meta"].get("gezien") or {}
    grens = datetime.date.today() - datetime.timedelta(days=dagen)
    for k, v in list(gezien.items()):
        try:
            if datetime.datetime.strptime(v, "%d-%m-%Y").date() < grens:
                del gezien[k]
        except ValueError:
            pass


RCA_TEKST = 5000


def rca_schoon(x, diepte=0):
    """Alleen tekst, getallen, ja en nee, lijsten en objecten, met ingekorte teksten. Zo komt er uit de wachtrij niets vreemds in site.json."""
    if diepte > 6:
        return None
    if x is None or isinstance(x, (bool, int, float)):
        return x
    if isinstance(x, str):
        return x[:RCA_TEKST]
    if isinstance(x, list):
        return [rca_schoon(v, diepte + 1) for v in x[:60]]
    if isinstance(x, dict):
        return {str(k)[:40]: rca_schoon(v, diepte + 1) for k, v in list(x.items())[:80]}
    return None


def rca_wijzig(data, r):
    """RCA analyse: de site stuurt steeds de hele RCA (status-RCA-n.txt met rij.rca). Een nieuwere versie vervangt de oude, weg haalt hem weg."""
    if not isinstance(r, dict) or not re.fullmatch(r"RCA-\d{1,5}", str(r.get("id") or "")):
        print("rca overgeslagen: geen geldig nummer")
        return
    lijst = data.setdefault("rca", [])
    # Het hoogste nummer blijft bewaard, ook als de RCA wordt verwijderd: een nummer komt nooit twee keer uit.
    data["meta"]["rca_laatste"] = max(int(data["meta"].get("rca_laatste") or 0), int(r["id"].split("-")[1]))
    oud = next((x for x in lijst if x.get("id") == r["id"]), None)
    if r.get("weg"):
        if oud is not None:
            lijst.remove(oud)
        print(r["id"], "verwijderd")
        return
    nieuw = rca_schoon(r)
    if oud is None:
        lijst.append(nieuw)
    else:
        lijst[lijst.index(oud)] = nieuw
    lijst.sort(key=lambda x: int(x["id"].split("-")[1]))
    print(r["id"], "opgeslagen:", nieuw.get("titel") or "")


def wijzig(a):
    """Zet een status uit de site op de bon, of haalt de bon weg. Het nummer wordt daarna niet opnieuw uitgegeven."""
    data = laad(a.site)
    opnieuw = []
    for w in sorted(laad(Path(a.map) / "wijzig.json"), key=volgorde):
        nr, status = w["nr"], w["status"]
        extra = w.get("rij") or {}
        if extra.get("zoekmeer"):
            continue
        if "menu" in extra:
            # Menu indelen: de indeling van de werkvoorbereider, of terug naar het standaardmenu.
            m = extra.get("menu")
            if isinstance(m, dict) and isinstance(m.get("kopjes"), list):
                data["meta"]["menu"] = {
                    "kopjes": [{"t": str(k.get("t") or "Kopje")[:40], "p": [x for x in k.get("p") or [] if isinstance(x, str)][:40], "dicht": bool(k.get("dicht"))} for k in m["kopjes"][:12] if isinstance(k, dict)],
                    "weg": [x for x in m.get("weg") or [] if isinstance(x, str)][:40],
                }
            else:
                data["meta"].pop("menu", None)
            print("menu", "aangepast" if data["meta"].get("menu") else "standaard")
            continue
        if "rca" in extra:
            rca_wijzig(data, extra["rca"])
            continue
        if extra.get("gezien"):
            # Te doen: de werkvoorbereider zette een regel op Gezien, of terug.
            gezien = data["meta"].setdefault("gezien", {})
            if extra.get("terug"):
                gezien.pop(extra["gezien"], None)
            else:
                gezien[extra["gezien"]] = str(w.get("tijd"))[:10]
            continue
        if extra.get("vervolg"):
            vervolg_wijzig(data, extra["vervolg"], w, opnieuw)
            continue
        if extra.get("pmreg"):
            # Een registratie is bewijs voor de audit: alleen de PM-inlog maakt die. Oude bestanden zonder van komen van voor dit veld.
            if w.get("van") not in (None, "", "pm"):
                print(nr, "registratie geweigerd: niet van de PM-inlog maar van", w.get("van"))
                continue
            pm_registratie(data, extra["pmreg"], Path(a.map) / "pmreg")
            continue
        if extra.get("stop"):
            stop_nieuw(data, extra["stop"])
            continue
        if extra.get("stopweg"):
            stop_weg(data, extra["stopweg"])
            continue
        if extra.get("bestel"):
            bestel_wijzig(data, extra["bestel"])
            continue
        if extra.get("zatkop"):
            zat_kop(data, extra["zatkop"])
            continue
        if extra.get("week"):
            rij = next((r for r in data["cm"] if r.get("nr") == extra["week"].get("nr")), None)
            if rij is not None:
                rij["week"] = bool(extra["week"].get("aan"))
                if rij["week"] and extra["week"].get("soort") == "opname":
                    rij["weeksoort"] = "opname"
                else:
                    rij.pop("weeksoort", None)
                if "opdracht" in extra["week"]:
                    t = str(extra["week"].get("opdracht") or "").strip()[:1000]
                    if t:
                        rij["opdracht"] = t
                    else:
                        rij.pop("opdracht", None)
                print(rij["nr"], rij.get("weeksoort") or "uitvoerbaar" if rij["week"] else "niet meer uitvoerbaar")
            continue
        if extra.get("opname"):
            opname_wijzig(data, extra["opname"], w, opnieuw)
            continue
        if extra.get("opdrachtaf"):
            opdracht_af(data, extra["opdrachtaf"], w, Path(a.map) / "registratie")
            continue
        rij = next((r for r in data["cm"] if r.get("nr") == nr), None)
        # Deels uitgevoerd is wat de monteur koos. De bon is dan niet klaar en moet opnieuw worden gepland.
        deels = status == "Deels uitgevoerd"
        if status != "Verwijderd":
            status = status_norm(status)
        if status == "Verwijderd":
            zat_weg(data, nr)
        elif (w.get("rij") or {}).get("zat"):
            zat_wijzig(data, nr, rij, w["rij"]["zat"])
        if rij is None:
            print(nr, "staat niet in het overzicht")
        elif status == "Verwijderd":
            for pad in (rij.get("bon") or {}).values():
                if str(pad).startswith("bonnen/"):
                    (REPO / pad).unlink(missing_ok=True)
            data["cm"].remove(rij)
            data["bestellijst"] = [r for r in data["bestellijst"] if r.get("cm") != nr]
            print(nr, "verwijderd")
        else:
            klaar = ("Uitgevoerd", "Gereed")
            zat = extra.get("zat") or {}
            plan = next((z for z in plannen(data) if any(r.get("nr") == nr for r in zat_rijen(z))), None)
            if deels and rij.get("status") not in klaar:
                # Een plan op een latere dag blijft staan: daar gebeurt de rest. Een plan van vandaag of eerder vervalt.
                dag = datetime.datetime.strptime(str(w.get("tijd"))[:10], "%d-%m-%Y").date() if re.match(r"\d{2}-\d{2}-\d{4}", str(w.get("tijd"))) else datetime.date.today()
                if plan and plan_datum(plan) > dag:
                    status = "Gepland"
                elif plan:
                    zat_weg(data, nr)
                    plan = None
                    rij["uitvoeren"] = "In overleg"
                    opnieuw.append(rij)
            elif plan and status in VAN_AGENDA and not (zat and not zat.get("weg")):
                # Een status zonder dag haalt de bon van de agenda. De site stuurt dat zelf mee; dit vangt oude pagina's op.
                zat_weg(data, nr)
                plan = None
                rij["uitvoeren"] = "Na levering" if status in BESTELFASE else "In overleg"
                opnieuw.append(rij)
            if status in klaar and not rij.get("uitgevoerd_op"):
                rij["uitgevoerd_op"] = str(w.get("tijd"))[:10]
            elif rij.get("status") in klaar and status not in klaar:
                rij["uitgevoerd_op"] = None
            rij["status"] = status
            for k in ("besteld_op", "leverdatum"):
                # Besteld (datum) en Leverdatum (datum). Het veld blijft bij een volgende status staan, als geschiedenis.
                if k in extra and (extra[k] is None or re.fullmatch(r"\d{2}-\d{2}-\d{4}", str(extra[k]))):
                    rij[k] = extra[k] or None
            print(nr, status, *(rij.get(k) for k in ("besteld_op", "leverdatum") if status in BESTELFASE and rij.get(k)))
            if "uitvoeren" in extra:
                rij["uitvoeren"] = extra["uitvoeren"] or None
                opnieuw.append(rij)
            if "prioset" in extra and (not zat or zat.get("weg")):
                # Prio van een bon die niet op een plan staat, bijvoorbeeld uit het prio-voorstel op Te doen. Op een plan gaat de prio via rij.zat.
                # Een eigen veld: rij.prio hoort bij de regel voor Lopende storingen en kan van een oudere pagina komen.
                # Apps Script vult een oud bestand aan, dus naast prioset kan een eerdere zat staan; alleen weghalen van een plan gaat samen met prioset.
                p = str(extra.get("prioset") or "")
                nieuw_prio = int(p) if p in ("1", "2", "3") else None
                if nieuw_prio != rij.get("prio"):
                    rij["prio"] = nieuw_prio
                    print(nr, "prio", nieuw_prio)
                    opnieuw.append(rij)
            if extra.get("weekaf"):
                af = extra["weekaf"]
                # Wat de monteur koos en wanneer staat in de afmelding zelf: Apps Script vult een oud bestand aan met een latere wijziging van de werkvoorbereider.
                # Oudere afmeldingen hebben nog geen eigen tijd of status, dan geldt die van het bestand.
                af_tijd = str(af.get("tijd") or w.get("tijd"))[:16]
                dag = af_tijd[:10]
                af_status = af.get("status") or status
                tekst = (af.get("tekst") or "").rstrip()
                weekaf = {"door": af.get("door") or "Monteur", "tijd": af_tijd, "status": af_status, "tekst": tekst}
                if rij.get("weekaf") == weekaf:
                    # Dezelfde afmelding kwam al eerder langs, bijvoorbeeld in een aangevuld bestand dat binnenkwam terwijl de taak liep.
                    print(nr, "afmelding al verwerkt")
                else:
                    regel = "%s, %s: %s." % (dag, weekaf["door"], af_status) + (" " + tekst + ("" if tekst[-1:] in ".!?" else ".") if tekst else "")
                    rij["opmerking"] = " ".join(filter(None, (rij.get("opmerking"), regel)))
                    # Te doen toont de laatste afmelding: Deels uitgevoerd, of afgemeld met een opmerking.
                    rij["weekaf"] = weekaf
                    if status == "Uitgevoerd" and not any(r.get("nr") == nr for z in plannen(data) for r in zat_rijen(z)):
                        rij["uitvoeren"] = "Uitgevoerd op " + dag
                        opnieuw.append(rij)
            if "afgemeld" in extra:
                rij["uitgevoerd_op"] = extra["afgemeld"] or None
                if extra["afgemeld"] and str(rij.get("uitvoeren")).startswith("Uitgevoerd op"):
                    rij["uitvoeren"] = "Uitgevoerd op " + extra["afgemeld"]
                    opnieuw.append(rij)
            if status == "Uitzoeken voor bestelling" and not any(r.get("cm") == nr for r in data["bestellijst"]):
                data["bestellijst"].append(bestelregel(nr, rij.get("onderdelen"), "Uit de onderhoudsplanning van " + str(w.get("tijd"))[:10] + "."))
    for rij in {r["nr"]: r for r in opnieuw}.values():
        bon_uitvoeren(data, rij, Path(a.map) / "uitvoeren")
    gezien_opruimen(data)
    stops_samen(data)
    # Een dag zonder bonnen en zonder lijn of naam is leeggehaald: die hoeft niet in de agenda te blijven.
    data["stops"] = [s for s in data.get("stops") or [] if zat_rijen(s) or s.get("lijn") or s.get("naam")]
    bewaar(a.site, data)


def zat_regel(r, c):
    """Wat er op de lijst en de bon staat. De site rekent hetzelfde uit in zatRegel."""
    c = c or {}
    return (r.get("prio") or c.get("prio") or "", r.get("uitvoerder") or "", "1" if c.get("status") in KLAAR else "")


def zat_stempel(data, z):
    cm = {x.get("nr"): x for x in data.get("cm", [])}
    return ";".join("|".join([r["nr"], *map(str, zat_regel(r, cm.get(r["nr"])))]) for r in zat_rijen(z)) + "#" + "|".join(z.get(k) or "" for k in ("teamleider", "monteurs", "letop"))


def lijst(a):
    data = laad(a.site)
    stand(data)["lijst"] = versleutel(Path(a.docx).read_bytes(), stand(data)["sleutel"], LIJST)
    bewaar(a.site, data)


def naar_pdf(bestanden, map_):
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(map_)] + [str(x) for x in bestanden], check=True, capture_output=True, timeout=280)


def paginas(pdf):
    return int(re.search(r"Pages:\s+(\d+)", subprocess.run(["pdfinfo", str(pdf)], check=True, capture_output=True, text=True).stdout).group(1))


LIJST_REGEL = 21.25  # hoogte van een lege regel op de lijst, in punten
LIJST_EINDE = 68  # van de tekst Extra werkzaamheden tot de onderrand van de pagina: de regel zelf en de marge


def lijst_ruimte(pdf):
    """Hoeveel lege regels er per tabel nog bij passen, gemeten vanaf de laatste regel van die tabel."""
    tekst = subprocess.run(["pdftotext", "-bbox", str(pdf), "-"], check=True, capture_output=True, text=True).stdout
    hoogte = float(re.search(r'<page [^>]*height="([\d.]+)"', tekst).group(1))
    return [max(0, int((hoogte - LIJST_EINDE - float(y)) // LIJST_REGEL)) for y in re.findall(r'yMin="([\d.]+)"[^>]*>aanvullingen:<', tekst)]


def lijst_opmaken(maak, docx, wm):
    """Lange regels zijn hoger dan het format rekent, waardoor de laatste regel op een eigen pagina viel.
    Daarom eerst opmaken zonder lege regels, meten wat er over is en de pagina daarmee vullen."""
    pdf = docx.with_suffix(".pdf")

    def opmaak(vrij):
        docx.write_bytes(maak(vrij))
        naar_pdf([docx], wm)
        return paginas(pdf)

    minimaal = opmaak((0, 0))
    vrij = lijst_ruimte(pdf)
    while opmaak(vrij) > minimaal:
        vrij = [max(0, x - 1) for x in vrij]
    return pdf


def plan_print_weg(oud):
    for k in ("pdf", "lijstpdf"):
        if oud.get(k):
            (REPO / oud[k]).unlink(missing_ok=True)


def plan_print(data, z, wm, oud):
    """Zet prio, uitvoerder en datum op de bonnen van een plan en maakt de lijst en de PDF om te printen. Wat niet veranderde blijft staan."""
    b = stand(data)
    wm.mkdir(parents=True, exist_ok=True)
    cm = {r.get("nr"): r for r in data.get("cm", [])}
    dag = plan_dag(z)
    nieuw, zonder = [], []
    for r in zat_rijen(z):
        c = cm.get(r["nr"])
        bon = (c or {}).get("bon")
        if not (bon and bon.get("docx")):
            zonder.append(r["nr"])
            continue
        prio, uitvoerder, _ = zat_regel(r, c)
        merk = "|".join((str(prio), uitvoerder, dag))
        if bon.get("stempel") != merk:
            docx = wm / (bon["naam"] + ".docx")
            docx.write_bytes(fill_bon.zet_zaterdag(ontsleutel(Path(bon["docx"]).name, b["sleutel"]), prio, uitvoerder, dag))
            nieuw.append((bon, docx, merk))
    if nieuw:
        naar_pdf([x[1] for x in nieuw], wm)
    for bon, docx, merk in nieuw:
        pdf = docx.with_suffix(".pdf")
        for k in ("docx", "pdf", "beeld"):
            if bon.get(k):
                (REPO / bon[k]).unlink(missing_ok=True)
        bon.update(docx=versleutel(docx.read_bytes(), b["sleutel"]), pdf=versleutel(pdf.read_bytes(), b["sleutel"]), beeld=versleutel(afbeelding(pdf).read_bytes(), b["sleutel"]), stempel=merk)
    if zonder:
        print("Geen bonbestand:", ", ".join(zonder))
    stempel = zat_stempel(data, z)
    if not nieuw and oud.get("lijstpdf") and oud.get("datum") == z.get("datum") and oud.get("stempel") == stempel:
        print(plan_naam(z) + ": printversie is actueel.")
        return oud
    regel = lambda r: (r["nr"], r.get("werkzaamheid"), r.get("lijn_machine"), *zat_regel(r, cm.get(r["nr"])))
    docx = wm / "zaterdaglijst.docx"
    datum = str(z.get("datum")) + (" – " + str(z.get("lijn")) if z.get("lijn") else "")
    leeg = ontsleutel(LIJST, b["sleutel"])
    lijsten = [[regel(r) for r in z.get(k) or []] for k in ("correctief", "preventief")]
    lijstpdf = lijst_opmaken(lambda vrij: fill_bon.zaterdaglijst(leeg, datum, lijsten, z, plan_tekst(z), vrij), docx, wm)
    stukken = [lijstpdf]
    for i, r in enumerate(zat_rijen(z)):
        bon = (cm.get(r["nr"]) or {}).get("bon")
        if bon and bon.get("pdf"):
            p = wm / ("stuk-%03d.pdf" % i)
            p.write_bytes(ontsleutel(Path(bon["pdf"]).name, b["sleutel"]))
            stukken.append(p)
    alles = wm / "zaterdagwerk.pdf"
    subprocess.run(["pdfunite", *map(str, stukken), str(alles)], check=True, capture_output=True)
    plan_print_weg(oud)
    print(plan_naam(z) + ": printversie gemaakt,", len(stukken) - 1, "bonnen,", len(nieuw), "bijgewerkt")
    return {"datum": z.get("datum"), "pdf": versleutel(alles.read_bytes(), b["sleutel"]), "lijstpdf": versleutel(lijstpdf.read_bytes(), b["sleutel"]), "stempel": stempel}


def zaterdag(a):
    """Doet dit voor de zaterdaglijst en elke onderhoudsstop. De PDF's van een weggehaalde stop verdwijnen."""
    data = laad(a.site)
    b = stand(data)
    wm = Path(a.map)
    if data.get("zaterdag"):
        b["zaterdag"] = plan_print(data, data["zaterdag"], wm / "zaterdag", b.get("zaterdag") or {})
    klaar = b.setdefault("stops", {})
    for s in data.get("stops") or []:
        klaar[s["id"]] = plan_print(data, s, wm / s["id"], klaar.get(s["id"]) or {})
    for k in [k for k in klaar if not plan_van(data, k)]:
        plan_print_weg(klaar.pop(k))
    # Een opnamebon toont de monteur de originele bon, dus die moet er zijn.
    zonder = [r["nr"] for r in data.get("cm", []) if r.get("week") and r.get("weeksoort") == "opname" and not (r.get("bon") or {}).get("pdf")]
    if zonder:
        print("Geen bonbestand:", ", ".join(zonder))
    bewaar(a.site, data)


def pm_spec(b, rijen):
    """De tekst van een PM-bon. Alles komt uit de PM-lijst, er wordt niets bij verzonnen."""
    taken = [rijen[t] for t in b["taken"]]
    freq = " en ".join(f.lower() for f in pm.FREQ if any(r["frequentie"] == f for r in taken))
    nodig = []
    for r in taken:
        if r.get("benodigdheden") and r["benodigdheden"] not in nodig:
            nodig.append(r["benodigdheden"])
    delen = []
    for r in taken:
        if r.get("onderdeel") and r["onderdeel"] not in delen:
            delen.append(r["onderdeel"])
    naam = re.sub(r"[^A-Za-z0-9]+", "_", b["lijn"] + " " + b["lijndeel"]).strip("_")
    return {
        "naam": b["nr"] + "_" + naam, "werkbon_nr": b["nr"], "in_bedrijf": True,
        "omschrijving": "Preventief %s – %s" % (freq, b["lijndeel"] if b["lijn"].lower() in b["lijndeel"].lower() else b["lijndeel"] + " " + b["lijn"].lower()),
        "uitvoeren_op": WEEKDAGEN[pm.dat(b["datum"]).weekday()] + " " + b["datum"],
        "lijn_machine": b["lijn"] + " / " + b["lijndeel"], "melder": "PM-planning", "installatie": delen[0] if len(delen) == 1 else b["lijndeel"],
        "afdeling": "TD", "onderdelen": ", ".join(nodig)[:120] or None,
        "stappen": [pm.stap(r) for r in taken],
        "opmerking": ["Taken in bedrijf uit de PM-planning. Aftekenen in de TD Hub, tabblad PM-bonnen."],
        "foto_tekst": "Geen foto – foto bij bevindingen toevoegen",
    }


def pmdag(a):
    """Maakt de PM-bonnen van een dag en zet ze samen in 1 PDF. Oude sets gaan na een week weg, wat is afgetekend staat in de Sheet."""
    data = laad(a.site)
    b = stand(data)
    pm.bijwerken(data, a.datum)
    wm = Path(a.map)
    wm.mkdir(parents=True, exist_ok=True)
    sets = b.setdefault("pm", {})
    for dag in [k for k in sets if pm.dat(k) < pm.dat(a.datum) - datetime.timedelta(days=7)]:
        (REPO / sets.pop(dag)["pdf"]).unlink(missing_ok=True)
    bonnen = [x for x in data["pmplan"]["bonnen"] if x["datum"] == a.datum]
    rijen = {r["id"]: r for r in data.get("pm", [])}
    if bonnen:
        sjabloon = wm / "template.docx"
        sjabloon.write_bytes(ontsleutel(TEMPLATE, b["sleutel"]))
        docx = []
        for x in bonnen:
            spec = pm_spec(x, rijen)
            pad = wm / (spec["naam"] + ".docx")
            fill_bon.maak(spec, sjabloon, pad)
            docx.append(pad)
        naar_pdf(docx, wm)
        stukken = [p.with_suffix(".pdf") for p in docx]
        for p in stukken:
            paginas = int(re.search(r"Pages:\s+(\d+)", subprocess.run(["pdfinfo", str(p)], check=True, capture_output=True, text=True).stdout).group(1))
            if paginas != 1:
                print(p.stem, "%d pagina's" % paginas)
        alles = wm / "pm-set.pdf"
        if len(stukken) > 1:
            subprocess.run(["pdfunite", *map(str, stukken), str(alles)], check=True, capture_output=True)
        else:
            alles.write_bytes(stukken[0].read_bytes())
        if a.datum in sets:
            (REPO / sets[a.datum]["pdf"]).unlink(missing_ok=True)
        sets[a.datum] = {"pdf": versleutel(alles.read_bytes(), b["sleutel"]), "bonnen": len(bonnen)}
    print(a.datum + ":", len(bonnen), "PM-bonnen")
    bewaar(a.site, data)


def pm_registratie(data, r, wm):
    """Een PM-bon die helemaal is afgemeld krijgt een registratiebon in F.95.602. Alleen als PDF: dit is het bewijs en dat verandert niet meer."""
    b = stand(data)
    klaar = b.setdefault("pmreg", {})
    bon = next((x for x in data["pmplan"]["bonnen"] if x["nr"] == r["nr"]), None)
    if r["nr"] in klaar or bon is None:
        print(r["reg"], r["nr"], "staat al vast" if bon else "staat niet meer in de planning")
        return
    spec = pm_spec(bon, {x["id"]: x for x in data.get("pm", [])})
    dag = str(r.get("tijd"))[:10]
    punten = r.get("punten") or []
    afgekeurd = len({p["naam"] for p in punten})
    regels = ["Registratie van PM-bon %s, gepland op %s." % (r["nr"], bon["datum"]), ("Alle taken en controlepunten nagelopen door %s op %s, %d afgekeurd." % (r.get("door"), r.get("tijd"), afgekeurd)) if punten else "Alle taken en controlepunten afgetekend door %s op %s." % (r.get("door"), r.get("tijd"))]
    extra = (["Opmerking monteur: " + r["opmerking"].rstrip(". ") + "."] if r.get("opmerking") else []) + (["Afgekeurd: " + "; ".join(p["naam"] + " – " + p["opmerking"] for p in punten) + "."] if punten else [])
    if extra:
        regels += textwrap.wrap(" ".join(" ".join(extra).split()), 112, max_lines=2, placeholder=" … zie TD Hub")
    spec.update(
        naam=r["reg"] + spec["naam"][len(r["nr"]):], werkbon_nr=r["reg"], uitvoerder=r.get("door"), uitvoeren_op="Uitgevoerd op " + dag,
        omschrijving="Registratie " + spec["omschrijving"][0].lower() + spec["omschrijving"][1:], opmerking=regels,
        afmelding={"monteur": str(r.get("door")), "datum": dag, "vervolg": any(p.get("bon") == "Ja" for p in punten)}, foto_tekst="Geen foto bij deze registratie",
    )
    wm.mkdir(parents=True, exist_ok=True)
    sjabloon, pad = wm / "template.docx", wm / (spec["naam"] + ".docx")
    sjabloon.write_bytes(ontsleutel(TEMPLATE, b["sleutel"]))
    fill_bon.maak(spec, sjabloon, pad)
    naar_pdf([pad], wm)
    pdf = pad.with_suffix(".pdf")
    print(r["reg"], r["nr"], "registratiebon gemaakt,", subprocess.run(["pdfinfo", str(pdf)], check=True, capture_output=True, text=True).stdout.split("Pages:")[1].split()[0], "pagina")
    klaar[r["nr"]] = {"reg": r["reg"], "naam": spec["naam"], "pdf": versleutel(pdf.read_bytes(), b["sleutel"])}


def zatbon(a):
    """Maakt de bestanden voor een bon die al in het overzicht staat maar nog geen Word-bon op de site heeft."""
    data = laad(a.site)
    b = stand(data)
    wm = Path(a.map)
    rij = next(r for r in data["cm"] if r.get("nr") == a.nr)
    spec = laad(wm / (a.nr + ".json"))
    sjabloon = wm / "template.docx"
    sjabloon.write_bytes(ontsleutel(TEMPLATE, b["sleutel"]))
    docx = wm / (a.nr + ".docx")
    fill_bon.maak(spec, sjabloon, docx)
    naar_pdf([docx], wm)
    pdf = docx.with_suffix(".pdf")
    aantal = paginas(pdf)
    rij["bon"] = {"naam": spec["naam"], "docx": versleutel(docx.read_bytes(), b["sleutel"]), "pdf": versleutel(pdf.read_bytes(), b["sleutel"]), "beeld": versleutel(afbeelding(pdf).read_bytes(), b["sleutel"])}
    bewaar(a.site, data)
    print(a.nr, "1 pagina" if aantal == 1 else "%d pagina's: maak de tekst korter" % aantal)


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
x = sub.add_parser("wijzig"); x.add_argument("site"); x.add_argument("map"); x.set_defaults(fn=wijzig)
x = sub.add_parser("lijst"); x.add_argument("site"); x.add_argument("docx"); x.set_defaults(fn=lijst)
x = sub.add_parser("zaterdag"); x.add_argument("site"); x.add_argument("map"); x.set_defaults(fn=zaterdag)
x = sub.add_parser("pmdag"); x.add_argument("site"); x.add_argument("map"); x.add_argument("--datum", required=True); x.set_defaults(fn=pmdag)
x = sub.add_parser("zatbon"); x.add_argument("site"); x.add_argument("map"); x.add_argument("nr"); x.set_defaults(fn=zatbon)
x = sub.add_parser("zoekwerk"); x.add_argument("site"); x.add_argument("--aantal", type=int, default=8); x.set_defaults(fn=zoekwerk)
x = sub.add_parser("zoek"); x.add_argument("site"); x.add_argument("bestand"); x.set_defaults(fn=zoek)
a = ap.parse_args()
a.fn(a)
