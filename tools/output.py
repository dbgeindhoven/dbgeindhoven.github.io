#!/usr/bin/env python3
"""Zet de Excel-bestanden van de dagstart in site.json, voor de pagina Output per lijn.

  output.py <site.json> [--ploeg <Output per ploeg.xlsx>] [--productie <Dienstrapport productie.xlsx>] [--inpak <Dienstrapport inpak en ompak.xlsx>]

Wat niet wordt meegegeven blijft staan. Bestanden zijn alleen te lezen, de kolommen worden op naam gezocht.

  Output per ploeg: kilo's per lijn en ploeg (tabblad output) en het plan per lijn (tabblad DBG Production Order, op Due Date).
  Dienstrapport inpak en ompak: gereed en uitval in kilo (Kilo's I&O), pallets (Palletrealisatie) en bijzonderheden (Dienstrapport I&O).
  Dienstrapport productie: stilstand per lijn (Dienstrapport productie). De kilo's in dat bestand zijn leeg.

Andere tabbladen, zoals Personele zaken en Bedrijfsongevallen, worden niet gelezen.

Voor de productie-pilot zet het ook prod_excel in site.json: per dienst wat de Excel-bestanden zeggen, in de vorm van de productie-app.
"""
import argparse
import collections
import datetime
import json
import re
import warnings

import openpyxl

warnings.filterwarnings("ignore")

CIJFERS_DAGEN = 21  # kilo's en pallets, genoeg voor de lopende week en 7 productiedagen
RAPPORT_DAGEN = 400  # teksten uit het dienstrapport: ruim een jaar blijft in site.json bewaard; de site zelf krijgt minder (site.py)
TEKENS = 240
DIENSTEN = ("Ochtend", "Middag", "Nacht")
LIJNEN = ("Lijn 1", "Lijn 2", "Lijn 3")
PLOEGEN = ("ochtend", "middag", "nacht a", "nacht b")
# Geen regels over personen in de dagstart: die horen in Personele zaken.
PERSOONLIJK = re.compile(r"\b(ziek|ziekte|verzuim|te laat|afgemeld|niet op komen)\b", re.I)
NIETS = re.compile(r"^\W*(geen bijzonderheden|goed ?gelopen|goed ?gedraaid)\W*$", re.I)


def boek(pad):
    return openpyxl.load_workbook(pad, data_only=True, read_only=True)


def kop_naam(v):
    return " ".join(str(v).replace("\xa0", " ").split()) if v is not None else ""


def rijen(ws, eerste):
    """Geeft de regels als woordenboek, vanaf de kopregel waarvan de eerste cel begint met eerste."""
    kop = None
    for r in ws.iter_rows(values_only=True):
        if kop is None:
            if str(r[0] or "").startswith(eerste):
                kop = [kop_naam(v) for v in r]
            continue
        yield {k: v for k, v in zip(kop, r) if k}, r


def dag(v, tot):
    """Een echte datum, niet in de toekomst. In het dienstrapport staan ook tikfouten als 2029."""
    if isinstance(v, datetime.datetime) and datetime.date(2020, 1, 1) <= v.date() <= tot:
        return v.date()
    return None


def tekst(d):
    return d.strftime("%d-%m-%Y")


def getal(v):
    if isinstance(v, bool):
        return 0
    if isinstance(v, (int, float)):
        return v
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        return 0


def schoon(v):
    return " ".join(str(v or "").split())


def dienst(v):
    m = re.search(r"ochtend|middag|nacht", str(v or ""), re.I)
    return m.group(0).capitalize() if m else None


def lees_ploeg(pad, vandaag):
    wb = boek(pad)
    kg, laatst = collections.Counter(), None
    for x, _ in rijen(wb["output"], "Entry No_"):
        d, lijn = dag(x.get("Registering Date"), vandaag), re.fullmatch(r"EHV_PRDL([123])", str(x.get("lijn")))
        if not d or not lijn or x.get("ploeg") not in PLOEGEN:
            continue
        kg[(d, "Lijn " + lijn.group(1), x.get("ploeg"))] += getal(x.get("output kgs tot"))
        tijd = str(x.get("tijdstip") or "")
        if laatst is None or (d, tijd) > laatst:
            laatst = (d, tijd)
    if not laatst:
        raise SystemExit("Geen boekingen gevonden op het tabblad output")
    grens = laatst[0] - datetime.timedelta(days=CIJFERS_DAGEN)
    plan = collections.Counter()
    for x, _ in rijen(wb["DBG Production Order"], "Status"):
        d, lijn = x.get("Due Date"), re.fullmatch(r"EHV_PRDL([123])", str(x.get("Production Line No_")))
        if isinstance(d, datetime.datetime) and lijn and d.date() >= grens:
            plan[(d.date(), "Lijn " + lijn.group(1))] += getal(x.get("Total Net Weight"))
    return {
        "bron": "Output per ploeg EHV, stand %s %s" % (tekst(laatst[0]), laatst[1][:5]), "tot": tekst(laatst[0]),
        "dagen": [{"datum": tekst(d), "lijn": l, "ploeg": p, "kg": round(v)} for (d, l, p), v in sorted(kg.items(), key=lambda i: (i[0][0], i[0][1], str(i[0][2]))) if v and d >= grens],
        "plan": [{"datum": tekst(d), "lijn": l, "kg": round(v)} for (d, l), v in sorted(plan.items()) if v],
    }


def lees_inpak(pad, vandaag):
    wb = boek(pad)
    regels, opm, extra = {}, [], {}
    woord = lambda v: schoon(v) if isinstance(v, str) and schoon(v) else ""  # in de verklaringskolommen staan soms getallen

    def regel(d, ds, n):
        return regels.setdefault((d, DIENSTEN.index(ds), n), {"datum": tekst(d), "dienst": ds, "lijn": "Lijn %d" % n, "kg": 0, "uitval": 0, "pallets": 0})

    for x, _ in rijen(wb["Kilo's I&O"], "Invoer"):
        d, ds = dag(x.get("Invoer (I&O)"), vandaag), dienst(x.get("Dienst (I&O)"))
        if d and ds:
            for n in (1, 2, 3):
                kg, uit = getal(x.get("Gereed L%d (I&O)" % n)), getal(x.get("Uitval lijn %d (I&O)" % n))
                if kg or uit:
                    r = regel(d, ds, n)
                    r["kg"], r["uitval"] = round(kg), round(uit)
                    if woord(x.get("Verklaring lijn %d (I&O)" % n)):
                        r["verklaring"] = woord(x.get("Verklaring lijn %d (I&O)" % n))[:TEKENS]
            e = {"ompak_uitval": round(getal(x.get("Uitval ompak (I&O)"))), "ompak_verklaring": woord(x.get("Verklaring ompak (I&O)"))[:TEKENS], "uitzoeken": round(getal(x.get("Uitval uitzoeken (I&O)")))}
            if any(e.values()):
                extra[(d, DIENSTEN.index(ds))] = dict(e, datum=tekst(d), dienst=ds)
    kop = None
    for x, r in rijen(wb["Palletrealisatie"], "Invoer"):
        d, ds = dag(x.get("Invoer (I&O)"), vandaag), dienst(x.get("Dienst (I&O)"))
        if not d or not ds:
            continue
        for n in (1, 2, 3):
            p = getal(x.get("Gereed lijn %d (I&O)" % n))
            if p:
                regel(d, ds, n)["pallets"] = p
        # De toelichting staat in de kolom Verklaringen of in de kolom ernaast, die geen kop heeft.
        t = [schoon(v) for v in r[9:11] if isinstance(v, str) and schoon(v)]
        if t:
            opm.append((d, ds, "; ".join(t)))
    if not regels:
        raise SystemExit("Geen kilo's gevonden op het tabblad Kilo's I&O")
    tot = max(k[0] for k in regels)
    grens = tot - datetime.timedelta(days=CIJFERS_DAGEN)
    return {
        "bron": "Dienstrapport inpak en ompak, t/m %s" % tekst(tot), "tot": tekst(tot),
        "dagen": [v for k, v in sorted(regels.items()) if k[0] >= grens],
        "opm": [{"datum": tekst(d), "dienst": ds, "tekst": t[:TEKENS]} for d, ds, t in opm if d >= grens],
        "extra": [v for k, v in sorted(extra.items()) if k[0] >= grens],
    }


def rapportregel(d, ds, waar, machine, uren, stil, t, van=None, tot=None):
    r = {"datum": tekst(d), "dienst": ds, "waar": waar, "machine": schoon(machine) or None, "uren": round(getal(uren), 2), "stil": stil, "tekst": t[:TEKENS]}
    if van or tot:
        r["van"], r["tot"] = van or "", tot or ""
    return r


OMGEDRAAID = []  # regels waarvan van en tot omgedraaid zijn ingevuld, om te melden


def minuten(v):
    """Tijdstip als minuten na middernacht, ook als Excel er een datum aan hangt (1900-01-01 06:05)."""
    if isinstance(v, (datetime.time, datetime.datetime)):
        return v.hour * 60 + v.minute
    return None


def hhmm(v):
    m = minuten(v)
    return "%02d:%02d" % divmod(m, 60) if m is not None else None


def stilstand_uren(x, d, ds, uren_kol, van_kol, tot_kol):
    """Duur, van en tot van een regel uit het dienstrapport. Ligt tot minder dan een uur vóór van, dan zijn van en tot omgedraaid ingevuld:
    Excel rekent dan bijna een hele dag (23:30 tot 23:15 wordt 23,75 uur). De duur is dan van min tot, en van en tot wisselen om."""
    uren = getal(x.get(uren_kol))
    v, t = x.get(van_kol), x.get(tot_kol)
    van, tot = minuten(v), minuten(t)
    if van is not None and tot is not None and 0 < van - tot <= 60 and uren > 12:
        OMGEDRAAID.append("%s %s: %s tot %s, %s uur wordt %s uur" % (tekst(d), ds.lower(), hhmm(v), hhmm(t), round(uren, 2), round((van - tot) / 60, 2)))
        return (van - tot) / 60, hhmm(t), hhmm(v)
    return uren, hhmm(v), hhmm(t)


def lees_productie(pad, vandaag):
    uit = []
    for x, _ in rijen(boek(pad)["Dienstrapport productie"], "Invoer"):
        d, ds = dag(x.get("Invoer (PR)"), vandaag), dienst(x.get("Dienst (PR)"))
        t, soort, machine = schoon(x.get("Omschrijving (PR)")), schoon(x.get("Lijn (PR)")).lower(), schoon(x.get("Machine (PR)"))
        if not d or not ds or not t or NIETS.match(t) or PERSOONLIJK.search(t):
            continue
        stil = {"ja": "Ja", "halve capaciteit": "Halve capaciteit"}.get(schoon(x.get("Stilstand (PR)")).lower(), "Nee")
        m = re.search(r"l\s*([123])\b", soort) or re.fullmatch(r"l\s*([123])", machine, re.I)
        waar = "Ompak" if "ompak" in soort else "Lijn " + m.group(1) if m else None
        # Procesregels zonder stilstand zijn een verhaal over de dienst, geen oorzaak.
        if waar and (soort.startswith("techniek") or stil != "Nee"):
            uren, van, tot = stilstand_uren(x, d, ds, "Totaal stilstand (PR)", "Storing van (PR)", "Storing tot (PR)")
            uit.append((d, DIENSTEN.index(ds), rapportregel(d, ds, waar, machine, uren, stil, t, van, tot)))
    return uit


def lees_io(pad, vandaag):
    uit = []
    for x, _ in rijen(boek(pad)["Dienstrapport I&O"], "Invoer"):
        d, ds = dag(x.get("Invoer (I&O)"), vandaag), dienst(x.get("Dienst (I&O)"))
        t, soort = schoon(x.get("Omschrijving (I&O)")), schoon(x.get("Lijn (I&O)")).lower()
        if not d or not ds or not t or NIETS.match(t) or PERSOONLIJK.search(t):
            continue
        uren, van, tot = stilstand_uren(x, d, ds, "Totaal storing (I&O)", "Storing van (I&O)", "Storing tot (I&O)")
        if soort.startswith("techniek") or soort == "kwaliteit" or uren:
            uit.append((d, DIENSTEN.index(ds), rapportregel(d, ds, "Ompak" if "ompak" in soort else "Inpak", x.get("Machine (I&O)"), uren, None, t, van, tot)))
    return uit


def excel_diensten(o):
    """Productie (pilot): per dienst wat de Excel-bestanden zeggen, in dezelfde vorm als de productie-app (gegevens), zodat de pagina Diensten
    ze naast de app kan tonen. Een nacht hoort bij de dag waarop hij begint: in Output per ploeg is dat nacht a van die dag plus nacht b van de dag erna."""
    D = lambda s: datetime.datetime.strptime(s, "%d-%m-%Y").date()
    kg = collections.defaultdict(float)
    for x in o.get("dagen") or []:
        p, d = x.get("ploeg") or "", D(x["datum"])
        ds = "Nacht" if p.startswith("nacht") else p.capitalize()
        if p == "nacht b":
            d -= datetime.timedelta(days=1)
        if ds in DIENSTEN:
            kg[(d, ds, x["lijn"])] += x.get("kg") or 0
    io = o.get("io") or {}
    io_r = {(D(x["datum"]), x["dienst"], x["lijn"]): x for x in io.get("dagen") or []}
    opm = collections.defaultdict(list)
    for x in io.get("opm") or []:
        opm[(D(x["datum"]), x["dienst"])].append(x["tekst"])
    extra = {(D(x["datum"]), x["dienst"]): x for x in io.get("extra") or []}
    sto = collections.defaultdict(list)
    for x in o.get("rapport") or []:
        afd = "Bakkerij" if x["waar"].startswith("Lijn") else "Inpak en ompak"
        r = {"lijn": x["waar"], "machine": x.get("machine") or "", "van": x.get("van") or "", "tot": x.get("tot") or "", "tekst": x.get("tekst") or "", "uren": x.get("uren") or 0}
        if afd == "Bakkerij":
            r["stil"] = x.get("stil") or "Nee"
        sto[(D(x["datum"]), x["dienst"], afd)].append(r)
    cijfers = {k[0] for k in kg} | {k[0] for k in io_r}
    if not cijfers:
        return []
    eind = max(cijfers | {k[0] for k in sto})
    grens = eind - datetime.timedelta(days=CIJFERS_DAGEN)
    uit = []
    for d in sorted(x for x in cijfers | {k[0] for k in sto} if grens < x <= eind):
        for ds in DIENSTEN:
            out = {l: round(kg[(d, ds, l)]) for l in LIJNEN if kg.get((d, ds, l))}
            if not out:  # zonder Output per ploeg: wat inpak gereed meldde
                out = {l: io_r[(d, ds, l)]["kg"] for l in LIJNEN if (io_r.get((d, ds, l)) or {}).get("kg")}
            s = sto.get((d, ds, "Bakkerij"), [])
            if out or s:
                uit.append({"datum": tekst(d), "dienst": ds, "afdeling": "Bakkerij", "gegevens": {"output": out, "storingen": s, "bijzonderheden": ""}})
            ger, pal = {}, {}
            for l in LIJNEN:
                x = io_r.get((d, ds, l)) or {}
                if x.get("kg") or x.get("uitval"):
                    ger[l] = {"kg": x.get("kg") or 0, "uitval": x.get("uitval") or 0}
                    if x.get("verklaring"):
                        ger[l]["verklaring"] = x["verklaring"]
                if x.get("pallets"):
                    pal[l] = x["pallets"]
            e = extra.get((d, ds)) or {}
            ompak = {k: v for k, v in (("uitval", e.get("ompak_uitval")), ("verklaring", e.get("ompak_verklaring"))) if v}
            uitz = {"kg": e["uitzoeken"]} if e.get("uitzoeken") else {}
            s = sto.get((d, ds, "Inpak en ompak"), [])
            if ger or pal or s or ompak or uitz:
                uit.append({"datum": tekst(d), "dienst": ds, "afdeling": "Inpak en ompak", "gegevens": {"gereed": ger, "ompak": ompak, "uitzoeken": uitz, "pallets": pal,
                            "palletsVerklaring": "; ".join(opm.get((d, ds), [])), "blokkades": [], "storingen": s, "bijzonderheden": ""}})
    return uit


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("site")
    p.add_argument("--ploeg")
    p.add_argument("--productie")
    p.add_argument("--inpak")
    a = p.parse_args()
    vandaag = datetime.date.today()
    data = json.load(open(a.site, encoding="utf-8"))
    o = data.setdefault("output", {"eenheid": "kg", "dagen": [], "plan": []})
    if a.ploeg:
        o.update(lees_ploeg(a.ploeg, vandaag))
    if a.inpak:
        o["io"] = lees_inpak(a.inpak, vandaag)
    # Het dienstrapport hoort bij de cijfers: een bestand dat niet is meegegeven houdt zijn eigen regels.
    # Regels van vóór de eerste dag in het nieuwe bestand blijven ook staan: zo groeit de geschiedenis, ook als het Excel minder dagen bevat.
    vervangen = lambda r: (r["waar"].startswith("Lijn") and a.productie) or (not r["waar"].startswith("Lijn") and a.inpak)
    nieuw = (lees_productie(a.productie, vandaag) if a.productie else []) + (lees_io(a.inpak, vandaag) if a.inpak else [])
    if nieuw:
        vroegst = min(x[0] for x in nieuw)
        grens = max(x[0] for x in nieuw) - datetime.timedelta(days=RAPPORT_DAGEN)
        dag_van = lambda r: datetime.datetime.strptime(r["datum"], "%d-%m-%Y").date()
        oud = [r for r in o.get("rapport", []) if not vervangen(r) or grens <= dag_van(r) < vroegst]
        regels = [(dag_van(r), DIENSTEN.index(r["dienst"]) if r.get("dienst") in DIENSTEN else 9, r) for r in oud] + [x for x in nieuw if x[0] >= grens]
        o["rapport"] = [x[2] for x in sorted(regels, key=lambda x: (x[0], x[1]))]
    diensten = excel_diensten(o)
    tot = max((datetime.datetime.strptime(x["datum"], "%d-%m-%Y").date() for x in diensten), default=None)
    data["prod_excel"] = {"bron": "Excel-dienstrapporten, t/m %s" % tekst(tot) if tot else "", "diensten": diensten}
    json.dump(data, open(a.site, "w", encoding="utf-8"), ensure_ascii=False)
    print("Output:", len(o.get("dagen", [])), "regels, plan", len(o.get("plan", [])), "| inpak en ompak:", len((o.get("io") or {}).get("dagen", [])), "| dienstrapport:", len(o.get("rapport", [])))
    print("Productie (pilot): %d diensten uit Excel" % len(diensten))
    for r in OMGEDRAAID:
        print("Van en tot omgedraaid:", r)


if __name__ == "__main__":
    main()
