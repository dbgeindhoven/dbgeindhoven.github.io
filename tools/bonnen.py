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

In de werkmap staat werk.json: een lijst met de inhoud van de wachtrijbestanden, elk aangevuld
met drive_id. Per bon staat daar <nr>.json met de tekst van de bon; maak zet er <nr>.docx en
<nr>.pdf en <nr>-bon.jpg (de afbeelding waarmee de bon op de site opent) naast. De leesbare bonnen en het template komen nooit in deze repository, alleen
versleuteld in bonnen/.
"""
import argparse, base64, datetime, json, re, secrets, subprocess, sys, tempfile
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
            data["bestellijst"].append(bestelregel(w["nr"], spec.get("onderdelen"), "Uit storing van " + datum + ", monteur " + str(w.get("melder")) + ". Foto op de bon."))
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


def stop_weg(data, k):
    """De bonnen blijven bestaan. Wat nog niet klaar is staat daarna nergens meer op."""
    s = plan_van(data, k)
    if not k or not s:
        return
    cm = {r.get("nr"): r for r in data.get("cm", [])}
    for r in zat_rijen(s):
        c = cm.get(r.get("nr"))
        if c and c.get("status") not in KLAAR:
            c["uitvoeren"] = None
            if c.get("status") == "Gepland":
                c["status"] = "Open"
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


def bon_uitvoeren(data, rij, wm):
    """Zet de nieuwe tekst bij Uitvoeren op ook op de Word- en PDF-bon."""
    bon = rij.get("bon") or {}
    print(rij["nr"], "uitvoeren op", rij["uitvoeren"])
    if not bon.get("docx"):
        return
    b = stand(data)
    wm.mkdir(parents=True, exist_ok=True)
    docx = wm / (bon["naam"] + ".docx")
    docx.write_bytes(fill_bon.zet_uitvoeren(ontsleutel(Path(bon["docx"]).name, b["sleutel"]), rij["uitvoeren"]))
    naar_pdf([docx], wm)
    pdf = docx.with_suffix(".pdf")
    for k in ("docx", "pdf", "beeld"):
        if bon.get(k):
            (REPO / bon[k]).unlink(missing_ok=True)
    bon.pop("stempel", None)
    bon.update(docx=versleutel(docx.read_bytes(), b["sleutel"]), pdf=versleutel(pdf.read_bytes(), b["sleutel"]), beeld=versleutel(afbeelding(pdf).read_bytes(), b["sleutel"]))


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
    regel = "%s, %s: %s." % (dag, door or "Monteur", keuze) + (" " + tekst.rstrip(". ") + "." if tekst else "")
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


def volgorde(w):
    """Een nieuwe stop eerst, bonnen kunnen er al naartoe verplaatst zijn. Het vervolg uit het dienstrapport als laatste, op tijd: het nummer eindigt op het moment van de wijziging."""
    extra = w.get("rij") or {}
    return (not extra.get("stop"), bool(extra.get("vervolg")), w["nr"] if extra.get("vervolg") else "")


def wijzig(a):
    """Zet een status uit de site op de bon, of haalt de bon weg. Het nummer wordt daarna niet opnieuw uitgegeven."""
    data = laad(a.site)
    opnieuw = []
    for w in sorted(laad(Path(a.map) / "wijzig.json"), key=volgorde):
        nr, status = w["nr"], w["status"]
        extra = w.get("rij") or {}
        if extra.get("vervolg"):
            vervolg_wijzig(data, extra["vervolg"], w, opnieuw)
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
        rij = next((r for r in data["cm"] if r.get("nr") == nr), None)
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
            if status in klaar and not rij.get("uitgevoerd_op"):
                rij["uitgevoerd_op"] = str(w.get("tijd"))[:10]
            elif rij.get("status") in klaar and status not in klaar:
                rij["uitgevoerd_op"] = None
            rij["status"] = status
            print(nr, status)
            if "uitvoeren" in extra:
                rij["uitvoeren"] = extra["uitvoeren"] or None
                opnieuw.append(rij)
    for rij in opnieuw:
        bon_uitvoeren(data, rij, Path(a.map) / "uitvoeren")
    bewaar(a.site, data)


def zat_regel(r, c):
    """Wat er op de lijst en de bon staat. De site rekent hetzelfde uit in zatStempel."""
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


def plan_print(data, z, wm, oud):
    """Zet prio, uitvoerder en datum op de bonnen van een plan en maakt de PDF om te printen. Wat niet veranderde blijft staan."""
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
    if not nieuw and oud.get("datum") == z.get("datum") and oud.get("stempel") == stempel:
        print(plan_naam(z) + ": printversie is actueel.")
        return oud
    regel = lambda r: (r["nr"], r.get("werkzaamheid"), r.get("lijn_machine"), *zat_regel(r, cm.get(r["nr"])))
    docx = wm / "zaterdaglijst.docx"
    datum = str(z.get("datum")) + (" – " + str(z.get("lijn")) if z.get("lijn") else "")
    docx.write_bytes(fill_bon.zaterdaglijst(ontsleutel(LIJST, b["sleutel"]), datum, [[regel(r) for r in z.get(k) or []] for k in ("correctief", "preventief")], z, plan_tekst(z)))
    naar_pdf([docx], wm)
    stukken = [docx.with_suffix(".pdf")]
    for i, r in enumerate(zat_rijen(z)):
        bon = (cm.get(r["nr"]) or {}).get("bon")
        if bon and bon.get("pdf"):
            p = wm / ("stuk-%03d.pdf" % i)
            p.write_bytes(ontsleutel(Path(bon["pdf"]).name, b["sleutel"]))
            stukken.append(p)
    alles = wm / "zaterdagwerk.pdf"
    subprocess.run(["pdfunite", *map(str, stukken), str(alles)], check=True, capture_output=True)
    if oud.get("pdf"):
        (REPO / oud["pdf"]).unlink(missing_ok=True)
    print(plan_naam(z) + ": printversie gemaakt,", len(stukken) - 1, "bonnen,", len(nieuw), "bijgewerkt")
    return {"datum": z.get("datum"), "pdf": versleutel(alles.read_bytes(), b["sleutel"]), "stempel": stempel}


def zaterdag(a):
    """Doet dit voor de zaterdaglijst en elke onderhoudsstop. De PDF van een weggehaalde stop verdwijnt."""
    data = laad(a.site)
    b = stand(data)
    wm = Path(a.map)
    if data.get("zaterdag"):
        b["zaterdag"] = plan_print(data, data["zaterdag"], wm / "zaterdag", b.get("zaterdag") or {})
    klaar = b.setdefault("stops", {})
    for s in data.get("stops") or []:
        klaar[s["id"]] = plan_print(data, s, wm / s["id"], klaar.get(s["id"]) or {})
    for k in [k for k in klaar if not plan_van(data, k)]:
        (REPO / klaar.pop(k)["pdf"]).unlink(missing_ok=True)
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
        "omschrijving": "Preventief %s – %s %s" % (freq, b["lijndeel"], b["lijn"].lower()),
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
    paginas = int(re.search(r"Pages:\s+(\d+)", subprocess.run(["pdfinfo", str(pdf)], check=True, capture_output=True, text=True).stdout).group(1))
    rij["bon"] = {"naam": spec["naam"], "docx": versleutel(docx.read_bytes(), b["sleutel"]), "pdf": versleutel(pdf.read_bytes(), b["sleutel"]), "beeld": versleutel(afbeelding(pdf).read_bytes(), b["sleutel"])}
    bewaar(a.site, data)
    print(a.nr, "1 pagina" if paginas == 1 else "%d pagina's: maak de tekst korter" % paginas)


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
a = ap.parse_args()
a.fn(a)
