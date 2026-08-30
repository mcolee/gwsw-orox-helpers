export const meta = {
  name: 'orox-10x-swarm',
  description: 'Multi-lens review van gwsw-orox-helpers; Fable-regisseur levert <=25 aanbevelingen voor 10x beter',
  phases: [
    { title: 'Review', detail: '8 lens-agents beoordelen de package parallel' },
    { title: 'Verify', detail: 'adversariele verify + additief-vs-contract per aanbeveling' },
    { title: 'Regie', detail: 'Fable-regisseur rangschikt <=25 aanbevelingen' },
  ],
}

const CONTEXT = `
Repo-root (cwd): /home/martin/gwsw-orox-helpers  (Python 3.12+, src-layout, uv).
Package: src/gwsw_orox_helpers/ — leeslaag voor GWSW-OroX (TTL) rioleringsdata.
Modules (LOC): clip 1299, dataset 730, inlezen 717, cache 297, domein 277, graaf 257,
schrijven 249, ontologie 147, klassen 122, geometry 122, codering 118, voortgang 59,
namen 42, bronnen 26, __init__ 21, errors 9.
Deps: pyoxigraph>=0.5 (Rust-parser, snelpad), rdflib>=7.0, shapely>=2.0.
Lees docs/architectuur.md voor de lagen en de twee pyoxigraph-paden (lezen-met-index,
schrijven-als-stroom).

HARDE CONTEXTREGELS (staan in CLAUDE.md):
- De publieke API die de afnemer nlriochecker importeert is BEVROREN: clip_orox, merge_orox,
  lees_orox, schrijf_orox, schrijf_orox_quads (uit __init__) EN de leeslaag dataset/cache/
  geometry. Geen enkele bestaande signatuur, retourvorm of gedrag mag breken.
- Aanbevelingen moeten ADDITIEF zijn (nieuwe modules/functies). Raakt een idee toch een
  bevroren contract, dan is het een VOORSTEL-VOOR-DE-AUTEUR, niet iets uitvoerbaars — markeer
  dat expliciet.
- Leidende GWSW-versie 1.6 uit de gebundelde ontologie; index is gegenereerd.
- Poort: ruff check, ruff format, mypy, pytest, dekking >=95%.
Onderzoek de code echt (Read/Grep/Bash in de repo) voordat je oordeelt; geen giswerk.`

const DIMENSIONS = [
  { key: 'architectuur', prompt: `LENS: ARCHITECTUUR & laagsnit. Beoordeel de laagindeling en importrichting (docs/architectuur.md), de twee pyoxigraph-paden, waar IRI/prefix/codering-kennis woont, en of de grote modules (clip 1299, dataset 730, inlezen 717) diepe modules zijn of god-modules. Zoek deepening-kansen: smallere interfaces over complexere implementaties.` },
  { key: 'modulariteit', prompt: `LENS: MODULARITEIT & koppeling. Breng cyclische of te strakke koppeling in kaart, lekkende abstracties, en verantwoordelijkheden die verkeerd wonen. Waar zou een nieuwe seam de package losser en testbaarder maken zonder een bevroren contract te raken?` },
  { key: 'beheerbaarheid', prompt: `LENS: BEHEERBAARHEID & leesbaarheid. Duplicatie, te lange functies, onduidelijke namen, ontbrekende types, dode code, inconsistente foutafhandeling (errors.py 9 LOC — genoeg?). Concrete vereenvoudigingen die de onderhoudslast verlagen.` },
  { key: 'upgradebaarheid', prompt: `LENS: UPGRADEBAARHEID & API-evolutie. Hoe pijnlijk is een pyoxigraph/rdflib/shapely-major-bump of een nieuwe GWSW-ontologieversie? Beoordeel het handmatige index-regeneratiepad, versie-drift-tests, en of de publieke API additief kan groeien (deprecatiebeleid vóór 1.0). Respecteer de bevriezing.` },
  { key: 'security', prompt: `LENS: SECURITY. De package leest onvertrouwde TTL/GeoPackage-invoer en schrijft bestanden. Zoek: onveilige deserialisatie, path-traversal bij schrijfpaden, XML/RDF-entiteitsuitbreiding, resource-uitputting (memory/geen limieten) op vijandige input, injectie in SPARQL/queries, en secrets/artefacten in de repo. Wees concreet over de aanvalsinvoer.` },
  { key: 'performance', prompt: `LENS: PERFORMANCE & geheugen. De laadtijd-historie zit rond ~20s; open perf-punten raken de gepinde API (dus additief benaderen). Zoek hotspots in inlezen/dataset/clip: onnodige materialisatie, O(n^2)-patronen, herhaalde parses, GC-druk, ontbrekende streaming. Stel meetbare, additieve optimalisaties voor (snelpad naast bestaand pad).` },
  { key: 'testbaarheid', prompt: `LENS: TESTBAARHEID & correctheid. Dekking staat >=95% maar dekt dat de kritieke paden (geometrie, cache, ontologie-inlees, clip) echt? Zoek zwakke asserties, ontbrekende edge-cases (lege/corrupte TTL, ontbrekende geometrie, CRS-mismatch), en drift-tests die te los zijn. Stel gerichte tests/fixtures voor.` },
  { key: 'ci-hygiene', prompt: `LENS: CI & repo-hygiene. Beoordeel .github/workflows (toets.yml, release.yml), de vijf-staps-poort, GitHub Actions-efficientie (dubbele triggers, caching, concurrency, matrix), en of er artefacten/secrets/junk getrackt worden die er niet horen. Concrete verbeteringen aan de ontwikkelstraat.` },
]

const RECS_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['recommendations'],
  properties: {
    recommendations: {
      type: 'array', maxItems: 6,
      items: {
        type: 'object', additionalProperties: false,
        required: ['title', 'probleem', 'voorstel', 'bestanden', 'impact', 'ernst', 'inspanning', 'raaktContract'],
        properties: {
          title: { type: 'string' },
          probleem: { type: 'string', description: 'wat is er mis, concreet en met bewijs uit de code' },
          voorstel: { type: 'string', description: 'de additieve wijziging' },
          bestanden: { type: 'array', items: { type: 'string' } },
          impact: { type: 'string', enum: ['architectuur','modulariteit','beheerbaarheid','upgradebaarheid','security','performance','testbaarheid','ci-hygiene'] },
          ernst: { type: 'string', enum: ['laag','midden','hoog','kritiek'] },
          inspanning: { type: 'string', enum: ['S','M','L','XL'] },
          raaktContract: { type: 'boolean', description: 'true als het een bevroren nlriochecker-contract raakt' },
        },
      },
    },
  },
}

const VERDICT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['isEcht', 'additief', 'redenering', 'tienXhefboom'],
  properties: {
    isEcht: { type: 'boolean', description: 'false als de aanbeveling onjuist, al opgelost, of speculatief is' },
    additief: { type: 'boolean', description: 'true als uitvoerbaar zonder een bevroren contract te breken; false = voorstel-voor-de-auteur' },
    redenering: { type: 'string' },
    tienXhefboom: { type: 'string', enum: ['triviaal','klein','noemenswaardig','groot'], description: 'bijdrage aan 10x beter' },
  },
}

const PLAN_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['aanbevelingen', 'themas', 'slotnoot'],
  properties: {
    aanbevelingen: {
      type: 'array', maxItems: 25,
      items: {
        type: 'object', additionalProperties: false,
        required: ['rang','titel','waarom10x','categorie','additief','inspanning','bestanden'],
        properties: {
          rang: { type: 'integer' },
          titel: { type: 'string' },
          waarom10x: { type: 'string' },
          categorie: { type: 'string' },
          additief: { type: 'boolean' },
          inspanning: { type: 'string', enum: ['S','M','L','XL'] },
          hangtAf: { type: 'string', description: 'rang(en) waar dit van afhangt, of leeg' },
          bestanden: { type: 'array', items: { type: 'string' } },
        },
      },
    },
    themas: { type: 'array', items: { type: 'string' }, description: 'de rode draden' },
    slotnoot: { type: 'string', description: 'wat de auteur zelf moet beslissen (contract-rakers) en wat additief kan' },
  },
}

phase('Review')
log(`Swarm start: ${DIMENSIONS.length} lenzen over gwsw-orox-helpers`)

const reviewed = await pipeline(
  DIMENSIONS,
  (d) => agent(
    `${CONTEXT}\n\n${d.prompt}\n\nLever maximaal 6 aanbevelingen met de hoogste hefboom voor "10x beter". Elke aanbeveling concreet, met bewijs uit de code en de geraakte bestanden.`,
    { label: `review:${d.key}`, phase: 'Review', schema: RECS_SCHEMA, effort: 'high' },
  ),
  (review, d) => parallel(((review && review.recommendations) || []).map((r, i) => () =>
    agent(
      `${CONTEXT}\n\nVERIFIEER adversarieel deze aanbeveling (lens ${d.key}).\nTITEL: ${r.title}\nPROBLEEM: ${r.probleem}\nVOORSTEL: ${r.voorstel}\nBESTANDEN: ${(r.bestanden||[]).join(', ')}\nAUTEUR-CLAIM raaktContract=${r.raaktContract}.\n\nControleer in de echte code: is het probleem echt en nog niet opgelost? Is het voorstel additief of raakt het een BEVROREN contract (clip_orox/merge_orox/lees_orox/schrijf_orox/schrijf_orox_quads + leeslaag dataset/cache/geometry)? Standaard isEcht=false bij twijfel.`,
      { label: `verify:${d.key}:${i}`, phase: 'Verify', schema: VERDICT_SCHEMA, effort: 'medium' },
    ).then((v) => (v ? { ...r, dimension: d.key, verdict: v } : null)),
  )),
)

const overleefd = reviewed.flat().filter(Boolean).filter((x) => x.verdict && x.verdict.isEcht)
log(`Geverifieerd: ${overleefd.length} echte aanbevelingen naar de regisseur`)

phase('Regie')
const bundel = overleefd.map((x, i) => ({
  n: i + 1, lens: x.dimension, titel: x.title, probleem: x.probleem, voorstel: x.voorstel,
  bestanden: x.bestanden, impact: x.impact, ernst: x.ernst, inspanning: x.inspanning,
  additief: x.verdict.additief, hefboom: x.verdict.tienXhefboom, verifyNoot: x.verdict.redenering,
}))

const plan = await agent(
  `${CONTEXT}\n\nJij bent de REGISSEUR. Hieronder ${bundel.length} geverifieerde aanbevelingen uit 8 lenzen:\n\n${JSON.stringify(bundel, null, 1)}\n\nSynthetiseer tot MAXIMAAL 25 aanbevelingen die samen de package ~10x beter maken op architectuur, beheerbaarheid, upgradebaarheid, modulariteit, security en performance. Ontdubbel overlappende ideeen, fuseer waar lenzen elkaar raken, en RANGSCHIK op (hefboom x haalbaarheid). Elke aanbeveling: waarom het 10x-relevant is, additief-vlag (contract-rakers apart en achteraan, als voorstel-voor-de-auteur), inspanning, afhankelijkheden en bestanden. Benoem de rode draden en zet in de slotnoot scherp wat de auteur zelf moet beslissen versus wat een agent additief mag oppakken.`,
  { label: 'regisseur:fable', phase: 'Regie', model: 'fable', schema: PLAN_SCHEMA, effort: 'high' },
)

return { geverifieerd: overleefd.length, plan }
