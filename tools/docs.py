#!/usr/bin/env python3
"""Machinedocumentatie: documenten per machine, versleuteld in de tak documenten van deze repository.

  docs.py voegtoe <site.json> <map> <clone van de tak documenten>

<map> is ingedeeld als <machine>/<soort>/<bestand>. Bestanden met dezelfde naam en een andere extensie
worden één document, bijvoorbeeld een PM-bon als Word en PDF. Zie CLAUDE.md.
"""
import argparse
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SOORTEN = ("Storingsinstructies", "PM-bonnen", "Onderhoudsschema's", "Bestellijsten", "PM-taken", "Werkbonnen", "Overzichten")
EXTENSIES = (".pdf", ".docx", ".xlsx", ".jpg")
MAX_MB = 90  # GitHub weigert bestanden vanaf 100 MB


def voegtoe(a):
    site = Path(a.site)
    data = json.loads(site.read_text("utf-8"))
    doel = Path(a.doel)
    if "refs/heads/documenten" not in (doel / ".git" / "HEAD").read_text():
        raise SystemExit("Dit is niet de clone van de tak documenten.")
    d = data["meta"].setdefault("docs", {"lijst": []})
    d.setdefault("sleutel", base64.b64encode(os.urandom(32)).decode())
    sleutel = base64.b64decode(d["sleutel"])
    lijst = {(r["machine"], r["soort"], r["titel"]): r for r in d["lijst"]}
    bestanden = sorted(p for p in Path(a.map).glob("*/*/*") if p.is_file())
    for p in bestanden:
        if p.parent.name not in SOORTEN or p.suffix.lower() not in EXTENSIES:
            raise SystemExit("Hoort niet in de indeling: %s" % p)
        if p.stat().st_size > MAX_MB * 1024 * 1024:
            raise SystemExit("Te groot voor GitHub: %s" % p)
    nieuw = 0
    for p in bestanden:
        inhoud = p.read_bytes()
        # De naam volgt uit de inhoud, dus opnieuw toevoegen maakt geen tweede bestand.
        naam = hmac.new(sleutel, inhoud, hashlib.sha256).hexdigest()[:20] + ".bin"
        if not (doel / naam).exists():
            iv = os.urandom(12)
            (doel / naam).write_bytes(iv + AESGCM(sleutel).encrypt(iv, inhoud, None))
            nieuw += 1
        machine, soort = p.parent.parent.name, p.parent.name
        r = lijst.setdefault((machine, soort, p.stem), {"machine": machine, "soort": soort, "titel": p.stem, "bestanden": {}})
        r["bestanden"][p.suffix.lower()[1:]] = naam
    d["lijst"] = sorted(lijst.values(), key=lambda r: (r["machine"], SOORTEN.index(r["soort"]), r["titel"]))
    site.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    print(len(bestanden), "bestanden nagelopen,", nieuw, "nieuw versleuteld,", len(d["lijst"]), "documenten op de site")


ap = argparse.ArgumentParser()
sub = ap.add_subparsers(dest="cmd", required=True)
x = sub.add_parser("voegtoe")
x.add_argument("site")
x.add_argument("map")
x.add_argument("doel")
x.set_defaults(fn=voegtoe)
args = ap.parse_args()
args.fn(args)
