#!/usr/bin/env python3
"""Bouwt de TD-site uit één gegevensbestand (site.json).

De gegevens staan NIET in deze repository. Ze staan leesbaar in de privépagina
bij Claude en versleuteld in index.html. Zie CLAUDE.md voor de werkwijze.

  site.py extract <privepagina.html> <site.json>
  site.py setkey  <site.json> --password "..." [--niveau td|dagstart|melden|monteur|wv|kijk|output|pm|productie|extern]
  site.py build   <site.json> --stand DD-MM-JJJJ --plain <uit.html> --public <index.html>
"""
import argparse, base64, copy, datetime, hashlib, hmac, json, re, secrets
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import pm

TOOLS = Path(__file__).resolve().parent
ITER = 600_000
GESLOTEN = ("Uitgevoerd", "Gereed", "Dubbel", "Vervallen")
HEAD = (
    '<!doctype html><html lang="nl"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
    '<meta name="robots" content="noindex,nofollow">'
    "<style>:root{padding:env(safe-area-inset-top,0) 0 env(safe-area-inset-bottom,0)}"
    "[hidden]{display:none!important}img{max-width:100%}</style></head><body>"
)
FOOT = "</body></html>"
b64 = lambda b: base64.b64encode(b).decode("ascii")


def fill(tpl, mode, payload):
    return tpl.replace("__MODE__", mode).replace("__PAYLOAD__", payload.replace("</", "<\\/"))


def bestel_groep(r):
    """Zet de statusteksten uit de bronnen om naar vaste groepen."""
    s = (r.get("status") or "").strip()
    t = s.lower()
    if t == "binnen":
        g = "Binnen"
    elif t in ("ja", "besteld"):
        g = "Besteld"
    elif t.startswith("opgevraagd"):
        g = "Opgevraagd"
    elif "opnemen" in t or "optekenen" in t or t.startswith("eerst"):
        g = "Eerst opmeten of checken"
    else:
        g = "Nog niet besteld"
    r["groep"] = g
    r["toelichting"] = s if len(s) > 12 else None


def extract(a):
    html = Path(a.html).read_text("utf-8")
    m = re.search(r'<script id="payload" type="application/json">(.*?)</script>', html, re.S)
    data = json.loads(m.group(1))
    Path(a.site).write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    print({k: len(v) for k, v in data.items() if isinstance(v, list)})


def setkey(a):
    """Zet het wachtwoord voor een niveau: wv (alles plus de bonnen), kijk (alles van wv, alleen lezen), td (alles), dagstart (dagstartpagina's), melden (alleen het meldformulier), monteur (storing melden en dienstrapport), pm (alleen de PM-bonnen), output (alleen het outputformulier) of productie (alleen de productie-app, pilot) of extern (de externe ploeg: alleen de bonnen van de zaterdag afmelden)."""
    from cryptography.hazmat.primitives.hashes import SHA256
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    p = Path(a.site)
    data = json.loads(p.read_text("utf-8"))
    pub = data["meta"].setdefault("publiek", {"iter": ITER, "salt": b64(secrets.token_bytes(16))})
    salt = base64.b64decode(pub["salt"])
    key = PBKDF2HMAC(algorithm=SHA256(), length=32, salt=salt, iterations=pub["iter"]).derive(a.password.encode("utf-8"))
    if a.naam:
        # Een eigen inlog per monteur: zelfde deel als de gedeelde monteurinlog, met zijn naam erbij.
        if a.niveau == "externmonteur":
            # Monteur 1 tot en met 12 van de externe ploeg: de monteur typt in de app zelf zijn naam.
            if a.naam not in [str(i) for i in range(1, 13)]:
                raise SystemExit("--naam is het nummer van de monteur, 1 tot en met 12")
            pub.setdefault("extern_monteurs", {})[a.naam] = b64(key)
            p.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
            return
        if a.niveau != "monteur":
            raise SystemExit("--naam hoort bij --niveau monteur of externmonteur")
        pub.setdefault("monteurs", {})[a.naam] = b64(key)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
        return
    pub[{"td": "sleutel", "dagstart": "sleutel_dagstart", "melden": "sleutel_melden", "monteur": "sleutel_monteur", "wv": "sleutel_wv", "kijk": "sleutel_kijk", "output": "sleutel_output", "pm": "sleutel_pm", "productie": "sleutel_productie", "extern": "sleutel_extern"}[a.niveau]] = b64(key)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")


def storingen(data):
    """Lopende storingen: open bonnen uit het CM-overzicht. Gereed verdwijnt vanzelf. Dezelfde regels als storingRij in de site."""
    besteld = {r.get("cm") for r in data.get("bestellijst", []) if r.get("groep") == "Besteld"}
    uit = []
    for r in data.get("cm", []):
        if r.get("status") in GESLOTEN or not str(r.get("bron") or "").startswith("CM-overzicht"):
            continue
        if r.get("status") == "Gepland":
            st = "Gepland"
        elif r.get("status") in ("Besteld", "Leverdatum", "In bestelling") or r.get("nr") in besteld:
            st = "In bestelling"
        else:
            st = "Open"
        uit.append({"nr": r.get("nr"), "storing": r.get("omschrijving"), "lijn": r.get("lijn"), "machine": r.get("machine"),
                    "status": st, "actiehouder": r.get("actiehouder") or r.get("monteur"), "prio": r.get("prio")})
    uit.sort(key=lambda x: (x["prio"] or 9, ["Open", "In bestelling", "Gepland"].index(x["status"]), int(re.search(r"\d+", x["nr"]).group())))
    return uit


def bestel_ids(data):
    """Elke bestelregel krijgt een vast nummer, zodat de site één regel kan aanpassen."""
    rijen = data.get("bestellijst", [])
    hoogste = max([int(r["id"][1:]) for r in rijen if re.fullmatch(r"B\d+", str(r.get("id") or ""))] + [0])
    for r in rijen:
        if not r.get("id"):
            hoogste += 1
            r["id"] = "B%d" % hoogste


def zaterdag(data):
    """Regels zonder eigen prio krijgen die van de bon. De dagstart heeft geen CM-overzicht."""
    cm = {r.get("nr"): r for r in data.get("cm", [])}
    for z in [data.get("zaterdag") or {}] + (data.get("stops") or []):
        for r in (z.get("correctief") or []) + (z.get("preventief") or []):
            if not r.get("prio") and (cm.get(r.get("nr")) or {}).get("prio"):
                r["prio"] = cm[r["nr"]]["prio"]


def machines(data):
    """Machines per lijn voor het storingsformulier: de opnamelijsten plus meta.machines_extra."""
    uit = {}
    for r in data.get("opnamelijsten", []):
        uit.setdefault(r.get("lijn") or "Overig", []).append(r["machine"])
    for lijn, namen in (data["meta"].get("machines_extra") or {}).items():
        uit.setdefault(lijn, []).extend(n for n in namen if n not in uit.get(lijn, []))
    return uit


PROD_ALGEMEEN = re.compile(r"^(l ?\d|lijn ?\d|inpak/ompak|inpak|ompak|-)?$", re.I)


def prod_machines(data):
    """Productie-app (pilot): de machines per lijn en voor inpak en ompak zoals ze in het dienstrapport staan, zodat een storing dezelfde naam krijgt.
    Algemene namen (L1, L2, L3, Inpak/ompak) tellen niet. Bij verschillende schrijfwijzen wint de vaakst gebruikte."""
    tel = {}
    for r in (data.get("output") or {}).get("rapport") or []:
        m = str(r.get("machine") or "").strip()
        if r.get("waar") not in ("Lijn 1", "Lijn 2", "Lijn 3", "Inpak", "Ompak") or PROD_ALGEMEEN.match(m):
            continue
        w = tel.setdefault(r["waar"], {}).setdefault(m.lower(), {})
        w[m] = w.get(m, 0) + 1
    return {waar: sorted((max(v, key=v.get) for v in namen.values()), key=str.lower) for waar, namen in tel.items()}


def prod_plan(data, stand):
    """De planning per lijn uit de productieorders, van een week terug tot twee weken vooruit. De app toont hem bij de output."""
    nu = datetime.datetime.strptime(stand, "%d-%m-%Y")
    uit = []
    for r in (data.get("output") or {}).get("plan") or []:
        try:
            d = datetime.datetime.strptime(r.get("datum") or "", "%d-%m-%Y")
        except ValueError:
            continue
        if -7 <= (d - nu).days <= 14:
            uit.append({k: r.get(k) for k in ("datum", "lijn", "kg")})
    return uit


def kopie_kenmerk(b, soort, pad):
    """Naam en sleutel van een kopie volgen uit de bon, zodat elke bouw hetzelfde bestand vindt. Uit de sleutel van een kopie is de sleutel van de bonnen niet terug te rekenen."""
    return hmac.new(base64.b64decode(b["sleutel"]), (soort + ":" + pad).encode("utf-8"), hashlib.sha256).digest()


def opname_kopieen(data, ook=()):
    """De monteurs hebben de sleutel van de bonnen niet. Elke open bon bij de monteurs (Uitvoerbare bonnen en opnamebonnen) krijgt daarom
    een eigen kopie van de originele bon, met een eigen sleutel die alleen in het monteursdeel staat. Gaat de bon van de lijst of dicht, dan verdwijnt de kopie."""
    b, map_, uit = data["meta"].get("bonnen") or {}, TOOLS.parent, {}
    if not b.get("sleutel"):
        return uit
    bron = AESGCM(base64.b64decode(b["sleutel"]))
    for r in data.get("cm", []):
        bon = r.get("bon") or {}
        if not bon.get("pdf"):
            continue
        sleutel = kopie_kenmerk(b, "sleutel", bon["pdf"])
        paden = {s: "bonnen/%s.bin" % kopie_kenmerk(b, "bestand", bon[s])[:8].hex() for s in ("pdf", "beeld") if bon.get(s)}
        if not ((r.get("week") or r.get("nr") in ook) and r.get("status") not in GESLOTEN):
            for p in paden.values():
                (map_ / p).unlink(missing_ok=True)
            continue
        try:
            for s, p in paden.items():
                if not (map_ / p).exists():
                    x = (map_ / bon[s]).read_bytes()
                    iv = secrets.token_bytes(12)
                    (map_ / p).write_bytes(iv + AESGCM(sleutel).encrypt(iv, bron.decrypt(x[:12], x[12:], None), None))
        except OSError as e:
            print(r["nr"], "geen kopie voor de monteurs:", e)
            continue
        uit[r["nr"]] = {"naam": bon.get("naam") or r["nr"], "sleutel": b64(sleutel), **paden}
    return uit


def box(tekst, sleutel):
    iv = secrets.token_bytes(12)
    ct = AESGCM(base64.b64decode(sleutel)).encrypt(iv, json.dumps(tekst, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), None)
    return {"iv": b64(iv), "ct": b64(ct)}



def kort_rapport(output, dagen):
    """Het productierapport in site.json bewaart ruim een jaar (output.py). De site krijgt alleen de laatste dagen: zo blijft index.html licht."""
    o = dict(output or {})
    r = o.get("rapport") or []
    if r:
        dag = lambda x: datetime.datetime.strptime(x["datum"], "%d-%m-%Y").date()
        grens = max(dag(x) for x in r) - datetime.timedelta(days=dagen)
        o["rapport"] = [x for x in r if dag(x) > grens]
    return o

def build(a):
    data = json.loads(Path(a.site).read_text("utf-8"))
    data["meta"]["stand"] = a.stand
    for r in data.get("bestellijst", []):
        if not r.get("groep"):
            bestel_groep(r)
    bestel_ids(data)
    data["storingen"] = storingen(data)
    zaterdag(data)
    pm.bijwerken(data, a.stand)
    data.setdefault("sqdc", {}).pop("auto", None)
    data["machines"] = machines(data)
    # Meldingen waarvan de bon is afgesloten, zodat ze uit "Nog open" in het dienstrapport verdwijnen.
    gesloten = [r["melding"] for r in data.get("cm", []) if r.get("melding") and r.get("status") in GESLOTEN]
    data["meta"].setdefault("bonnen", {})["gesloten"] = gesloten
    # Rooster van de storingsdienst: bij de eerste keer staan de monteurs met een eigen inlog in de keuzelijst.
    if "rooster" not in data:
        data["rooster"] = {"mensen": sorted((data["meta"].get("publiek") or {}).get("monteurs") or {}), "dagen": {}}
    tpl = (TOOLS / "template.html").read_text("utf-8")
    Path(a.plain).write_text(fill(tpl, "plain", json.dumps(data, ensure_ascii=False, separators=(",", ":"))), "utf-8")

    td = copy.deepcopy(data)
    # 31 dagen voor het RCA-signaal (regels over 30 dagen), de dagstart heeft genoeg aan 14.
    td["output"] = kort_rapport(td.get("output"), 31)
    pub = td["meta"].pop("publiek")
    mld = td["meta"].get("meldingen") or {}
    meld_sleutel = mld.pop("sleutel_melden", None)
    monteur_sleutel = mld.pop("sleutel_monteur", None)
    output_sleutel = mld.pop("sleutel_output", None)
    pm_sleutel = mld.pop("sleutel_pm", None)
    productie_sleutel = mld.pop("sleutel_productie", None)
    extern_sleutel = mld.pop("sleutel_extern", None)
    extmon_sleutel = mld.pop("sleutel_extmonteur", None)
    kijk_sleutel = mld.pop("sleutel_kijk", None)
    mld.pop("sheet", None)
    mld.pop("wachtrij", None)
    # Welke melding welke bon werd, zonder de sleutel van de bonnen. Die staat alleen in het TD-deel.
    verwerkt = (data["meta"].get("bonnen") or {}).get("verwerkt", {})
    monteur_bonnen = {k: v for k, v in verwerkt.items() if not v.startswith("SQDM")}
    dagstart = {"meta": {"stand": a.stand, "meldingen": mld, "bonnen": {"verwerkt": verwerkt, "gesloten": gesloten}}, "sqdc": data.get("sqdc", {}), "storingen": data["storingen"], "machines": data["machines"], "pmplan": pm.monteur_deel(data, a.stand), "output": kort_rapport(data.get("output", {}), 14), "zaterdag": data.get("zaterdag", {}), "stops": data.get("stops", [])}
    # Alleen het werkvoorbereidingsdeel kan bonnen openen. Het TD-deel krijgt de regels zonder bestanden en sleutel.
    wv = copy.deepcopy(td)
    # RCA analyse: de feiten en het effect van een maatregel kijken verder terug dan het RCA-signaal.
    wv["output"] = kort_rapport(data.get("output"), 120)
    wv["prodmachines"] = prod_machines(data)  # productie (pilot): voor Verbeteren op de pagina Diensten
    td.pop("rca", None)  # RCA analyse is voor werkvoorbereider en kijkinlog
    td.pop("prod_excel", None)  # productie (pilot): de diensten uit de Excel-dienstrapporten staan alleen op de pagina Diensten
    mld.pop("sleutel_wv", None)
    td["meta"].pop("actielijst", None)
    td["meta"].pop("levbestand", None)  # met inkoopbedragen, alleen voor de werkvoorbereider
    td["meta"].pop("gezien", None)  # Te doen is alleen voor de werkvoorbereider
    td["meta"].pop("menu", None)  # de eigen indeling van werkvoorbereider en kijkinlog
    td["meta"]["bonnen"] = {"verwerkt": verwerkt, "gesloten": gesloten}
    for r in td.get("cm", []):
        r.pop("bon", None)
    boxes = [box(td, pub["sleutel"])]
    # Werkvoorbereider en kijkinlog lezen hetzelfde grote deel, anders wordt de pagina een derde zwaarder.
    # Per inlog verschillen alleen de sleutels: de kijksleutel kan in Apps Script alleen lezen.
    wv_meld = wv["meta"].pop("meldingen", None)
    deel_sleutel = b64(secrets.token_bytes(32))
    deel = box(wv, deel_sleutel)
    if pub.get("sleutel_wv"):
        # Met de sleutel van de gedeelde monteurinlog opent de werkvoorbereider de monteursapp in zijn eigen menu (pagina Monteursapp).
        boxes.append(box(dict({"deel": deel_sleutel, "meldingen": wv_meld}, **({"app": pub["sleutel_monteur"]} if pub.get("sleutel_monteur") else {}), **({"appextern": pub["sleutel_extern"]} if pub.get("sleutel_extern") and extern_sleutel else {}), **({"appextmon": pub["extern_monteurs"]} if pub.get("extern_monteurs") and extmon_sleutel else {})), pub["sleutel_wv"]))
    if pub.get("sleutel_kijk"):
        boxes.append(box({"deel": deel_sleutel, "niveau": "kijk", "meldingen": {"url": mld.get("url"), "sleutel": kijk_sleutel}}, pub["sleutel_kijk"]))
    if pub.get("sleutel_dagstart"):
        boxes.append(box(dagstart, pub["sleutel_dagstart"]))
    if pub.get("sleutel_melden"):
        # Alleen het webadres en de meldsleutel: geen enkele lijst.
        boxes.append(box({"niveau": "melden", "meta": {"meldingen": {"url": mld.get("url"), "sleutel": meld_sleutel}}}, pub["sleutel_melden"]))
    # Storing melden en het dienstrapport, plus de machinenamen, de PM-bonnen en de bonnen die de werkvoorbereider heeft ingepland. Geen bonbestanden.
    # De externe ploeg op zaterdag: de bonnen van de eerstvolgende zaterdag. Hun kopieën van de bon delen ze met de monteurs.
    ext = extern_deel(data, a.stand)
    kopie = opname_kopieen(data, {b["nr"] for b in ext["bonnen"]} if ext and pub.get("sleutel_extern") and extern_sleutel else ())
    monteur_deel = {"niveau": "monteur", "rooster": rooster_deel(data, a.stand), "machines": data["machines"], "pmplan": pm.monteur_deel(data, a.stand), "weekbonnen": weekbonnen(data, a.stand, kopie), "olbonnen": olbonnen(data, a.stand), "meta": {"meldingen": {"url": mld.get("url"), "sleutel": monteur_sleutel, "sleutel_pm": pm_sleutel}, "bonnen": {"verwerkt": monteur_bonnen, "gesloten": gesloten}}}
    if pub.get("sleutel_monteur"):
        boxes.append(box(monteur_deel, pub["sleutel_monteur"]))
    for wie, sleutel in (pub.get("monteurs") or {}).items():
        tekst = (data["meta"].get("monteur_tekst") or {}).get(wie)
        boxes.append(box(dict(monteur_deel, naam=wie, **({"tekst": tekst} if tekst else {})), sleutel))
    if pub.get("sleutel_output"):
        # Alleen het webadres en de outputsleutel: geen enkele lijst.
        boxes.append(box({"niveau": "output", "meta": {"meldingen": {"url": mld.get("url"), "sleutel": output_sleutel}}}, pub["sleutel_output"]))
    if pub.get("sleutel_pm"):
        # Alleen de PM-bonnen en een sleutel die niets anders kan dan die bonnen afmelden.
        boxes.append(box({"niveau": "pm", "naam": data["meta"].get("pm_monteur") or "Monteur", "pmplan": pm.monteur_deel(data, a.stand), "meta": {"meldingen": {"url": mld.get("url"), "sleutel": pm_sleutel}}}, pub["sleutel_pm"]))
    if pub.get("sleutel_extern") and extern_sleutel:
        # Alleen de zaterdag en een sleutel die niets anders kan dan die bonnen afmelden. Geen andere lijsten, namen of prijzen.
        for b in (ext or {}).get("bonnen", []):
            if b["nr"] in kopie:
                b["kopie"] = kopie[b["nr"]]
        boxes.append(box({"niveau": "extern", "zat": ext, "meta": {"stand": a.stand, "meldingen": {"url": mld.get("url"), "sleutel": extern_sleutel}}}, pub["sleutel_extern"]))
        # Monteur 1 tot en met 12: dezelfde zaterdag, de app toont alleen wat de teamleider hem toewees. Hun sleutel kan alleen eigen werk klaarzetten.
        for nr, sleutel in sorted((pub.get("extern_monteurs") or {}).items()) if extmon_sleutel else []:
            boxes.append(box({"niveau": "extern", "rol": "monteur", "mnr": nr, "zat": ext, "meta": {"stand": a.stand, "meldingen": {"url": mld.get("url"), "sleutel": extmon_sleutel}}}, sleutel))
    if pub.get("sleutel_productie") and productie_sleutel:
        # Productie-app (pilot): de machines uit het dienstrapport en de planning. Geen andere lijsten; de sleutel kan alleen het tabblad Productie lezen en schrijven.
        boxes.append(box({"niveau": "productie", "machines": prod_machines(data), "plan": prod_plan(data, a.stand), "meta": {"stand": a.stand, "meldingen": {"url": mld.get("url"), "sleutel": productie_sleutel}}}, pub["sleutel_productie"]))
    inhoud = json.dumps({"iter": pub["iter"], "salt": pub["salt"], "boxes": boxes, "deel": deel}, separators=(",", ":"))
    Path(a.public).write_text(HEAD + fill(tpl, "enc", inhoud) + FOOT, "utf-8")
    print({k: len(v) for k, v in data.items() if isinstance(v, list)})


def dag_van(t):
    try:
        return datetime.datetime.strptime(t, "%d-%m-%Y").date()
    except ValueError:
        return datetime.date(2000, 1, 1)


def extern_zaterdag(data, stand):
    """De eerstvolgende zaterdag in de planning, vanaf vandaag: de externe ploeg ziet hem de hele week."""
    nu = datetime.datetime.strptime(stand, "%d-%m-%Y").date()
    dag = lambda z: datetime.datetime.strptime(z["datum"], "%d-%m-%Y").date()
    l = [z for z in [data.get("zaterdag") or {}] + list(data.get("stops") or []) if z.get("datum") and dag(z) >= nu and dag(z).weekday() == 5]
    return min(l, key=dag) if l else None


def extern_deel(data, stand):
    """Wat de externe ploeg van die zaterdag ziet: per bon de velden voor de kaart en het venster, de veiligheid en extra instructies,
    en wat hij al afmeldde (cm[].extern). Geen uitvoerders, opmerkingen of namen van de eigen mensen."""
    z = extern_zaterdag(data, stand)
    if not z:
        return None
    cm = {r.get("nr"): r for r in data.get("cm", [])}
    bonnen = []
    for deel in ("correctief", "preventief"):
        for r in z.get(deel) or []:
            c = cm.get(r.get("nr"))
            if not c or c.get("status") == "Vervallen" or (c.get("status") in GESLOTEN and not c.get("extern")):
                continue
            bonnen.append({"nr": c["nr"], "deel": deel, "prio": r.get("prio") or c.get("prio"), "omschrijving": c.get("omschrijving") or r.get("werkzaamheid"),
                           "lijn": c.get("lijn"), "machine": c.get("machine"), "status": c.get("status"), "veilig": c.get("veilig") or [], "extra": c.get("extra") or [],
                           "extern": [{k: v for k, v in x.items() if k in ("status", "uitvoerder", "uren", "teamleider", "tijd")} for x in c.get("extern") or []]})
    # Deels uitgevoerd en Onderdeel bestellen halen de bon van het plan. Wat de ploeg deze week afmeldde, blijft hij zien.
    al, zd = {b["nr"] for b in bonnen}, dag_van(z["datum"])
    for c in data.get("cm", []):
        x = (c.get("extern") or [None])[-1]
        if x and c["nr"] not in al and zd - datetime.timedelta(days=7) < dag_van(str(x.get("tijd"))[:10]) <= zd:
            bonnen.append({"nr": c["nr"], "deel": "correctief", "prio": c.get("prio"), "omschrijving": c.get("omschrijving"), "lijn": c.get("lijn"), "machine": c.get("machine"),
                           "status": c.get("status"), "veilig": c.get("veilig") or [], "extra": c.get("extra") or [],
                           "extern": [{k: v for k, v in y.items() if k in ("status", "uitvoerder", "uren", "teamleider", "tijd")} for y in c.get("extern") or []]})
    # De PM-taken van die zaterdag: elke taak apart, met de controlepunten. Aftekenen in de PM-registratie doet de werkvoorbereider na zijn akkoord.
    pp = data.get("pmplan") or {}
    for b in pp.get("bonnen") or []:
        if b.get("datum") != z["datum"]:
            continue
        for t in b.get("taken") or []:
            x = (pp.get("taken") or {}).get(t) or {}
            bonnen.append({"nr": t, "pm": True, "pmbon": b["nr"], "alle": list(b.get("taken") or []), "deel": "preventief", "prio": 1, "omschrijving": x.get("taak") or t,
                           "lijn": b.get("lijn"), "machine": b.get("lijndeel"), "onderdeel": x.get("onderdeel") or "", "frequentie": x.get("frequentie") or "",
                           "uit": bool(b.get("uit")), "punten": x.get("punten") or [{"o": "", "p": [x.get("taak") or t]}], "veilig": [], "extra": []})
    return {"datum": z["datum"], "lijn": z.get("lijn") or "", "letop": z.get("letop") or "", "bonnen": bonnen}


def rooster_deel(data, stand):
    """Het rooster voor de monteursapp: de mensen en de dagen van twee weken terug tot acht weken vooruit."""
    r = data.get("rooster") or {}
    nu = datetime.datetime.strptime(stand, "%d-%m-%Y")
    van, tot = nu - datetime.timedelta(days=14), nu + datetime.timedelta(days=56)
    return {"mensen": r.get("mensen") or [], "diensten": r.get("diensten") or [], "dagen": {d: v for d, v in (r.get("dagen") or {}).items() if van <= datetime.datetime.strptime(d, "%d-%m-%Y") <= tot}}


def weekbonnen(data, stand, kopie):
    """De aangevinkte bonnen voor de monteurs: alleen de velden voor de kaart. Een afgemelde bon blijft twee weken bij Afgemeld staan.
    Een open bon heeft de kopie van de originele bon, een opnamebon ook de onderdelen die nog opgenomen moeten worden.
    Staat de bon in de onderhoudsplanning, dan krijgt hij de dag mee (dag): de monteur ziet wanneer hij gepland is."""
    grens = datetime.datetime.strptime(stand, "%d-%m-%Y") - datetime.timedelta(days=14)
    plan_dag = {r.get("nr"): z.get("datum") for z in [data.get("zaterdag") or {}] + list(data.get("stops") or []) if z.get("datum") for r in (z.get("correctief") or []) + (z.get("preventief") or [])}

    def dag(v):
        try:
            return datetime.datetime.strptime(str(v)[:10], "%d-%m-%Y")
        except ValueError:
            return None

    def zicht(r):
        if r.get("status") not in GESLOTEN:
            return True
        d = dag(r.get("uitgevoerd_op"))
        return r.get("status") in ("Uitgevoerd", "Gereed") and d is not None and d >= grens

    uit = []
    for r in data.get("cm", []):
        o = r.get("opname") or {}
        klaar = o.get("klaar") and (dag(o.get("tijd")) or grens) >= grens
        aan = r.get("week") and zicht(r)
        if not (aan or klaar):
            continue
        x = {k: r.get(k) for k in ("nr", "omschrijving", "lijn", "machine", "onderdelen", "uitvoeren", "prio", "status", "uitgevoerd_op", "opdracht")}
        if plan_dag.get(r["nr"]):
            x["dag"] = plan_dag[r["nr"]]
        # Eerder in de app dan op de planning (appdag): tot en met die dag staat de bon daar bij de monteurs, daarna weer op de dag van zijn plan.
        if r.get("appdag") and dag(r["appdag"]) and dag(r["appdag"]) >= datetime.datetime.strptime(stand, "%d-%m-%Y"):
            x["dag"] = r["appdag"]
        if aan and r.get("weeksoort") == "opname":
            x["soort"] = "opname"
            al = {y.get("onderdeel"): y.get("spec") for y in o.get("regels") or []}  # wat bij Deels uitgevoerd al is ingevuld
            x["regels"] = [{**{k: b.get(k) for k in ("id", "onderdeel", "specificatie", "aantal", "toelichting")}, "spec": al.get(b.get("onderdeel"))} for b in data.get("bestellijst", []) if b.get("cm") == r["nr"] and b.get("groep") not in ("Binnen", "Besteld")]
        elif not aan:
            x.update(soort="opname", klaar=True, af={k: o.get(k) for k in ("door", "tijd", "tekst")})
        if aan and r["nr"] in kopie:
            x["bon"] = kopie[r["nr"]]
        uit.append(x)
    return uit


def ol_norm(t):
    return re.sub(r"[^a-z0-9]+", " ", str(t or "").lower()).strip()


def ol_pm(data, r):
    """De PM-taken van de machine van een opnamelijst: zelfde lijn en het lijndeel past op de machine."""
    m = ol_norm(r.get("machine"))
    return [p for p in data.get("pm", []) if p.get("lijn") == r.get("lijn") and m and (ol_norm(p.get("lijndeel")) == m or m.startswith(ol_norm(p.get("lijndeel"))) or ol_norm(p.get("lijndeel")).startswith(m))]


def olbonnen(data, stand):
    """Opnamelijsten voor de monteursapp: elke lijst die nog open staat, met de onderdelen en PM-punten van die machine al ingevuld.
    Wat de werkvoorbereider inplande heeft een dag (dag). Wat al is ingevuld staat in de Sheet (tabblad Opnamelijst) en niet hier.
    Een lijst die in de app is afgemeld blijft twee weken bij Afgemeld staan; een lijst die op papier is opgenomen staat er niet in."""
    grens = datetime.datetime.strptime(stand, "%d-%m-%Y") - datetime.timedelta(days=14)
    uit = []
    for r in data.get("opnamelijsten", []):
        d = r.get("digitaal") or {}
        try:
            recent = datetime.datetime.strptime(str(d.get("tijd"))[:10], "%d-%m-%Y") >= grens
        except ValueError:
            recent = False
        if d and not recent or not d and (r.get("opname_gedaan") or r.get("uitgewerkt")) and not r.get("plan"):
            continue
        x = {k: r.get(k) for k in ("ol", "lijn", "machine", "pm_code")}
        if d:
            x["af"] = {"door": d.get("door"), "tijd": d.get("tijd")}
        else:
            x["dag"] = (r.get("plan") or {}).get("dag")
            x["plantijd"] = (r.get("plan") or {}).get("tijd")
            taken = ol_pm(data, r)
            x["comps"] = list(dict.fromkeys(p.get("onderdeel") for p in taken if p.get("onderdeel")))[:30]
            x["pm"] = [{"id": p["id"], "taak": p.get("taak")} for p in taken][:40]
        uit.append(x)
    return uit


ap = argparse.ArgumentParser()
sub = ap.add_subparsers(dest="cmd", required=True)
x = sub.add_parser("extract"); x.add_argument("html"); x.add_argument("site"); x.set_defaults(fn=extract)
x = sub.add_parser("setkey"); x.add_argument("site"); x.add_argument("--password", required=True); x.add_argument("--niveau", choices=["td", "dagstart", "melden", "monteur", "wv", "kijk", "output", "pm", "productie", "extern", "externmonteur"], default="td"); x.add_argument("--naam"); x.set_defaults(fn=setkey)
x = sub.add_parser("build"); x.add_argument("site"); x.add_argument("--stand", required=True); x.add_argument("--plain", required=True); x.add_argument("--public", required=True); x.set_defaults(fn=build)
a = ap.parse_args()
a.fn(a)
