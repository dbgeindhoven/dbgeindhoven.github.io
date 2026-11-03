# TD-site DBG Eindhoven

View-only website voor de overzichten van de technische dienst. Publiek adres: https://dbgeindhoven.github.io/

Repository: `dbgeindhoven/dbgeindhoven.github.io`.

## Waar de gegevens staan
- **Leesbaar:** in de privépagina bij Claude: https://claude.ai/artifact/3JPNTaJyRYKhn2m64RygkB. Dit is de bron. Daarin staat ook de sleutel voor de versleuteling (`meta.publiek`).
- **Versleuteld:** in `index.html` in deze repository.
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
6. Commit en push alleen `index.html` (en eventueel `tools/`) naar `main`. GitHub Pages publiceert vanaf `main`, map `/`.

Een nieuwe pagina maak je in `tools/template.html`: voeg een scherm toe aan `SCHERM` en aan `P_DAG` of `P_TD`. Dagstartpagina's moeten ook in het dagstartdeel van `build` in `tools/site.py`.

## Meldingen
Op het SQD-overzicht kunnen bezoekers per letter een melding maken. De site is statisch, dus meldingen gaan via een Google Apps Script-webapp (`tools/meldingen.gs`) naar de privé Google Sheet "TD Hub meldingen". De webadres, de sleutel en het Sheet-ID staan in `meta.meldingen` in de privépagina, niet in deze repository. Zonder `url` blijven de knoppen verborgen. Een open melding kleurt de letter rood. Een melding met `bon_nodig` = Ja is bedoeld voor een CM-bon.

## Twee toegangsniveaus
- **Dagstart:** SQD, Lopende storingen, Output per lijn en Zaterdag.
- **TD:** alles, dus ook TD-overzicht, CM-bonnen, Bestellijst, Priolijst, Opnamelijsten en PM-taken.
`index.html` bevat per niveau een eigen versleuteld deel. Het dagstart-wachtwoord kan de TD-gegevens niet openen.

## Wachtwoord wijzigen
`python3 tools/site.py setkey /tmp/site.json --niveau td --password "..."` of `--niveau dagstart`, en daarna stap 4 t/m 6.
