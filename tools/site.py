#!/usr/bin/env python3
"""Bouwt de TD-site uit één gegevensbestand (site.json).

De gegevens staan NIET in deze repository. Ze staan leesbaar in de privépagina
bij Claude en versleuteld in index.html. Zie CLAUDE.md voor de werkwijze.

  site.py extract <privepagina.html> <site.json>
  site.py setkey  <site.json> --password "..." [--niveau td|dagstart|melden|monteur|wv]
  site.py build   <site.json> --stand DD-MM-JJJJ --plain <uit.html> --public <index.html>
"""
import argparse, base64, copy, json, re, secrets
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

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
    """Zet het wachtwoord voor een niveau: wv (alles plus de bonnen), td (alles), dagstart (dagstartpagina's), melden (alleen het meldformulier), monteur (storing melden en dienstrapport) of output (alleen het outputformulier)."""
    from cryptography.hazmat.primitives.hashes import SHA256
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    p = Path(a.site)
    data = json.loads(p.read_text("utf-8"))
    pub = data["meta"].setdefault("publiek", {"iter": ITER, "salt": b64(secrets.token_bytes(16))})
    salt = base64.b64decode(pub["salt"])
    key = PBKDF2HMAC(algorithm=SHA256(), length=32, salt=salt, iterations=pub["iter"]).derive(a.password.encode("utf-8"))
    pub[{"td": "sleutel", "dagstart": "sleutel_dagstart", "melden": "sleutel_melden", "monteur": "sleutel_monteur", "wv": "sleutel_wv", "output": "sleutel_output"}[a.niveau]] = b64(key)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")


def storingen(data):
    """Lopende storingen: open bonnen uit het CM-overzicht. Gereed verdwijnt vanzelf."""
    besteld = {r.get("cm") for r in data.get("bestellijst", []) if r.get("groep") == "Besteld"}
    uit = []
    for r in data.get("cm", []):
        if r.get("status") in GESLOTEN or not str(r.get("bron") or "").startswith("CM-overzicht"):
            continue
        if r.get("status") == "Gepland":
            st = "Gepland"
        elif r.get("status") == "Besteld" or r.get("nr") in besteld:
            st = "In bestelling"
        else:
            st = "Open"
        uit.append({"nr": r.get("nr"), "storing": r.get("omschrijving"), "lijn": r.get("lijn"), "machine": r.get("machine"),
                    "status": st, "actiehouder": r.get("actiehouder") or r.get("monteur"), "prio": r.get("prio")})
    uit.sort(key=lambda x: (x["prio"] or 9, ["Open", "In bestelling", "Gepland"].index(x["status"]), int(re.search(r"\d+", x["nr"]).group())))
    return uit


def machines(data):
    """Machines per lijn voor het storingsformulier: de opnamelijsten plus meta.machines_extra."""
    uit = {}
    for r in data.get("opnamelijsten", []):
        uit.setdefault(r.get("lijn") or "Overig", []).append(r["machine"])
    for lijn, namen in (data["meta"].get("machines_extra") or {}).items():
        uit.setdefault(lijn, []).extend(n for n in namen if n not in uit.get(lijn, []))
    return uit


def box(tekst, sleutel):
    iv = secrets.token_bytes(12)
    ct = AESGCM(base64.b64decode(sleutel)).encrypt(iv, json.dumps(tekst, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), None)
    return {"iv": b64(iv), "ct": b64(ct)}


def build(a):
    data = json.loads(Path(a.site).read_text("utf-8"))
    data["meta"]["stand"] = a.stand
    for r in data.get("bestellijst", []):
        if not r.get("groep"):
            bestel_groep(r)
    data["storingen"] = storingen(data)
    data.setdefault("sqdc", {}).pop("auto", None)
    data["machines"] = machines(data)
    # Meldingen waarvan de bon is afgesloten, zodat ze uit "Nog open" in het dienstrapport verdwijnen.
    gesloten = [r["melding"] for r in data.get("cm", []) if r.get("melding") and r.get("status") in GESLOTEN]
    data["meta"].setdefault("bonnen", {})["gesloten"] = gesloten
    tpl = (TOOLS / "template.html").read_text("utf-8")
    Path(a.plain).write_text(fill(tpl, "plain", json.dumps(data, ensure_ascii=False, separators=(",", ":"))), "utf-8")

    td = copy.deepcopy(data)
    pub = td["meta"].pop("publiek")
    mld = td["meta"].get("meldingen") or {}
    meld_sleutel = mld.pop("sleutel_melden", None)
    monteur_sleutel = mld.pop("sleutel_monteur", None)
    output_sleutel = mld.pop("sleutel_output", None)
    mld.pop("sheet", None)
    mld.pop("wachtrij", None)
    # Welke melding welke bon werd, zonder de sleutel van de bonnen. Die staat alleen in het TD-deel.
    verwerkt = (data["meta"].get("bonnen") or {}).get("verwerkt", {})
    monteur_bonnen = {k: v for k, v in verwerkt.items() if not v.startswith("SQDM")}
    dagstart = {"meta": {"stand": a.stand, "meldingen": mld, "bonnen": {"verwerkt": verwerkt}}, "sqdc": data.get("sqdc", {}), "storingen": data["storingen"], "output": data.get("output", {}), "zaterdag": data.get("zaterdag", {})}
    # Alleen het werkvoorbereidingsdeel kan bonnen openen. Het TD-deel krijgt de regels zonder bestanden en sleutel.
    wv = copy.deepcopy(td)
    mld.pop("sleutel_wv", None)
    td["meta"].pop("actielijst", None)
    td["meta"]["bonnen"] = {"verwerkt": verwerkt, "gesloten": gesloten}
    for r in td.get("cm", []):
        r.pop("bon", None)
    boxes = [box(td, pub["sleutel"])]
    if pub.get("sleutel_wv"):
        boxes.append(box(wv, pub["sleutel_wv"]))
    if pub.get("sleutel_dagstart"):
        boxes.append(box(dagstart, pub["sleutel_dagstart"]))
    if pub.get("sleutel_melden"):
        # Alleen het webadres en de meldsleutel: geen enkele lijst.
        boxes.append(box({"niveau": "melden", "meta": {"meldingen": {"url": mld.get("url"), "sleutel": meld_sleutel}}}, pub["sleutel_melden"]))
    if pub.get("sleutel_monteur"):
        # Alleen de sleutel voor storing melden en het dienstrapport, plus de machinenamen voor het formulier.
        boxes.append(box({"niveau": "monteur", "machines": data["machines"], "meta": {"meldingen": {"url": mld.get("url"), "sleutel": monteur_sleutel}, "bonnen": {"verwerkt": monteur_bonnen, "gesloten": gesloten}}}, pub["sleutel_monteur"]))
    if pub.get("sleutel_output"):
        # Alleen het webadres en de outputsleutel: geen enkele lijst.
        boxes.append(box({"niveau": "output", "meta": {"meldingen": {"url": mld.get("url"), "sleutel": output_sleutel}}}, pub["sleutel_output"]))
    inhoud = json.dumps({"iter": pub["iter"], "salt": pub["salt"], "boxes": boxes}, separators=(",", ":"))
    Path(a.public).write_text(HEAD + fill(tpl, "enc", inhoud) + FOOT, "utf-8")
    print({k: len(v) for k, v in data.items() if isinstance(v, list)})


ap = argparse.ArgumentParser()
sub = ap.add_subparsers(dest="cmd", required=True)
x = sub.add_parser("extract"); x.add_argument("html"); x.add_argument("site"); x.set_defaults(fn=extract)
x = sub.add_parser("setkey"); x.add_argument("site"); x.add_argument("--password", required=True); x.add_argument("--niveau", choices=["td", "dagstart", "melden", "monteur", "wv", "output"], default="td"); x.set_defaults(fn=setkey)
x = sub.add_parser("build"); x.add_argument("site"); x.add_argument("--stand", required=True); x.add_argument("--plain", required=True); x.add_argument("--public", required=True); x.set_defaults(fn=build)
a = ap.parse_args()
a.fn(a)
