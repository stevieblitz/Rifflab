# RiffLab — gebruikerswensen en herstelplan (14 oktober 2026)

**Bron van waarheid:** werk uitsluitend verder vanaf de door gebruiker aangewezen stabiele Windows UI test run #69, commit `9f2865fa43856a5fe16f7b805c29bb9456bf1d58` (v2.0.0-dev.69). Ontwikkel op `restore-from-dev69`, **niet op main**. Geen 1.3.x-code of blinde cherry-picks, geen nieuwe zware build tot de UI en audio gecontroleerd zijn. Dit zijn wensen van de gebruiker, niet nieuwe featurevoorstellen van de assistent.

## P0 — audio / regressie (moet altijd correct blijven)
- [ ] **Transpose is notation-only:** verschuift zichtbare noten/akkoorden én hoofdindicator, **nooit** audio-pitch, mix of export. Test bij -12, -1, 0, +1, +12; spelen én pauzeren, met/zonder stems.
- [ ] **Steps is niet pitch:** wijziging van steps/timing/resolutie verandert nooit audio-pitch. Onderzoek de feitelijke control en signaalverbinding op dev.69.
- [ ] **BPM verandert echte afspeelsnelheid met behoud van pitch** en houdt waveform/grid in sync.
- [ ] Detectie van chords/notes alleen uit bass/guitar/other, niet vocals; Bass Mode toont de grondtonen, geen major/minor.
- [ ] Hoofdnootindicator loopt synchroon met timeline en toont geen tussenliggende kortstondige detecties.
- [ ] Controleer bestaande NoteGuard / Stability instellingen en analyseparameters; wijzig ze niet zonder gerichte test.

## P1 — PLAYER / timeline
- [ ] Lange, aaneengesloten gekleurde nootbalken, **geen losse beatblokjes**. De lengte weerspiegelt de duur; doorlopende noot hoeft niet bij maatgrens te breken.
- [ ] Beatlijnen en afzonderlijke duidelijke **maatstrepen/nummers boven de nootbalken**; steeds zichtbaar waar volgende maat begint (Chordify-referentie).
- [ ] Verticale akkoord-/noottimeline met automatisch volgen en circa 4–8 maten vooruit, klik om te springen; A/B-loop.
- [ ] Horizontale zoom met echt horizontale slider, verticale hoogtezoom met echt verticale slider, beide in player dock.
- [ ] Waveform zichtbaar; klik/sleep voor seek, synchroniseer hoofdindicator en noten; eigen waveform zoom.
- [ ] Confidence-indicator **onder waveform**; onzekere noten met accent in corresponderend waveformsegment. **Confidence View heeft voorrang**.
- [ ] Zoom, scroll-/splitterposities en overige instellingen na herstart onthouden.

## P1 — werkruimte en navigatie
- [ ] Strak, flat, eenvoudig, futuristisch; compact, rustige marges, geen rommel. Zelf grafisch kunnen aanpassen via Qt Designer/developerworkflow, **geen eindgebruikers-customizer**.
- [ ] Adobe-achtige menu's: **File** (Open, Save, Save As, Recent, Import/Export) en **View** met **Workspace** (Save, Load, Reset).
- [ ] **View > Panels** toggles: Mixer, Timeline, Main Indicator, Tuner. Standaard aan; verborgen panelen bij herstel op eigen positie, formaat en zoom.
- [ ] Tuner **eigen pagina/tab** terug, niet vast onder mixer, niet zwevend; inputkeuze/tunings, chroma/needle/waveform behouden.
- [ ] Mixer verticaal scrollbaar, voldoende breed, elke stem bruikbaar; geen clipping.
- [ ] No(o)tinstellingen bundelen in één dropdown plus knop Input Settings.
- [ ] Analyze, Re-analyze en Stop logisch bundelen.
- [ ] Alle zichtbare interfacecopy in het Engels.
- [ ] Weg met onnodige PROJECT-vermelding; geen visuele regressies.

## P1 — stems & mixer
- [ ] Zonder stems blijft mixer zichtbaar maar gedimd/uitgeschakeld, overlay met **Generate Stems**.
- [ ] Tijdens generatie: **Generating Stems…**, niet klikbaar; na generatie overlay automatisch weg en mixer aan.
- [ ] Footer LED: grijs **STEMS OFF**, oranje **CREATING**, groen **STEMS READY**.
- [ ] Bestaande Demucs, import via YouTube of lokale bestanden, export en stemvolumes intact laten.

## P1 — branding
- [ ] Gebruik de **originele, goedgekeurde** officiële logo-/iconbestanden uit dev.69. Geen nieuwe symbolen verzinnen.
- [ ] Controleer venstericoon, exe-icoon, logo binnen app, controls en het Qt Designer-prototype; consistent met de eerdere goedgekeurde verhoudingen.
- [ ] Credits: “by Stevie Blitz, powered by AI”, Stevie Blitz-link naar GitHub.

## Ontwikkelvolgorde / acceptatie
- [x] Stabiele basis #69 uit GitHub Actions bevestigd.
- [x] Aparte branch `restore-from-dev69` vanaf #69.
- [x] Eerder codewerk op deze branch: File/View-basismenu's, apart TUNER-tab, scrollbare mixer, stem-overlay/LED. **Nog niet gevalideerd, geen definitieve acceptatie**.
- [ ] Geautomatiseerde syntax/import/start-up-check op **de exacte branch**, plus screenshot van het werkelijk draaiende venster.
- [ ] Pitch-/transpose-/BPM-tests met hoorbare audio en synchronisatietest.
- [ ] UI vergelijken met dev.69 en screenshots: logo's, iconen, spacing, note bars, active note, waveform, tuner, menus.
- [ ] Bovenstaande P1-punten volledig uitvoeren; eerst kleine test/screenshot, daarna pas volledige Windows-testbuild.
- [ ] Geen stille wijziging van muzikale logica; geen push naar main totdat gebruiker resultaat goedkeurt.

**NB:** De eerder gebruikte branch `restore-stable-ui-transpose` komt van 1.3.x en is niet de nieuwe basis.
