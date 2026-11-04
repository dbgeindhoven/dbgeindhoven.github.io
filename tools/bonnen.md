# Bonnen uit meldingen

De geplande taak "TD Hub bonnen" maakt van meldingen echte CM-bonnen in het format F.95.602 Werkbon TD. Dit is de werkwijze. Deze repository is openbaar: zet hier nooit een leesbare bon, een foto, een naam of het Word-template neer.

## Welke meldingen een bon worden
- **Productiemelding:** krijgt bij binnenkomst de code `SQDM-n` en wordt meteen een bon met hetzelfde nummer. Is er geen bon nodig, dan haalt de dagstart of TD bij de opvolging het vinkje "Technische dienst nodig: maak een CM-bon" weg voordat de taak draait. Een productiemelding heeft meestal geen lijn en machine: haal die uit de tekst en de foto, of zet `n.t.b.` op de bon.
- **Actie uit het ochtendoverleg:** is een productiemelding met melder `Ochtendoverleg`. In `oplossing` staat de afgesproken actie met de laatste stand, dus nog niet wat er is gedaan. Gebruik die tekst voor de stappen. Regels die met `[x] ` beginnen zijn al gedaan: neem die niet op als stap. `actiehouder` en `datum` komen uit de actielijst.
- **Monteurstoring:** wordt altijd een bon, met het eerstvolgende CM-nummer.
  - Vervolg Gereed: de bon komt direct op Uitgevoerd.
  - Vervolg Onderdeel bestellen: de bon blijft Open en krijgt een regel op de bestellijst.
  - Vervolg Plannen voor onderhoudstop: de bon blijft Open tot de werkvoorbereider hem inplant.
  - Vervolg Overdragen aan volgende dienst: de bon blijft Open. `oplossing` is dan wat er al is gedaan en mag leeg zijn.

Apps Script zet elke melding die een bon moet worden als tekstbestand `bon-<id>.txt` in de Drive-map "TD Hub wachtrij" (`meta.meldingen.wachtrij`). De taak draait elk uur. Een bestand verdwijnt pas uit die map als de bon helemaal klaar is. Mislukt een run, dan pakt de volgende run het opnieuw op.

Er loopt altijd maar één run tegelijk. Daarvoor staat tijdens een run het bestand `bezig.txt` in dezelfde map.

## Status en verwijderen vanaf de site
De werkvoorbereider kan op de site de status van een bon aanpassen en een melding met de bon verwijderen. Apps Script zet dat als `status-<nr>.txt` in dezelfde map, met `nr`, `status`, `rij`, `tijd` en `door`. Status `Verwijderd` betekent: de bon moet helemaal weg. De site toont zo'n bestand meteen aan iedereen. Daarom blijft het staan tot de wijziging in het overzicht zit en gepubliceerd is.

Op de pagina Zaterdagwerk past de werkvoorbereider de prio en uitvoerder aan en haalt hij regels van de lijst. Dat komt in hetzelfde bestand, in `rij.zat`: `datum`, `prio`, `uitvoerder` en eventueel `weg: true`. `bonnen.py wijzig` zet dit in `zaterdag` en de prio op de bon. Bij `weg` blijft de bon bestaan: alleen `uitvoeren` wordt leeg en Gepland wordt Open.

## Stappen
Werk in een lege map `/tmp/bonwerk`. Stop bij een fout voordat je iets uit de wachtrij haalt, gooi `bezig.txt` weg en meld wat er misging.

0. **Slot.** Staat `bezig.txt` in de wachtrijmap en is dat bestand jonger dan 30 minuten, stop dan meteen. Een oudere gooi je weg. Maak daarna zelf `bezig.txt` in de wachtrijmap met `create_file`.

1. **Gegevens.** Doe stap 1 en 2 uit `CLAUDE.md`, zodat `/tmp/site.json` er staat.
2. **Wachtrij.** Zoek met `search_files` op `parentId = '<wachtrij>' and trashed = false`. Lees elk bestand dat met `bon-` begint met `read_file_content`. Zet de inhoud als lijst in `/tmp/bonwerk/werk.json`, per regel aangevuld met `"drive_id"` (het id van het wachtrijbestand). Neem de tekst letterlijk over, zonder de backslashes die `read_file_content` voor tekens als `_` zet. Doe hetzelfde met elk bestand dat met `status-` begint, maar dan in `/tmp/bonwerk/wijzig.json`. Staan er geen `bon-`-bestanden, sla dan stap 3 tot en met 6 en 8 over.
3. **Template.** Bestaat `bonnen/template.bin` niet, zoek dan in Drive naar Word-bestanden met `F.95.602`, `F_95_602` of `Werkbon` in de titel. Het juiste bestand is leeg, heeft versiedatum 28-09-2026 en bevat de stap "Stop de machine". `Werkbon_TD_zaterdagwerk.docx` is een oude versie en telt niet. Vind je het niet, stop dan en vraag erom. Laat de wachtrij staan. Vind je het wel, download het met `download_file_content`. Dat resultaat wordt op schijf bewaard als JSON: decodeer `content` met Python naar `/tmp/bonwerk/template.docx` en draai `python3 tools/bonnen.py template /tmp/site.json /tmp/bonwerk/template.docx`.
4. **Nummers.** Lees `/preferences.md` uit het geheugen en zoek het hoogste CM-nummer dat daar staat. Handmatig gemaakte bonnen staan daar eerder dan in het overzicht. Draai `python3 tools/bonnen.py nummer /tmp/site.json /tmp/bonwerk --laatste-cm <dat nummer>`.
5. **Tekst.** Schrijf voor elke regel zonder `overslaan` het bestand `/tmp/bonwerk/<nr>.json` (zie hieronder). Staat er een `foto` in de melding, download die dan met `download_file_content`, decodeer `content` naar `/tmp/bonwerk/<nr>.jpg` en bekijk hem met Read. Komt het resultaat niet als bestand maar in het gesprek terug, sla de foto dan over en vermeld dat in `foto_tekst`.
6. **Bonnen maken.** `python3 tools/bonnen.py maak /tmp/site.json /tmp/bonwerk`. Elke bon moet op 1 pagina passen. Bekijk elke PDF als afbeelding (`pdftoppm -r 70 -png`). Maak de tekst korter als het niet past.
7. **Vastleggen.** Zijn er bonnen gemaakt, draai dan `python3 tools/bonnen.py registreer /tmp/site.json /tmp/bonwerk`. Bestaat `wijzig.json`, draai dan `python3 tools/bonnen.py wijzig /tmp/site.json /tmp/bonwerk`. Draai daarna altijd `python3 tools/bonnen.py zaterdag /tmp/site.json /tmp/bonwerk/zat`: dat zet prio, uitvoerder en datum op de bonnen van de zaterdaglijst en maakt de PDF om te printen opnieuw als er iets veranderde. Bouw daarna met stap 4 uit `CLAUDE.md`. Commit en push `index.html` en `bonnen/`, ook de bestanden die `wijzig` heeft weggehaald. Publiceer dan pas `/tmp/artifact.html` (stap 5). Is de push geweigerd, doe dan `git pull --rebase`, bouw opnieuw en push nog een keer.
8. **Nummers bijhouden.** Zijn er CM-nummers uitgegeven, werk dan de regel Werkbonnummering in `/preferences.md` bij op dezelfde manier als de andere nummers, zodat andere chats doortellen.
9. **Wachtrij leegmaken.** Gooi elk verwerkt wachtrijbestand weg met `trash_file`, ook de regels met `overslaan` en de `status-`-bestanden. Zoek daarna opnieuw in de wachtrijmap. Zijn er nieuwe `bon-`- of `status-`-bestanden binnengekomen, ga dan verder vanaf stap 2 met dezelfde `/tmp/site.json` en een lege `/tmp/bonwerk`. Gooi `bezig.txt` pas weg als die er niet meer zijn.
10. **Melden.** Stuur de Word-bestanden en PDF's met `SendUserFile` (status proactive). Noem per bon het nummer, de machine en wat de werkvoorbereider moet nakijken. Alleen statuswijzigingen of verwijderde bonnen hoef je niet te melden.

## Tekst van een bon
`<nr>.json` heeft deze velden. Alles in het Nederlands, kort en feitelijk.

| Veld | Inhoud |
|---|---|
| `naam` | Bestandsnaam zonder extensie, bijvoorbeeld `SQDM-4_ketting_koelbaan_L2` |
| `kort` | Regel voor het CM-overzicht, zonder "Correctief" |
| `omschrijving` | Hooguit 80 tekens. Monteurstoring: `Correctief – ` plus wat er moet gebeuren. Productiemelding: `SQD – ` plus wat er moet gebeuren |
| `werkbon_nr` | Het nummer uit `werk.json` |
| `uitvoeren_op` | De datum uit de melding, anders `In overleg`. Onderhoudstop: `Eerstvolgende onderhoudstop`. Overdragen: `Volgende dienst`. Gereed: `Uitgevoerd op DD-MM-JJJJ` |
| `lijn_machine` | `Lijn 2 / Koelbaan`. Onbekend: `n.t.b. – ` plus wat wel bekend is |
| `melder` | `Naam (DD-MM-JJJJ)` |
| `installatie` | Het machinedeel |
| `afdeling` | `Productie` of `TD` |
| `uitvoerder` | Actiehouder, of de monteur bij een gereedgemelde storing. Anders weglaten |
| `onderdelen` | Wat de melding noemt, anders `Evt. ` plus wat logisch is. Geen typenummers verzinnen |
| `stappen` | 3 tot 6 korte taakstappen |
| `let_op` | Eén regel over het specifieke risico. Weglaten als er geen is |
| `opmerking` | Hooguit 4 regels. Eerste regel: de melding met naam en tijd. Daarna invulvelden met `☐` |
| `foto` | Pad naar de foto in `/tmp/bonwerk` |
| `foto_bijschrift` | Wat er op de foto staat. Een monteur kan een foto van de storing en van de oplossing toevoegen; die staan met een label op één afbeelding |
| `foto_tekst` | Alleen zonder foto: `Geen foto bij melding – foto vóór/na toevoegen.` |

Regels voor de inhoud:
- De vaste stappen staan al in het template: stoppen en vergrendelen met LMRA, werkplek schoon, LOTOTO opheffen, formulier invullen en afmelden. Herhaal die niet in `stappen`.
- Begin met beoordelen als de oorzaak niet vaststaat. Verzin geen oorzaak, maat, type of instelling.
- Werk aan elektra: spanningsloos maken en meten, alleen door een bevoegd persoon.
- Benoem bij `let_op` wat voor deze klus telt: vreemde voorwerpen boven product, productcontactdelen en extra reiniging, werken op hoogte, onbekende leidingen eerst identificeren.
- Gereedgemelde storing: zet in `stappen` wat de monteur heeft gedaan, in zijn eigen woorden.
- Een automatische bon is een concept. De werkvoorbereider kijkt hem na voordat hij wordt uitgevoerd.

## Aan en uit
De taak draait alleen zinvol als het webadres in `meta.meldingen.url` staat. Zonder `bon-`- of `status-`-bestanden in de wachtrij stopt een run direct.
