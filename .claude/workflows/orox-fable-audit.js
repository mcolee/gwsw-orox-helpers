export const meta = {
  name: 'orox-fable-audit',
  description: 'Fable 5.1-swarm: is gwsw-orox-helpers PyPI-klaar en professioneel? 9 lenzen met bewijs, adversariele verify, Fable-regisseur',
  phases: [
    { title: 'Audit', detail: '9 Fable-lenzen: defecten met repro, security, packaging, architectuur, kwaliteit', model: 'fable' },
    { title: 'Verify', detail: 'Fable-skepticus draait repro na of controleert het bewijs in de code', model: 'fable' },
    { title: 'Regie', detail: 'Fable-regisseur: release-blokkers eerst, dan ernst x zekerheid', model: 'fable' },
  ],
}

// Optioneel: args = { scratch: '<map voor repro-scripts>' }
const SCRATCH = (args && args.scratch) || '/tmp/orox-fable-audit'

const CONTEXT = `
Repo-root (cwd): /home/martin/gwsw-orox-helpers  (Python 3.12+, src-layout, uv, versie 0.2.2).
Package: src/gwsw_orox_helpers/ — leeslaag voor GWSW-OroX (TTL) rioleringsdata.
Modules (LOC): dataset 984, inlezen 794, cache 417, graaf 330, clip/ (knip 316, plan 312,
merge 294, bereik 196, __init__ 185, stroom 151, termen 128, orkest 118, grenzen 85),
schrijven 277, domein 277, geometry 244, ontologie 231, netwerk 211, namen 177, bestand 175,
rdfmotor 158, errors 153, klassen 142, codering 118, bronnen 73, voortgang 59.
Deps: pyoxigraph>=0.5 (Rust-parser), rdflib>=7.0, shapely>=2.0. Gebundelde data: twee
GWSW-ontologieen (TTL) en twee vocabulaire-indexen (JSON) in src/gwsw_orox_helpers/data/.
Lees docs/architectuur.md eerst; lees elk bestand dat je beoordeelt EEN KEER VOLLEDIG met Read.
Geen cd; werkmap is de repo-root.

DOEL VAN DE AUTEUR: een PyPI-klare, professionele package — kwaliteit, goede architectuur,
geen security-bugs. Jij beoordeelt of het dat al IS en wat er aantoonbaar aan ontbreekt.

HARDE CONTEXTREGELS (CLAUDE.md):
- Twee gebundelde GWSW-versies: 1.6 (default/leidend) en 1.7; de package detecteert de versie
  uit de gwsw:-prefix van de bron; onbekend -> 1.6 met logging.warning; publieke leesweg
  GwswDataset.gwsw_versie.
- De publieke API die nlriochecker importeert is BEVROREN: clip_orox, merge_orox, lees_orox,
  schrijf_orox, schrijf_orox_quads (uit __init__) EN de leeslaag dataset/cache/geometry.
  Een bevinding die dat raakt is een VOORSTEL-VOOR-DE-AUTEUR (raaktContract=true).
- Poort: ruff check, ruff format, mypy, pytest, dekking >=95%.

WAT AL GEDAAN IS (issues #1-#39, allemaal gesloten; niet opnieuw voorstellen):
clip/-package-splitsing, is_a-memo, een-pass GML-lezer, mkstemp voor tmp-bestand, dep-bovengrenzen,
_oxigraph-adapter (rdfmotor), GraafLezer-protocol, RecursionError in _lees_grenzen, mypy
disallow_untyped_defs, DatasetError-subklassen, dedup-generator, netwerk-module, CI-triggers/
cache/matrix, CRS-mismatch-test, round-trip-fixture, subset() verliest geometry_errors (#36),
frozenset-iteratievolgorde in _orientations_of_class (#37), GWSW 1.7 dual-version (#32),
gwsw_versie-accessor (#39).

BEWIJSPLICHT. Elke bevinding heeft een 'soort':
- defect / security: aantoonbaar fout gedrag op concrete invoer. Schrijf een minimale repro
  (pytest-bestand of script) in ${SCRATCH}/<lens>/ (maak de map aan; NOOIT in de repo), draai
  hem met \`uv run python ...\` of \`uv run pytest <pad> -x -q\` vanuit de repo-root en plak de
  werkelijke uitvoer als bewijs. Zonder draaiende repro: zekerheid='vermoeden'.
- packaging / architectuur / kwaliteit: bewijs is een exact bestand:regel-citaat of de uitvoer
  van een commando (bv. \`uv build\`, \`unzip -l dist/*.whl\`, \`uv run python -c 'import ...'\`).
Draai NIET de volledige testsuite. Wijzig NIETS in de repo (dist/ opruimen mag als je hem maakte).
Meningen, stijlvoorkeuren en "zou mooier kunnen" tellen niet; "een professionele afnemer zou
hierover struikelen" telt wel, mits met bewijs.`

const DIMENSIONS = [
  { key: 'packaging', prompt: `LENS: PYPI-KLAARHEID. Beoordeel pyproject.toml (metadata, classifiers, license, readme, urls, requires-python, dynamic version), py.typed, __all__/__version__, wat er in de wheel en sdist zit (draai \`uv build\` naar ${SCRATCH}/packaging/dist en inspecteer: data-bestanden aanwezig? grootte? tests/junk erin?), of de package vanuit de wheel in een schone omgeving importeert en werkt (\`uv run --isolated --with <wheel> python -c ...\`), release.yml (publiceert hij naar PyPI, trusted publishing?), CHANGELOG-discipline, naamruimte/naam-botsing op PyPI. Wat blokkeert \`pip install gwsw-orox-helpers\` voor een vreemde?` },
  { key: 'api-docs', prompt: `LENS: PUBLIEKE API & documentatie als product. Beoordeel wat een afnemer ziet zonder de broncode: README (installatie, quickstart, klopt de code erin?), docstrings van de publieke functies, typehints en retourtypen, foutklassen (errors.py) en of ze gedocumenteerd zijn, verrassende defaults, parameters die nlriochecker-specifiek ruiken, Engels/Nederlands-consistentie. Zoek concrete plekken waar een nieuwe gebruiker vastloopt of verkeerd gebruikt.` },
  { key: 'security', prompt: `LENS: SECURITY op onvertrouwde invoer (alle IO-paden: bestand, inlezen, cache, schrijven, clip). Jaag op: pickle-deserialisatie van cachebestanden die een aanvaller kan planten, path-traversal via namen uit de data of cache-sleutels, XML/RDF-entiteitsuitbreiding in GML of RDF/XML, geheugen-/tijdsuitputting op vijandige TTL zonder plafond, symlink-volging bij schrijven, secrets/artefacten in de repo-historie. Lever een concrete aanvalsinvoer en draai hem.` },
  { key: 'defecten-lezen', prompt: `LENS: DEFECTEN in het leespad (bestand, inlezen, rdfmotor, dataset, cache). Jaag op: TTL-randgevallen (lege graaf, BOM, dubbele of ontbrekende prefix, 1.7-prefix met 1.6-termen, blank nodes, taaltags/datatypes), verschillen tussen het pyoxigraph- en rdflib-pad op dezelfde invoer, stale of botsende cache (zelfde naam andere inhoud, oudere pickle-schemaversie, half geschreven cache na crash), lui vs eager pad dat afwijkt.` },
  { key: 'defecten-geo-clip', prompt: `LENS: DEFECTEN in geometrie, clip, merge en schrijver. Beloftes: merge(clip(bron)) ≡ bron en de schrijver regenereert inhoudelijk identiek. Jaag op: GML-varianten (posList/pos/coordinates, srsDimension=3, ontbrekende srsName, lege ringen), Z-verlies, precisieverlies, quads/knopen die wegvallen of dubbel komen aan de clipgrens, literal-escaping (quotes, backslash, newline, unicode), datatypes/taaltags die verdwijnen, volgorde-niet-determinisme tussen runs (draai twee keer met verschillende PYTHONHASHSEED).` },
  { key: 'architectuur-snit', prompt: `LENS: ARCHITECTUUR — de snit zoals hij nu is. Toets docs/architectuur.md aan de code: klopt de importrichting tussen de lagen (draai een importgraaf, bv. grep op 'from gwsw_orox_helpers' per module), is de clip/-package echt langs zijn fasen gesneden, dragen rdfmotor en het GraafLezer-protocol de pyoxigraph/rdflib-naad volledig of lekt die nog elders, waar is dataset (984) of inlezen (794) nog een god-module met meerdere redenen om te veranderen, en waar woont dezelfde IRI-/prefix-/coderingskennis op twee plekken. Bewijs per punt met bestand:regel; benoem ook wat goed is, zodat de regisseur weet wat hij niet hoeft aan te raken.` },
  { key: 'architectuur-evolutie', prompt: `LENS: ARCHITECTUUR — evolueerbaarheid en diepe modules. Beoordeel de package zoals een auteur van een bibliotheek die nog jaren mee moet: zijn de publieke modules diep (smalle interface, veel verborgen complexiteit) of ondiep (veel kleine functies die de aanroeper moet samenstellen)? Wat kost een GWSW 1.8, een derde gebundelde ontologie, een pyoxigraph 1.0 of rdflib 8 concreet in aantal te wijzigen bestanden? Is de cache-laag als seam bruikbaar voor een andere backend? Waar dwingt de bevroren nlriochecker-API een ontwerp af dat je additief kunt laten groeien naar een schonere 1.0-API, en hoe zou dat migratiepad eruitzien (voorstel-voor-de-auteur, raaktContract=true)? Bewijs met bestand:regel en concrete telling.` },
  { key: 'kwaliteit', prompt: `LENS: CODEKWALITEIT & robuustheid zoals een strenge reviewer van een professionele bibliotheek die leest. Foutafhandeling (kale except, verzwolgen uitzonderingen, uitzonderingen buiten de DatasetError-familie), logging-hygiene (print? logger-namen? warnings-spam), resource-lekken (open handles, tmp-bestanden), threading/proces-veiligheid van de cache, dode code, typehints die liegen (Any, cast, type: ignore), inconsistentie tussen modules. Bewijs met bestand:regel.` },
  { key: 'tests-ci', prompt: `LENS: TESTS & CI als kwaliteitsbewijs. Dekt 95% de kritieke paden echt? Zoek zwakke asserties, tests die de implementatie kopieren, ontbrekende negatieve tests, fixture-drift, flaky-risico (tmp, volgorde, tijd), en of de CI (toets.yml, release.yml) een vreemde bijdrager beschermt: matrix, locked install, wheel-rooktest, publicatie. Bewijs met bestand:regel of een commando-uitvoer.` },
]

const RECS_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['bevindingen'],
  properties: {
    bevindingen: {
      type: 'array', maxItems: 5,
      items: {
        type: 'object', additionalProperties: false,
        required: ['title', 'soort', 'probleem', 'bewijs', 'zekerheid', 'ernst', 'bestanden', 'fixrichting', 'raaktContract'],
        properties: {
          title: { type: 'string' },
          soort: { type: 'string', enum: ['defect', 'security', 'packaging', 'architectuur', 'kwaliteit'] },
          probleem: { type: 'string', description: 'verwacht vs werkelijk, concreet' },
          bewijs: { type: 'string', description: 'repro-pad + commando + geplakte uitvoer, of bestand:regel-citaat' },
          zekerheid: { type: 'string', enum: ['aangetoond', 'vermoeden'] },
          ernst: { type: 'string', enum: ['laag', 'midden', 'hoog', 'kritiek'], description: 'kritiek = blokkeert een professionele PyPI-release' },
          bestanden: { type: 'array', items: { type: 'string' } },
          fixrichting: { type: 'string', description: 'kortste additieve fix' },
          raaktContract: { type: 'boolean' },
        },
      },
    },
  },
}

const VERDICT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['isEcht', 'bewijsGecontroleerd', 'additief', 'ernst', 'redenering'],
  properties: {
    isEcht: { type: 'boolean', description: 'true alleen als jij het zelf reproduceerde of het bewijs in de code bevestigde' },
    bewijsGecontroleerd: { type: 'boolean' },
    additief: { type: 'boolean', description: 'fix mogelijk zonder bevroren contract te breken' },
    ernst: { type: 'string', enum: ['laag', 'midden', 'hoog', 'kritiek'], description: 'jouw eigen inschatting, niet die van de vinder' },
    redenering: { type: 'string' },
  },
}

const PLAN_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['releaseKlaar', 'blokkers', 'architectuurOordeel', 'aanbevelingen', 'themas', 'slotnoot'],
  properties: {
    releaseKlaar: { type: 'boolean', description: 'is 0.2.2 vandaag als professionele PyPI-release te verdedigen?' },
    blokkers: { type: 'array', items: { type: 'string' }, description: 'wat MOET voor de eerste PyPI-publicatie' },
    architectuurOordeel: {
      type: 'object', additionalProperties: false,
      required: ['cijfer', 'sterk', 'zwak', 'richting10'],
      properties: {
        cijfer: { type: 'integer', minimum: 1, maximum: 10, description: 'architectuur als geheel, 10 = voorbeeldig' },
        sterk: { type: 'array', items: { type: 'string' }, description: 'wat de auteur moet bewaren' },
        zwak: { type: 'array', items: { type: 'string' }, description: 'de structurele zwaktes, met bestand' },
        richting10: { type: 'string', description: 'het pad van dit cijfer naar een 9-10, additief waar het kan, contract-rakers benoemd' },
      },
    },
    aanbevelingen: {
      type: 'array', maxItems: 20,
      items: {
        type: 'object', additionalProperties: false,
        required: ['rang', 'titel', 'soort', 'ernst', 'lens', 'bewijs', 'fixrichting', 'additief', 'inspanning', 'bestanden'],
        properties: {
          rang: { type: 'integer' },
          titel: { type: 'string' },
          soort: { type: 'string', enum: ['defect', 'security', 'packaging', 'architectuur', 'kwaliteit'] },
          ernst: { type: 'string', enum: ['laag', 'midden', 'hoog', 'kritiek'] },
          lens: { type: 'string' },
          bewijs: { type: 'string' },
          fixrichting: { type: 'string' },
          additief: { type: 'boolean' },
          inspanning: { type: 'string', enum: ['S', 'M', 'L', 'XL'] },
          bestanden: { type: 'array', items: { type: 'string' } },
        },
      },
    },
    themas: { type: 'array', items: { type: 'string' } },
    slotnoot: { type: 'string', description: 'contract-rakers voor de auteur; wat een agent additief mag oppakken' },
  },
}

// Auditstap als losse functie: byte-identieke prompt/opts, zodat een latere volledige run
// met resumeFromRunId de auditresultaten uit de cache haalt.
const auditeer = (d) => agent(
  `${CONTEXT}\n\n${d.prompt}\n\nLever maximaal 5 bevindingen; liever 2 aangetoonde dan 5 vermoedens. Werkmap voor repro's/builds: ${SCRATCH}/${d.key}/.`,
  { label: `audit:${d.key}`, phase: 'Audit', model: 'fable', schema: RECS_SCHEMA, effort: 'high' },
)

phase('Audit')
log(`Fable-audit: ${DIMENSIONS.length} lenzen, repro's en builds in ${SCRATCH}`)

// args.stap === 'audit': alleen de 8 lens-agents, geen verify/regie (kostenmeting).
if (args && args.stap === 'audit') {
  const ruw = await parallel(DIMENSIONS.map((d) => () => auditeer(d).then((r) => ({ lens: d.key, ...(r || { bevindingen: [] }) }))))
  const n = ruw.filter(Boolean).reduce((s, r) => s + r.bevindingen.length, 0)
  log(`Audit klaar: ${n} ruwe bevindingen, geen verify (stap=audit)`)
  return { stap: 'audit', ruw: ruw.filter(Boolean) }
}

const reviewed = await pipeline(
  DIMENSIONS,
  auditeer,
  (review, d) => parallel(((review && review.bevindingen) || []).map((r, i) => () =>
    agent(
      `${CONTEXT}\n\nJij bent de SKEPTICUS. Probeer deze bevinding te weerleggen (lens ${d.key}).\nTITEL: ${r.title}\nSOORT: ${r.soort}\nPROBLEEM: ${r.probleem}\nGECLAIMD BEWIJS: ${r.bewijs}\nCLAIM ernst=${r.ernst}, zekerheid=${r.zekerheid}, raaktContract=${r.raaktContract}.\n\nBij defect/security: draai de repro zelf (of schrijf een betere in ${SCRATCH}/verify-${d.key}-${i}/). Bij packaging/architectuur/kwaliteit: controleer het citaat of commando in de echte code. Is het echt fout, of gedocumenteerd, bedoeld, al gedekt door een test, of al gedaan in #1-#39? Is de fix additief? isEcht=true ALLEEN als jij het zelf bevestigde.`,
      { label: `verify:${d.key}:${i}`, phase: 'Verify', model: 'fable', schema: VERDICT_SCHEMA, effort: 'medium' },
    ).then((v) => (v ? { ...r, lens: d.key, verdict: v } : null)),
  )),
)

const overleefd = reviewed.flat().filter(Boolean).filter((x) => x.verdict && x.verdict.isEcht)
const gesneuveld = reviewed.flat().filter(Boolean).length - overleefd.length
log(`Verify: ${overleefd.length} bevestigd, ${gesneuveld} afgevallen`)

phase('Regie')
const bundel = overleefd.map((x, i) => ({
  n: i + 1, lens: x.lens, soort: x.soort, titel: x.title, probleem: x.probleem, bewijs: x.bewijs,
  ernstVinder: x.ernst, ernstSkepticus: x.verdict.ernst, bestanden: x.bestanden,
  fixrichting: x.fixrichting, additief: x.verdict.additief, verifyNoot: x.verdict.redenering,
}))

const plan = await agent(
  `${CONTEXT}\n\nJij bent de REGISSEUR. ${bundel.length} bevestigde bevindingen uit 9 lenzen:\n\n${JSON.stringify(bundel, null, 1)}\n\nBeantwoord eerst: is 0.2.2 vandaag een verdedigbare professionele PyPI-release, en wat zijn de harde blokkers? Geef daarna een eigen architectuuroordeel (cijfer 1-10, wat sterk is en bewaard moet blijven, de structurele zwaktes, en het pad naar een 9-10); lees daarvoor zelf docs/architectuur.md en de importgraaf, leun niet alleen op de twee architectuurlenzen. Ontdubbel (zelfde oorzaak = een punt), rangschik op ernst x zekerheid met release-blokkers bovenaan, geef per punt de kortste additieve fixrichting en inspanning. Contract-rakers apart en achteraan. Benoem de rode draden en zet in de slotnoot wat de auteur zelf beslist versus wat een agent additief mag oppakken. Controleer twijfelgevallen zelf in de code.`,
  { label: 'regisseur:fable', phase: 'Regie', model: 'fable', schema: PLAN_SCHEMA, effort: 'high' },
)

return { bevestigd: overleefd.length, afgevallen: gesneuveld, plan }
