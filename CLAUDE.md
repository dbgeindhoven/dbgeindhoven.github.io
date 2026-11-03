# TD-site DBG Eindhoven

View-only website voor de overzichten van de technische dienst. Publiek adres: https://dbgeindhoven.github.io/

Repository: `dbgeindhoven/dbgeindhoven.github.io`.

## Waar de gegevens staan
- **Leesbaar:** in de privépagina bij Claude: https://claude.ai/artifact/3JPNTaJyRYKhn2m64RygkB. Dit is de bron. Daarin staat ook de sleutel voor de versleuteling (`meta.publiek`).
- **Versleuteld:** in `index.html` in deze repository, en de bonnen en het Word-template in `bonnen/`.
- Deze repository is openbaar. Zet hier nooit leesbare gegevens neer: geen `site.json`, geen `dist/`, geen namen, geen CM-regels. Het wachtwoord hoort hier ook niet.

## Bijwerken vanuit een chat
1. Lees de privépagina met de Artifact-tool (`action: read`). Het resultaat noemt het opgeslagen bestand met de volledige pagina.
2. `python3 tools/site.py extract <dat bestand> /tmp/site.json`
3. Pas `/tmp/site.json` aan met Python. Lijsten: `cm`, `zaterdag`, `bestellijst`, `priolijst`, `opnamelijsten`, `pm`. Toelichting per lijst en de stand per lijst staan in `meta.standen`.
   - `sqdc`: `datum`, `vakken` (S, Q, D; `kleur` is groen, rood of null; `punten` is een lijst teksten) en `directie_acties` (`actie`, `actiehouder`, `datum` als DD-MM-JJJJ of DD-MM-JJJJ UU:MM, `gereed`). Er is bewust geen vak voor Cost.
   - `output`: `datum`, `eenheid`, `lijnen` (`lijn`, `plan`, `output`, `opmerking`).
   - `sqdc.auto` niet met de hand aanpassen: `site.py build` berekent de kengetallen in de vakken.
   - `storingen` niet met de hand aanpassen: `site.py build` maakt die lijst uit de open bonnen van het CM-overzicht. Gepland blijft Gepland, Besteld of een bestelregel op Besteld wordt In bestelling, de rest wordt Open. Gereed verdwijnt. Een veld `actiehouder` op een CM-regel gaat voor op `monteur`.
4. `python3 tools/site.py build /tmp/site.json --stand DD-MM-JJJJ --plain /tmp/artifact.html --public index.html`
5. Publiceer `/tmp/artifact.html` met de Artifact-tool op dezelfde `url`.
6. Commit en push alleen `index.html` en `bonnen/` (en eventueel `tools/`) naar `main`. GitHub Pages publiceert vanaf `main`, map `/`.

Een nieuwe pagina maak je in `tools/template.html`: voeg een scherm toe aan `SCHERM` en aan `P_DAG` of `P_TD`. Dagstartpagina's moeten ook in het dagstartdeel van `build` in `tools/site.py`.

## Meldingen
Een melding bestaat uit melder, foto, probleem en risico (Safety, Quality of Delivery). Op de pagina Meldingen vult de dagstart of TD de opvolging aan en zet een melding desgewenst door naar S, Q of D op het SQD-overzicht (kolom `letter`; leeg betekent nog niet doorgezet). De site is statisch, dus meldingen gaan via een Google Apps Script-webapp (`tools/meldingen.gs`) naar de privé Google Sheet "TD Hub meldingen". De webadres, de sleutel en het Sheet-ID staan in `meta.meldingen` in de privépagina, niet in deze repository. Zonder `url` blijven de knoppen verborgen. Een open melding kleurt de letter rood. Een melding met `bon_nodig` = Ja is bedoeld voor een CM-bon. De Sheet heeft per melding ook `oplossing` en `foto` (Drive-bestand in de privémap "TD Hub foto's"). Directie-acties staan in dezelfde Sheet met letter `DIR`.

## Bonnen uit meldingen
Een productiemelding krijgt bij binnenkomst de code `SQDM-n` (kolom `code` in de Sheet). Vinkt de dagstart of TD "Technische dienst nodig: maak een CM-bon" aan, dan wordt het een echte bon met datzelfde nummer. Een monteurstoring wordt altijd een bon, met het eerstvolgende CM-nummer. In het CM-overzicht staan deze bonnen met `herkomst` (Productie of Monteur) en met `bon`: de versleutelde Word- en PDF-bon. Die zijn alleen te openen op de pagina Bonnen met het eigen wachtwoord van de werkvoorbereider. Welke melding welke bon werd staat in `meta.bonnen.verwerkt`.

De geplande taak "TD Hub bonnen" maakt de bonnen. De werkwijze staat in `tools/bonnen.md`. Staat `meta.meldingen.url` nog leeg, dan heeft de taak geen schema. Zet zodra het webadres is ingevuld het schema aan met `update_trigger`: `CRON_TZ=Europe/Amsterdam 48 6-14/2 * * 1-5`. Pas je `tools/meldingen.gs` aan, stuur dan een nieuwe ingevulde versie van het script; de echte waarden staan in `meta.meldingen`.

## Vijf toegangsniveaus
- **Melden:** alleen het meldformulier. Dit deel bevat geen enkele lijst, en de meldsleutel kan alleen nieuwe meldingen versturen.
- **Monteur:** storing melden en het gedeelde dienstrapport. Dit deel bevat geen lijsten; de monteursleutel leest alleen dienstrapportregels en voegt alleen storingen toe. Dienstrapportregels staan in de Sheet met letter `TD` en status `Rapport`, met `vervolg` Gereed, Onderdeel bestellen of Plannen voor onderhoudstop.
- **Dagstart:** SQD, Meldingen, Lopende storingen, Output per lijn en Zaterdag.
- **TD:** alles, dus ook TD-overzicht, CM-bonnen, Bestellijst, Priolijst, Opnamelijsten, PM-taken en Dienstrapport. Geen bonbestanden: dit deel bevat de sleutel van de bonnen niet.
- **Werkvoorbereider (`wv`):** alles van TD plus de pagina Bonnen, waar de Word- en PDF-bonnen te downloaden zijn. Alleen dit deel bevat `meta.bonnen.sleutel` en `cm[].bon`.
`index.html` bevat per niveau een eigen versleuteld deel. Het dagstart-wachtwoord kan de TD-gegevens niet openen.

## Wachtwoord wijzigen
`python3 tools/site.py setkey /tmp/site.json --niveau td --password "..."` `--niveau dagstart`, `--niveau melden`, `--niveau monteur` of `--niveau wv`, en daarna stap 4 t/m 6.
