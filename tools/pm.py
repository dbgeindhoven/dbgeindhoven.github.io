#!/usr/bin/env python3
"""PM-planning: welke preventieve taken op welke dag op een bon komen. site.py en bonnen.py gebruiken dit.

Elk lijndeel heeft een vaste plek in een cyclus van 4 weken: een week en een werkdag. Wekelijkse taken komen
elke week op die werkdag, maandelijkse taken elke 4 weken in die week. Zo komt een maandelijkse taak in elke
kalendermaand minstens één keer aan de beurt. Bonnen tot en met vandaag liggen vast, latere bonnen worden bij
elke bouw opnieuw berekend. Wat is afgetekend staat niet hier maar live in de Sheet (tabblad PM).

Taken uit bedrijf (LOTOTO) kunnen alleen als de lijn stilstaat. Welke lijn wanneer staat in pmplan.uit, per lijn
een begindatum (vanaf) en de weekdag waarop de lijn stilstaat (dag, 6 = zaterdag). Die taken krijgen een eigen
bon met uit = true, op die dag. Ook hier heeft elk lijndeel een vaste week in de cyclus van 4 weken.
"""
import datetime

TOESTAND = "In bedrijf"
FREQ = {"Wekelijks": 1, "2-wekelijks": 2, "Maandelijks": 4}  # om de hoeveel weken
MAX_REGELS = 16  # zoveel regels taakstappen passen op één bon van 1 pagina
MAX_REGELS_UIT = 12  # uit bedrijf: de vaste stappen over stoppen en LOTOTO blijven staan, dus minder ruimte
TEKENS = 56  # tekens op een regel in het vak Werkinstructie
VOORUIT = 42  # dagen vooruit plannen
BEWAAR = 56  # dagen terug bewaren
MONTEUR_VOORUIT = 14  # dagen vooruit in het deel van de monteurs, de site toont er 7
EEN_DAG = datetime.timedelta(days=1)


def dat(s):
    d, m, j = map(int, str(s).split("-"))
    return datetime.date(j, m, d)


def tekst(d):
    return d.strftime("%d-%m-%Y")


def groepen_uit(data):
    """De taken uit bedrijf van de lijnen in pmplan.uit, per lijndeel. De sleutel begint met UIT zodat hij een eigen plek krijgt."""
    lijnen = (data.get("pmplan") or {}).get("uit") or {}
    uit = {}
    for r in data.get("pm", []):
        if r.get("lijn") in lijnen and str(r.get("bedrijfstoestand") or "").startswith("Uit") and r.get("frequentie") in FREQ and not r.get("niet_plannen"):
            uit.setdefault("UIT | " + r["lijn"] + " | " + r["lijndeel"], []).append(r)
    return uit


def verdeel_uit(plan, g):
    """Elk lijndeel uit bedrijf krijgt de week met de minste taken op de stilstanddag van zijn lijn."""
    vak = plan.setdefault("vak", {})
    lijnen = plan.get("uit") or {}
    druk = {}
    for k in sorted(g, key=lambda k: (k in vak and 0 or 1, -len(g[k]), k)):
        lijn = g[k][0]["lijn"]
        dag = int(lijnen[lijn].get("dag") or 6)
        if k not in vak or vak[k].get("dag") != dag:
            def last(w):
                return max(druk.get((lijn, x), 0) + sum(1 for r in g[k] if (x - w) % FREQ[r["frequentie"]] == 0) for x in range(1, 5))
            vak[k] = {"week": min(range(1, 5), key=lambda w: (last(w), druk.get((lijn, w), 0), w)), "dag": dag}
        for r in g[k]:
            for x in range(1, 5):
                if (x - vak[k]["week"]) % FREQ[r["frequentie"]] == 0:
                    druk[(lijn, x)] = druk.get((lijn, x), 0) + 1


def groepen(data):
    """De taken van de planning per lijndeel. Een taak met niet_plannen blijft op de lijst, maar komt niet op een bon."""
    uit = {}
    for r in data.get("pm", []):
        if r.get("bedrijfstoestand") == TOESTAND and r.get("frequentie") in FREQ and not r.get("niet_plannen"):
            uit.setdefault(r["lijn"] + " | " + r["lijndeel"], []).append(r)
    return uit


def verdeel(plan, g):
    """Elk nieuw lijndeel krijgt de rustigste plek. Een bestaande plek blijft staan, zodat bekend blijft wanneer iets aan de beurt is."""
    vak = plan.setdefault("vak", {})
    plekken = [(w, d) for w in range(1, 5) for d in range(1, 6)]
    druk = {p: 0 for p in plekken}

    def erbij(rijen, week, dag):
        uit = {}
        for r in rijen:
            for w in range(1, 5):
                if (w - week) % FREQ[r["frequentie"]] == 0:
                    uit[(w, dag)] = uit.get((w, dag), 0) + 1
        return uit

    def tel(extra):
        for p, n in extra.items():
            druk[p] = druk.get(p, 0) + n

    for k, v in vak.items():
        if k in g:
            tel(erbij(g[k], v["week"], v["dag"]))
    nieuw = sorted((k for k in g if k not in vak), key=lambda k: (-sum(r["frequentie"] == "Wekelijks" for r in g[k]), -len(g[k]), k))
    for k in nieuw:
        def proef(p):
            extra = erbij(g[k], *p)
            weken = {x[0] for x in extra}
            return (max(druk[x] + n for x, n in extra.items()), sum(n for x, n in druk.items() if x[0] in weken), sum(n for x, n in druk.items() if x[1] == p[1]), p)
        p = min(plekken, key=proef)
        vak[k] = {"week": p[0], "dag": p[1]}
        tel(erbij(g[k], *p))


def stap(r):
    """De regel op de bon. Operatortaken staan voorlopig op de TD-bon om te inventariseren."""
    return "%s%s (%s)" % (r["taak"].rstrip(". "), " [Operator]" if r.get("discipline") == "Operator" else "", r["id"])


def verdeel_over_bonnen(rijen, maximaal=MAX_REGELS):
    uit = [[]]
    regels = 0
    for r in rijen:
        n = (len(stap(r)) - 1) // TEKENS + 1
        if uit[-1] and regels + n > maximaal:
            uit.append([])
            regels = 0
        uit[-1].append(r)
        regels += n
    return uit


def bonnen_op(plan, g, d, uit=None):
    """De bonnen van één dag: één bon per lijndeel. Past het niet op 1 pagina, dan krijgt het lijndeel meer bonnen. Bonnen uit bedrijf tellen door na die van in bedrijf."""
    n = (d - dat(plan["start"])).days
    week, dag = n // 7 % 4 + 1, d.weekday() + 1
    uit = uit if uit is not None else []
    for k in sorted(g):
        v = plan["vak"][k]
        if v["dag"] != dag:
            continue
        volgorde = list(FREQ)
        rijen = sorted((r for r in g[k] if (week - v["week"]) % FREQ[r["frequentie"]] == 0), key=lambda r: (volgorde.index(r["frequentie"]), r["onderdeel"] or "", r["id"]))
        for deel in verdeel_over_bonnen(rijen, MAX_REGELS_UIT if k.startswith("UIT | ") else MAX_REGELS) if rijen else []:
            b = {"nr": "PM-%s-%d" % (d.strftime("%y%m%d"), len(uit) + 1), "datum": tekst(d), "lijn": deel[0]["lijn"], "lijndeel": deel[0]["lijndeel"], "taken": [r["id"] for r in deel]}
            if k.startswith("UIT | "):
                b["uit"] = True
            uit.append(b)
    return uit


def bijwerken(data, vandaag):
    """Legt de bonnen tot en met vandaag vast en berekent de weken daarna. Zonder pmplan gebeurt er niets."""
    plan = data.get("pmplan")
    if not plan:
        return
    nu, start = dat(vandaag), dat(plan["start"])
    g = groepen(data)
    verdeel(plan, g)
    gu = groepen_uit(data)
    verdeel_uit(plan, gu)
    lijnen = plan.get("uit") or {}
    # Uit bedrijf: alvast vier weken na de begindatum zichtbaar, ook als die verder weg ligt dan normaal.
    eind = max([nu + datetime.timedelta(days=VOORUIT)] + [dat(v["vanaf"]) + datetime.timedelta(days=27) for v in lijnen.values() if v.get("vanaf")])
    tot = dat(plan["vast_tot"]) if plan.get("vast_tot") else start - EEN_DAG
    # Een bon met een registratiebon blijft staan: dat is het bewijs dat het werk is gedaan.
    vast = (data["meta"].get("bonnen") or {}).get("pmreg") or {}
    bonnen, d = [b for b in plan.get("bonnen", []) if dat(b["datum"]) <= tot and (b["nr"] in vast or nu - datetime.timedelta(days=BEWAAR) <= dat(b["datum"]))], tot + EEN_DAG
    while d <= eind:
        if d >= start:
            # Een lijndeel met dag 6 in vak doet ook zijn taken in bedrijf op zaterdag, zoals de oven van lijn 3.
            gdag = g if d.weekday() < 5 else {k: v for k, v in g.items() if plan["vak"][k]["dag"] == 6}
            dagbonnen = bonnen_op(plan, gdag, d) if d.weekday() < 6 and gdag and d <= nu + datetime.timedelta(days=VOORUIT) else []
            gd = {k: v for k, v in gu.items() if lijnen[v[0]["lijn"]].get("vanaf") and d >= dat(lijnen[v[0]["lijn"]]["vanaf"])}
            if gd:
                bonnen_op(plan, gd, d, dagbonnen)
            bonnen += dagbonnen
        d += EEN_DAG
    plan["bonnen"] = bonnen
    if nu > tot:
        plan["vast_tot"] = tekst(nu)
    rijen = {r["id"]: r for r in data.get("pm", [])}
    punten = data.get("pmpunten") or {}
    plan["taken"] = {t: {**{k: (rijen.get(t) or {}).get(k) for k in ("taak", "onderdeel", "frequentie", "discipline", "benodigdheden")}, "punten": punten.get(t)} for b in bonnen for t in b["taken"]}


def monteur_deel(data, vandaag):
    """Alleen wat de monteurs nodig hebben: de bonnen tot twee weken vooruit en de tekst van die taken."""
    plan = data.get("pmplan")
    if not plan:
        return None
    grens = dat(vandaag) + datetime.timedelta(days=MONTEUR_VOORUIT)
    bonnen = [b for b in plan.get("bonnen", []) if dat(vandaag) - datetime.timedelta(days=BEWAAR) <= dat(b["datum"]) <= grens]
    return {"bonnen": bonnen, "taken": {t: plan["taken"][t] for b in bonnen for t in b["taken"]}}
