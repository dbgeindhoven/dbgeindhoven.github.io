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
   - `output`: `eenheid`, `bron`, `dagen` (`datum`, `lijn`, `ploeg`, `kg`) en `plan` (`datum`, `lijn`, `kg`). Dit zijn de startcijfers uit het Excel-bestand "Output per ploeg EHV"; het plan is de som van de productieorders per lijn op Due Date. Wat de ploegen invullen staat live in de Sheet (tabblad `Output`) en gaat voor op deze cijfers.
   - `storingen` niet met de hand aanpassen: `site.py build` maakt die lijst uit de open bonnen van het CM-overzicht. Gepland blijft Gepland, Besteld of een bestelregel op Besteld wordt In bestelling, de rest wordt Open. Gereed verdwijnt. Een veld `actiehouder` op een CM-regel gaat voor op `monteur`.
4. `python3 tools/site.py build /tmp/site.json --stand DD-MM-JJJJ --plain /tmp/artifact.html --public index.html`
5. Publiceer `/tmp/artifact.html` met de Artifact-tool op dezelfde `url`.
6. Commit en push alleen `index.html` en `bonnen/` (en eventueel `tools/`) naar `main`. GitHub Pages publiceert vanaf `main`, map `/`.

## Actielijst ochtendoverleg
`meta.actielijst` (`bron`, `regels`) staat alleen in het werkvoorbereidingsdeel. Op de pagina Actielijst controleert de werkvoorbereider de indeling en zet hij de acties in één keer op het SQD-bord: de browser maakt per regel een melding met melder `Ochtendoverleg`, zodat Google het SQDM-nummer geeft. De melddatum op het bord is de invoerdatum uit de actielijst. Met `geplaatst: true` toont de pagina alleen nog de prio's. Haal `meta.actielijst` weg als alles geplaatst is en de prio's zijn opgeslagen.

Een nieuwe pagina maak je in `tools/template.html`: voeg een scherm toe aan `SCHERM` en aan `P_DAG` of `P_TD`. Dagstartpagina's moeten ook in het dagstartdeel van `build` in `tools/site.py`.

## Meldingen
Een melding bestaat uit melder, foto, probleem en risico (Safety, Quality of Delivery). Op de pagina Meldingen vult de dagstart of TD de opvolging aan en zet een melding desgewenst door naar S, Q of D op het SQD-overzicht (kolom `letter`; leeg betekent nog niet doorgezet). De site is statisch, dus meldingen gaan via een Google Apps Script-webapp (`tools/meldingen.gs`) naar de privé Google Sheet "TD Hub meldingen". De webadres, de sleutel en het Sheet-ID staan in `meta.meldingen` in de privépagina, niet in deze repository. Zonder `url` blijven de knoppen verborgen. Het SQD-overzicht werkt alleen met meldingen met een `SQDM`-code die zijn doorgezet: er staan bewust geen cijfers uit de CM-bonnen op. Een open melding kleurt de letter rood. Een melding met `bon_nodig` = Ja is bedoeld voor een CM-bon. De Sheet heeft per melding ook `oplossing` en `foto` (Drive-bestand in de privémap "TD Hub foto's"). Directie-acties staan in dezelfde Sheet met letter `DIR`. Op het SQD-overzicht toont een kaartje alleen het probleem, de actiehouder, de melddatum en de kleur van de prio (kolom `prio`, 1 t/m 3); de rest staat in het detailpaneel.

## Bonnen uit meldingen
Een productiemelding krijgt bij binnenkomst de code `SQDM-n` (kolom `code` in de Sheet) en wordt meteen een echte bon met datzelfde nummer. De dagstart of TD kan dat voorkomen door het vinkje "Technische dienst nodig: maak een CM-bon" weg te halen voordat de taak draait. Een monteurstoring wordt altijd een bon, met het eerstvolgende CM-nummer. Alle bonnen staan in de lijst `cm`, met `herkomst` (Productie of Monteur) en `bon`: de versleutelde Word- en PDF-bon, plus een afbeelding (`beeld`) waarmee de bon op de site zelf opent. Op de site staan SQD-bonnen (`SQDM-n`) apart van de CM-bonnen: de pagina CM-bonnen toont ze niet, Lopende storingen wel. De bestanden zijn alleen te openen op de pagina's SQD-bonnen en Aangemaakte CM-bonnen, met het eigen wachtwoord van de werkvoorbereider. Welke melding welke bon werd staat in `meta.bonnen.verwerkt`.

Een statuswijziging of een verwijderde bon staat als `status-<nr>.txt` in de wachtrijmap. De site past die meteen toe voor iedereen en de geplande taak zet hem daarna in `cm`. Een verwijderde melding blijft in de Sheet staan met status `Verwijderd`, zodat een SQDM-nummer nooit dubbel uitkomt; de foto gaat naar de prullenbak.

De geplande taak "TD Hub bonnen" maakt de bonnen. De werkwijze staat in `tools/bonnen.md`. De taak draait elk uur, dag en nacht. Pas je `tools/meldingen.gs` aan, stuur dan een nieuwe ingevulde versie van het script; de echte waarden staan in `meta.meldingen`.

## Zes toegangsniveaus
- **Melden:** alleen het meldformulier. Dit deel bevat geen enkele lijst, en de meldsleutel kan alleen nieuwe meldingen versturen.
- **Monteur:** storing melden en het gedeelde dienstrapport. Dit deel bevat alleen de machinenamen voor het formulier en geen andere lijsten; de monteursleutel leest alleen dienstrapportregels en voegt alleen storingen toe. Dienstrapportregels staan in de Sheet met letter `TD` en status `Rapport`, met `vervolg` Gereed, Overdragen aan volgende dienst, Onderdeel bestellen of Plannen voor onderhoudstop. De machinelijst komt uit `opnamelijsten`; aanvullen kan per lijn in `meta.machines_extra`. Zonder bereik blijft een storing op de telefoon staan en verstuurt hij zichzelf. `sw.js` zorgt dat de pagina dan ook opent.
- **Output:** één gezamenlijke inlog voor de ploegen. Alleen het formulier met naam, datum, ploeg, lijn, output in kilo en opmerking. Dit deel bevat geen enkele lijst; de outputsleutel leest en schrijft alleen het tabblad `Output`. Opnieuw invullen voor dezelfde datum, ploeg en lijn vervangt de regel.
- **Dagstart:** SQD, Meldingen, Lopende storingen, Output per lijn en Zaterdag. In de presentatie staat Meldingen niet, en heeft Output per lijn een eigen stap per lijn met tabel en grafiek. Lopende storingen toont alleen prio 1: bonnen en meldingen, omdat die SQD direct in gevaar brengen. Bij een melding zonder bon staat een vinkje of er een bon gemaakt moet worden.
- **TD:** alles, dus ook TD-overzicht, CM-bonnen, Bestellijst, Priolijst, Opnamelijsten, PM-taken en Dienstrapport. Geen bonbestanden: dit deel bevat de sleutel van de bonnen niet.
- **Werkvoorbereider (`wv`):** alles van TD plus de pagina's SQD-bonnen en Aangemaakte CM-bonnen, waar de Word- en PDF-bonnen te downloaden zijn. Alleen dit deel bevat `meta.bonnen.sleutel`, `cm[].bon` en `meta.meldingen.sleutel_wv`. Met die sleutel past de werkvoorbereider de status van een bon aan en verwijdert hij meldingen, storingen, directie-acties en bonnen die uit een melding komen.
`index.html` bevat per niveau een eigen versleuteld deel. Het dagstart-wachtwoord kan de TD-gegevens niet openen.

## Wachtwoord wijzigen
`python3 tools/site.py setkey /tmp/site.json --niveau td --password "..."` `--niveau dagstart`, `--niveau melden`, `--niveau monteur`, `--niveau output` of `--niveau wv`, en daarna stap 4 t/m 6.
