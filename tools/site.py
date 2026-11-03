#!/usr/bin/env python3
"""Bouwt de TD-site uit één gegevensbestand (site.json).

De gegevens staan NIET in deze repository. Ze staan leesbaar in de privépagina
bij Claude en versleuteld in index.html. Zie CLAUDE.md voor de werkwijze.

  site.py extract <privepagina.html> <site.json>
  site.py setkey  <site.json> --password "..."
  site.py build   <site.json> --stand DD-MM-JJJJ --plain <uit.html> --public <index.html>
"""
import argparse, base64, copy, json, re, secrets
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ITER = 600_000
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
    from cryptography.hazmat.primitives.hashes import SHA256
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    p = Path(a.site)
    data = json.loads(p.read_text("utf-8"))
    salt = secrets.token_bytes(16)
    key = PBKDF2HMAC(algorithm=SHA256(), length=32, salt=salt, iterations=ITER).derive(a.password.encode("utf-8"))
    data["meta"]["publiek"] = {"iter": ITER, "salt": b64(salt), "sleutel": b64(key)}
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")


def build(a):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    data = json.loads(Path(a.site).read_text("utf-8"))
    data["meta"]["stand"] = a.stand
    for r in data.get("bestellijst", []):
        if not r.get("groep"):
            bestel_groep(r)
    tpl = (TOOLS / "template.html").read_text("utf-8")
    Path(a.plain).write_text(fill(tpl, "plain", json.dumps(data, ensure_ascii=False, separators=(",", ":"))), "utf-8")

    pub = copy.deepcopy(data)
    sleutel = pub["meta"].pop("publiek")
    iv = secrets.token_bytes(12)
    tekst = json.dumps(pub, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ct = AESGCM(base64.b64decode(sleutel["sleutel"])).encrypt(iv, tekst, None)
    box = json.dumps({"iter": sleutel["iter"], "salt": sleutel["salt"], "iv": b64(iv), "ct": b64(ct)}, separators=(",", ":"))
    Path(a.public).write_text(HEAD + fill(tpl, "enc", box) + FOOT, "utf-8")
    print({k: len(v) for k, v in data.items() if isinstance(v, list)})


ap = argparse.ArgumentParser()
sub = ap.add_subparsers(dest="cmd", required=True)
x = sub.add_parser("extract"); x.add_argument("html"); x.add_argument("site"); x.set_defaults(fn=extract)
x = sub.add_parser("setkey"); x.add_argument("site"); x.add_argument("--password", required=True); x.set_defaults(fn=setkey)
x = sub.add_parser("build"); x.add_argument("site"); x.add_argument("--stand", required=True); x.add_argument("--plain", required=True); x.add_argument("--public", required=True); x.set_defaults(fn=build)
a = ap.parse_args()
a.fn(a)
