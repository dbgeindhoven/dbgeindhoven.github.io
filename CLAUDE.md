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
4. `python3 tools/site.py build /tmp/site.json --stand DD-MM-JJJJ --plain /tmp/artifact.html --public index.html`
5. Publiceer `/tmp/artifact.html` met de Artifact-tool op dezelfde `url`.
6. Commit en push alleen `index.html` (en eventueel `tools/`) naar `main`. GitHub Pages publiceert vanaf `main`, map `/`.

Een nieuw tabblad maak je in `tools/template.html`: voeg een scherm toe aan `VIEWS` en `RENDER`.

## Wachtwoord wijzigen
`python3 tools/site.py setkey /tmp/site.json --password "..."` en daarna stap 4 t/m 6.
