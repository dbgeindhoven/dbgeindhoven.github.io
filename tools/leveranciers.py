#!/usr/bin/env python3
"""Zet het leveranciersbestand van de techniek in site.json, voor de pagina Leveranciers.

  leveranciers.py <site.json> <leveranciersbestand.xlsx>

De kolommen worden op naam gezocht. Een nieuw bestand vervangt het oude helemaal.
De inkoopbedragen zijn vertrouwelijk: meta.levbestand staat alleen in het werkvoorbereidingsdeel.
"""
import argparse
import datetime
import json
import re
import warnings

import openpyxl

warnings.filterwarnings("ignore")


def schoon(v):
    return " ".join(str(v).replace("\xa0", " ").split()) if v is not None else ""


def bedrag(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return round(v, 2)
    try:
        return round(float(str(v).replace(",", ".")), 2)
    except ValueError:
        return None


def inkoopkop(k):
    """Inkoopspend 2024 FY wordt 2024, Inkoopspend 2025 (t/m 1-10) wordt 2025 t/m 1-10."""
    return " ".join(re.sub(r"Inkoopspend|\bFY\b|[()]", " ", k).split())


def lees(pad):
    ws = openpyxl.load_workbook(pad, data_only=True, read_only=True).worksheets[0]
    kop, lijst = None, []
    for r in ws.iter_rows(values_only=True):
        if kop is None:
            if "Leverancier" in map(schoon, r):
                kop = [schoon(v) for v in r]
                locaties = [k for k in kop if k.startswith("Locatie ")]
                inkoop = [k for k in kop if k.startswith("Inkoopspend")]
            continue
        x = dict(zip(kop, r))
        naam = schoon(x.get("Leverancier"))
        if not naam:
            continue
        cat = schoon(x.get("Categorie"))
        rij = {
            "nr": schoon(x.get("Lev.nr.")), "naam": naam, "categorie": cat[:1].upper() + cat[1:],
            "yopar": schoon(x.get("Yopar leverancier?")).lower() == "ja",
            "locaties": [k[len("Locatie "):] for k in locaties if bedrag(x.get(k))],
            "inkoop": [bedrag(x.get(k)) for k in inkoop], "opmerking": schoon(x.get("Opmerking")),
        }
        lijst.append({k: v for k, v in rij.items() if v not in ("", False)})
    if kop is None:
        raise SystemExit("Geen kolom Leverancier gevonden")
    return {"bron": "Techniek - leveranciersbestand", "stand": datetime.date.today().strftime("%d-%m-%Y"), "inkoop": [inkoopkop(k) for k in inkoop], "lijst": lijst}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("site")
    p.add_argument("xlsx")
    a = p.parse_args()
    data = json.load(open(a.site, encoding="utf-8"))
    data["meta"]["levbestand"] = lees(a.xlsx)
    json.dump(data, open(a.site, "w", encoding="utf-8"), ensure_ascii=False)
    print("Leveranciers:", len(data["meta"]["levbestand"]["lijst"]))


if __name__ == "__main__":
    main()
