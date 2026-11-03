#!/usr/bin/env python3
"""Bouwt de TD-site uit één gegevensbestand (site.json).

De gegevens staan NIET in deze repository. Ze staan leesbaar in de privépagina
bij Claude en versleuteld in index.html. Zie CLAUDE.md voor de werkwijze.

  site.py extract <privepagina.html> <site.json>
  site.py setkey  <site.json> --password "..." [--niveau td|dagstart]
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
    """Zet het wachtwoord voor een niveau: td (alles) of dagstart (alleen de dagstartpagina's)."""
    from cryptography.hazmat.primitives.hashes import SHA256
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    p = Path(a.site)
    data = json.loads(p.read_text("utf-8"))
    pub = data["meta"].setdefault("publiek", {"iter": ITER, "salt": b64(secrets.token_bytes(16))})
    salt = base64.b64decode(pub["salt"])
    key = PBKDF2HMAC(algorithm=SHA256(), length=32, salt=salt, iterations=pub["iter"]).derive(a.password.encode("utf-8"))
    pub["sleutel" if a.niveau == "td" else "sleutel_dagstart"] = b64(key)
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


def sqd_auto(data):
    """Kengetallen in de S-, Q- en D-vakken, berekend uit de bestaande lijsten."""
    open_nrs = {r["nr"] for r in data.get("cm", []) if r.get("status") not in GESLOTEN}

    def tel(veld):
        nrs = set()
        for m in data.get("priolijst", []):
            if m.get(veld) == 3:
                nrs |= set(m.get("open_cm") or [])
        return len(nrs & open_nrs)

    st = data.get("storingen", [])
    z = data.get("zaterdag", {})
    return {
        "S": [{"label": "Open bonnen op machines met hoog veiligheidsrisico", "waarde": tel("score_veiligheid")}],
        "Q": [{"label": "Open bonnen op machines met hoog voedselveiligheidsrisico", "waarde": tel("score_voedselveiligheid")}],
        "D": [
            {"label": "Lopende storingen", "waarde": len(st)},
            {"label": "Daarvan prio 1", "waarde": sum(1 for x in st if x.get("prio") == 1)},
            {"label": "Ingepland komende zaterdag", "waarde": len(z.get("correctief", [])) + len(z.get("preventief", []))},
        ],
    }


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
    data.setdefault("sqdc", {})["auto"] = sqd_auto(data)
    tpl = (TOOLS / "template.html").read_text("utf-8")
    Path(a.plain).write_text(fill(tpl, "plain", json.dumps(data, ensure_ascii=False, separators=(",", ":"))), "utf-8")

    td = copy.deepcopy(data)
    pub = td["meta"].pop("publiek")
    dagstart = {"meta": {"stand": a.stand, "meldingen": td["meta"].get("meldingen")}, "sqdc": data.get("sqdc", {}), "storingen": data["storingen"], "output": data.get("output", {}), "zaterdag": data.get("zaterdag", {})}
    boxes = [box(td, pub["sleutel"])]
    if pub.get("sleutel_dagstart"):
        boxes.append(box(dagstart, pub["sleutel_dagstart"]))
    inhoud = json.dumps({"iter": pub["iter"], "salt": pub["salt"], "boxes": boxes}, separators=(",", ":"))
    Path(a.public).write_text(HEAD + fill(tpl, "enc", inhoud) + FOOT, "utf-8")
    print({k: len(v) for k, v in data.items() if isinstance(v, list)})


ap = argparse.ArgumentParser()
sub = ap.add_subparsers(dest="cmd", required=True)
x = sub.add_parser("extract"); x.add_argument("html"); x.add_argument("site"); x.set_defaults(fn=extract)
x = sub.add_parser("setkey"); x.add_argument("site"); x.add_argument("--password", required=True); x.add_argument("--niveau", choices=["td", "dagstart"], default="td"); x.set_defaults(fn=setkey)
x = sub.add_parser("build"); x.add_argument("site"); x.add_argument("--stand", required=True); x.add_argument("--plain", required=True); x.add_argument("--public", required=True); x.set_defaults(fn=build)
a = ap.parse_args()
a.fn(a)
