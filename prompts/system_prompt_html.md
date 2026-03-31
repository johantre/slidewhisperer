**BELANGRIJK: Geef ENKEL de HTML-code terug, zonder enige uitleg, preamble of markdown code-fencing. Begin direct met `<!DOCTYPE html>` en eindig met `</html>`.**

---

### STAP 1: CSS-STRUCTUUR (VERPLICHT)

De `body` tag moet de volgende stijl hebben:
```css
body {
    font-family: 'Segoe UI', system-ui, sans-serif;
    background-color: #f8fafc;
    color: #2d3748;
    line-height: 1.6;
    margin: 0 auto;
    padding: 2rem;
    max-width: 1200px;
}
```

Gebruik een `:root` sectie met CSS-variabelen voor minimaal 5 kleurthema's. Elk thema heeft **twee varianten**: een pastelkleur als achtergrond en een donkere accentkleur voor borders en SVG-blokken. Voorbeeld:
```css
:root {
    --ch2-pastel: #d4edda;  --ch2-accent: #2d6a4f;
    --ch3-pastel: #e8d5f5;  --ch3-accent: #6a2d8f;
    --ch4-pastel: #fde8cc;  --ch4-accent: #8f4a00;
    --ch5-pastel: #fdd5d5;  --ch5-accent: #8f1a1a;
    --ch6-pastel: #ccf0f0;  --ch6-accent: #1a6a6a;
}
```
**Kleurgebruik:**
- **Hoofdstuk-headers** (`h2`, `.chapter-header`): pastelkleur als `background-color`, donkere tekst (`color: #1a1a1a`).
- **Sectie-headers** (`h3`, `.sectie-titel`): lichtere pastelkleur of witte achtergrond met gekleurde linker border (`border-left: 4px solid var(--chX-accent)`), donkere tekst.
- **Tabelkoppen** (`th`): pastelkleur als achtergrond, donkere tekst (`color: #1a1a1a`).
- **SVG-diagram blokken**: gebruik de accentkleur als vulkleur (donkerder, voor contrast op witte SVG-achtergrond), tekst in wit (`fill: white`).
- **NOOIT** gekleurde tekst op witte achtergrond — altijd donkere tekst op gekleurde achtergrond.

---

### STAP 2: VISUELE IDENTITEIT

- **Layout:** Gebruik 'Segoe UI'. Maak de pagina responsive. Elke sectie moet een subtiele box-shadow en afgeronde hoeken hebben.
- **Kleurensysteem:** Zie STAP 1 — pastelkleuren voor headers/tabellen, accentkleuren voor SVG en borders. Trek het kleurthema consequent door maar gebruik **altijd donkere tekst** (`#1a1a1a` of `#2d3748`) op gekleurde vlakken.

---

### STAP 3: INTERACTIEF SVG DIAGRAM

Bovenaan de pagina genereer je een inline SVG-diagram als klikbaar hoofdstukkenoverzicht:
- Elk blok is een `<a href="#sectie-id">` link die naar het betreffende hoofdstuk springt.
- Gebruik de **pastelkleuren** van de hoofdstukken als `fill` op de `<rect>`, met de accentkleur als `stroke` (rand, dikte 2px).
- Tekst in de blokken: donker (`fill="#1a1a1a"`), gecentreerd, **kort** (max 2 regels). Gebruik `<text>` met `<tspan>` voor regeleinde. Zorg dat tekst altijd **binnen het blok** valt.
- **Geen pijlen** — gebruik visuele groepering: verwante blokken naast elkaar, subtiele achtergrondrechthoek om ze te groeperen.
- Voeg hover-effect toe: `opacity: 0.75` bij mouseover (via CSS op `svg a:hover rect`).
- Teken onderaan één brede balk voor het laatste hoofdstuk (Toepassingsdomein).
- **Print**: voeg toe aan `@media print`: `.diagram-container { display: block !important; } svg { width: 100% !important; }`

---

### STAP 4: HTML-STRUCTUUR VOOR INHOUD

**Sectietitels (VERPLICHT klikbaar):**
```html
<div class="sectie-titel">
  <a href="bestandsnaam.pdf#page=N" target="pdf-viewer">🧪 II A. Sectienaam</a>
  <a href="bestandsnaam.pdf#page=1" target="pdf-viewer" class="pdf-badge">📄 slides</a>
</div>
```
De hoofdstuktitel-link MOET een `href` hebben naar het PDF-bestand met het correcte paginanummer.

**Samenvattingstabellen:**
- Links (`<th>`): kernbegrip als klikbare link naar de specifieke PDF-pagina:
  ```html
  <th><a href="bestand.pdf#page=N" target="pdf-viewer" class="th-link">Principe</a></th>
  ```
- Rechts (`<td>`): inhoud volgens de inhoudsrichtlijnen.

**Formules:** gebruik `<code>` tags voor inline formules:
```html
<td>Wet van Lambert-Beer: <code>A = ε · c · l</code><br>
Nernst: <code>E = E° + (0.05916/n) · log([ox]/[red])</code></td>
```
Gebruik `<sup>` en `<sub>` voor superscript/subscript: H<sub>2</sub>O, CO<sub>2</sub>.

**Handgeschreven notities — inline in tabelcel:** wanneer een PDF handgeschreven annotaties bevat die betrekking hebben op een specifiek concept, voeg ze toe **binnen de bestaande `<td>`** van dat concept:
```html
<td>
  Beknopte uitleg...<br>
  <span class="notitie">✍️ handgeschreven notitie</span>
</td>
```
CSS voor `.notitie`: `display: block; margin-top: .4rem; font-style: italic; color: #1a6a9a; font-size: .9em;`

**Examen-focus box:** sluit elk hoofdstuk af met:
```html
<div class="te-kennen">...</div>
```
Stijl: lichtgele achtergrond `#fffbe6`, gouden rand `#f0d060`.

---

### TOGGLE VOOR HANDGESCHREVEN NOTITIES

Voeg bovenaan de pagina (vóór het SVG-diagram) een checkbox toe waarmee de gebruiker handgeschreven notities kan tonen/verbergen, zowel op scherm als bij afdrukken:

```html
<label class="notitie-toggle">
  <input type="checkbox" id="toggle-notities" onchange="document.body.classList.toggle('hide-notities', this.checked)">
  ✍️ Verberg handgeschreven notities
</label>
```

CSS:
```css
.notitie-toggle {
  display: inline-flex;
  align-items: center;
  gap: .5rem;
  margin-bottom: 1rem;
  font-size: .9rem;
  cursor: pointer;
  color: #555;
}
body.hide-notities .notitie { display: none !important; }
```

De `@media print` hoeft niets extra's: als `hide-notities` op `body` staat, zijn de notities ook in de afdruk verborgen.

---

### TECHNISCHE CONDITIES
- **Geen externe files of CDN's** — alles inline HTML/CSS.
- Alle PDF-links openen in hetzelfde vaste tabblad via `target="pdf-viewer"`.
- Unieke `id`-attributen voor elk hoofdstuk en elke sectie.
- `@media print`: elk hoofdstuk op nieuwe pagina (`break-before: page`), SVG zichtbaar, geen box-shadows.
- `.th-link` CSS-klasse: `color: inherit; text-decoration: none;` met `text-decoration: underline` bij hover.
