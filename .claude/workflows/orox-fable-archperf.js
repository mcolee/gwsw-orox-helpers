export const meta = {
  name: 'orox-fable-archperf',
  description: 'Fable 5.1-swarm op gwsw-orox-helpers, doel: architectuur en performance 50% beter; 10 lenzen met skills en bewijs/meting, adversariele verify, Fable-regisseur met 50%-plan',
  phases: [
    { title: 'Audit', detail: '5 architectuurlenzen (codebase-design, bestand:regel) + 5 performancelenzen (profiel, gepaarde meting, klasse-C-prototype)', model: 'fable' },
    { title: 'Verify', detail: 'Fable-skepticus controleert het citaat of draait de meting na', model: 'fable' },
    { title: 'Regie', detail: 'Fable-regisseur: architectuur- en performance-oordeel, 50%-plan per pad, <=20 aanbevelingen', model: 'fable' },
  ],
}

// Optioneel: args = { scratch: '<map voor repro-/meetscripts>' }
const SCRATCH = (args && args.scratch) || '/tmp/orox-fable-archperf'

const CONTEXT = `
Repo-root (cwd): /home/martin/gwsw-orox-helpers  (Python 3.12+, src-layout, uv, versie 0.2.2, dev=2d4ae46).
Package: src/gwsw_orox_helpers/ — leeslaag voor GWSW-OroX (TTL) rioleringsdata.
Modules (LOC): dataset 1081, inlezen 812, cache 630, schrijven 420, clip/ (knip 334, plan 318,
merge 294, bereik 196, __init__ 188, stroom 151, orkest 129, termen 120, grenzen 98), graaf 325,
domein 277, geometry 266, ontologie 231, namen 219, netwerk 210, rdfmotor 191, errors 186,
bestand 181, klassen 142, codering 131, bronnen 78, voortgang 59.
Deps: pyoxigraph>=0.5 (Rust-parser), rdflib>=7.0, shapely>=2.0. Gebundelde data: twee
GWSW-ontologieen (TTL, 1.6 en 1.7) en twee vocabulaire-indexen (JSON) in src/gwsw_orox_helpers/data/.
Lees docs/architectuur.md (549 regels) eerst en volledig; lees elk bestand dat je beoordeelt EEN
KEER VOLLEDIG met Read. Geen cd; werkmap is de repo-root. Draai NIET de volledige testsuite.
Wijzig NIETS in de repo; alles wat je schrijft gaat naar ${SCRATCH}/<lens>/ (maak de map aan).

DOEL VAN DE AUTEUR: architectuur EN performance 50% BETER maken. Concreet:
- performance: de wandkloktijd van een heet pad halveren (load ~20 s -> ~10 s, clip ~39 s ->
  ~20 s, merge, schrijf) of de piek halveren; per pad tegen de gemeten Rust-vloer.
- architectuur: de wijzigingsmoeite halveren (helft van de bestanden/regels voor een
  evolutiescenario), de god-modules halveren, of het oppervlak dat een afnemer moet leren
  halveren — met een telling voor en na.
Het onderzoek van 28-08 liet zien dat 50% met klasse A (lokale optimalisatie) en B (datastructuur
binnen de module) NIET haalbaar is. Klasse C — een andere route door de motoren, een ander
tussenformaat, een andere snit — is daarom nadrukkelijk TOEGESTAAN en gewenst, mits gelabeld
(klasse A/B/C) en met raaktContract eerlijk gezet. Liever een gemeten klasse-C-route van 40%
dan drie ongemeten klasse-A-ideeen van 5%.
Deze swarm gaat UITSLUITEND over architectuur en performance. Security, packaging, docs, tests
en CI zijn al geaudit (issues #41-#58, afgehandeld) en tellen hier NIET; een bevinding buiten
architectuur/performance wordt door de skepticus afgekeurd.

SKILLS: laad met de Skill-tool voordat je begint de skill(s) die in je lens staan, en gebruik
hun vocabulaire en methode (deep module / interface / seam / adapter; profiel voor
hypothese; diagnoselus: meten -> hypothese -> experiment -> meten). Ontbrekende tools als
pyinstrument of memray draai je met \`uv run --with pyinstrument ...\` (niet installeren in
de repo).

HARDE CONTEXTREGELS (CLAUDE.md):
- Twee gebundelde GWSW-versies: 1.6 (default/leidend) en 1.7; versiedetectie uit de gwsw:-prefix;
  publieke leesweg GwswDataset.gwsw_versie.
- De publieke API die nlriochecker importeert is BEVROREN: clip_orox, merge_orox, lees_orox,
  schrijf_orox, schrijf_orox_quads (uit __init__) EN de leeslaag dataset/cache/geometry; het
  oppervlak staat gepind in tests/test_publieke_api.py. Een bevinding die dat raakt is een
  VOORSTEL-VOOR-DE-AUTEUR (raaktContract=true) — wel opnemen, wel labelen.
- docs/architectuur.md draagt beloftes: importrichting tussen lagen, twee paden door pyoxigraph
  (lezen met index, schrijven als stroom), "de schrijfweg is lui", dataset is het gezicht en niet
  de bak, de cache leest mee met de lader. Toets de code aan die beloftes en de beloftes aan de
  code; beide richtingen kunnen fout zijn.

WAT AL GEDAAN OF ONDERZOCHT IS (niet opnieuw voorstellen; wel voortbouwen):
- Gesloten issues #1-#39 en #41-#58: clip/-package-splitsing, is_a-memo, een-pass GML-lezer,
  _oxigraph-adapter (rdfmotor), GraafLezer-protocol, DatasetError-familie, dedup-generator,
  netwerk-module, hete lezers bouwen termen niet per aanroep (#23), graph_types_of-microbench,
  GWSW 1.7 dual-version (#32), gwsw_versie-accessor (#39), cache-rechtencheck (#45),
  wortel-AST-test op de lagentekening (#57), opt-in deterministische schrijver (#58).
- Versnellingsonderzoek 28-08-2026 op de 112 MB-export (rapport en meetstraat in
  ~/.local/share/Trash/files/gwsw-orox-helpers-onderzoek/2026-08-28-50procent/ (sinds 05-09 in de prullenbak): RAPPORT.md, meet.sh, gelijk.py,
  profielen/, prototypes/ — lees RAPPORT.md voordat je een perf-hypothese bouwt):
  load_dataset +8-9% (GC uit over load_dataset; snelpad in graaf.naar_rdflib); twee routes waren
  REGRESSIES (pyoxigraph-termen in de index −21%, tuple-cachesleutel in vul_uit −9%);
  schrijf_orox zit op de Rust-vloer (kale pyoxigraph parse→serialize 6,3 s van ~7 s);
  clip_orox +38% door de bron 1x i.p.v. N+1x te lezen, prijs +891 MiB piek en het omkeren
  van de "schrijfweg is lui"-belofte (auteursbeslissing, nog open).
- Laadtijd-historie: ~2 min → 20,3 s (#4) → −7,9% (#7). Huidig: load ~20 s, clip ~39 s,
  piek < 1,3 GB op 23.485 knopen / 23.440 strengen / 1,88 M triples.

MEETPROTOCOL (performance-lenzen):
- Export: ~/Development/nlriochecker/data/gwsw_orox_ttl/dewoldenhoogeveen_orox.ttl (112 MB, cp850-bytes in
  een straatnaam; scripts/benchmark.py regelt de codering). Grenzen:
  tests/fixtures/gis/gemeentegrenzen_dewoldenhoogeveen.geojson.
- Meetstraat: \`uv run python scripts/benchmark.py --paden <pad> --herhalingen 3 --json ${SCRATCH}/<lens>/x.json\`
  en \`--profiel-map ${SCRATCH}/<lens>/profielen\` voor cProfile; scripts/benchmark_is_a.py,
  benchmark_gml.py, benchmark_graph_types_of.py voor microbenchmarks. Lees scripts/benchmark.py
  eerst (--help) voor de exacte vlaggen.
- De machine heeft 4 cores en 15 GB en is NIET stil: andere agents draaien tegelijk. Daarom:
  (a) hotspot-claims komen uit een PROFIEL (cumulatieve tijd per functie, geplakt), niet uit
  wandklok; (b) een versnellingsclaim is alleen 'aangetoond' als hij GEPAARD is gemeten
  (referentie en experiment om en om, n>=3) en EENDUIDIG (traagste experiment sneller dan
  snelste referentie) — anders zekerheid='vermoeden' met de ruwe cijfers erbij; (c) gebruik
  \`flock ${SCRATCH}/meet.lock\` om je meting te serialiseren tegen andere lenzen, zoals
  meet.sh in het onderzoek van 28-08 doet.
- Een prototype schrijf je als monkeypatch of kopie in ${SCRATCH}/<lens>/, NOOIT in src/.
- Geheugen: ru_maxrss uit benchmark.py (Rust/GEOS alloceren buiten tracemalloc om).

BEWIJSPLICHT. Elke bevinding heeft een 'soort':
- architectuur: bewijs is een exact bestand:regel-citaat, een importgraaf-uitvoer (bv.
  \`grep -n 'from gwsw_orox_helpers\\|^import gwsw_orox_helpers\\|^from \\.' src/gwsw_orox_helpers/*.py src/gwsw_orox_helpers/clip/*.py\`),
  of een concrete telling (aantal te wijzigen bestanden voor scenario X).
- performance: bewijs is een profiel-uittreksel of een gepaarde meting met de ruwe getallen.
Meningen en "zou mooier kunnen" tellen niet; "dit kost een afnemer aantoonbaar tijd, geheugen
of wijzigingsmoeite" telt wel, mits met bewijs. Benoem ook wat GOED is: de regisseur moet
weten wat hij niet mag aanraken.`

const ARCH_SKILLS = 'SKILLS voor deze lens: mattpocock-skills:codebase-design (deep modules, seams, adapters) — laad hem eerst.'
const EVO_SKILLS = 'SKILLS voor deze lens: mattpocock-skills:codebase-design en mattpocock-skills:domain-modeling (begrippenmodel, ADR-denken) — laad ze eerst.'
const PERF_SKILLS = 'SKILLS voor deze lens: python-library-quality:optimizing-python-performance (profileren, memray/tracemalloc, benchmarken) en mattpocock-skills:diagnosing-bugs (de diagnoselus voor traagheid: meten -> hypothese -> experiment -> meten) — laad ze eerst.'

const DIMENSIONS = [
  { key: 'arch-afnemer', prompt: `${ARCH_SKILLS}\nLENS: ARCHITECTUUR — het interface gezien vanuit de afnemer. De enige afnemer staat lokaal: ~/Development/nlriochecker/src/nlriochecker/ (grep daar op 'from gwsw_orox_helpers' — 20+ importplekken, vooral dataset: Conduit, Node, GwswDataset, part_holders_of, aspect_holders_of, parts_of, HAS_CONNECTION, GWSW, Inwinning, markeer_vulwaarden; cache: laad_met_cache, CacheUitslag; voortgang). Lees die afnemerbestanden (een keer volledig) en beoordeel de diepte van het interface: hoeveel moet nlriochecker weten (IRI-constanten, RdfNode, losse module-functies naast methoden) om een check te schrijven, welke samenstellingen herhaalt de afnemer zelf die de bibliotheek had moeten dragen (patronen die 3x+ terugkomen), en welke leaks van implementatie (rdflib-termen, pyoxigraph, pickle) bereiken de afnemer? Tel het oppervlak dat de afnemer nu leert en schets een dieper interface dat het halveert — additief naast het bevroren oppervlak (raaktContract=true waar het pin raakt). Bewijs: bestand:regel in beide repo's en de telling.` },
  { key: 'arch-lagen', prompt: `${ARCH_SKILLS}\nLENS: ARCHITECTUUR — lagen, importrichting en verantwoordelijkheden. Bouw de importgraaf van alle 27 modules (grep, zie context) en leg hem naast de lagentekening in docs/architectuur.md en de wortel-AST-test uit #57 (tests/, zoek 'lagentekening' of 'wortel'). Waar loopt een import tegen de richting in, waar draagt een module meer dan een reden om te veranderen (dataset 1081, inlezen 812, cache 630: welke verantwoordelijkheden zitten erin, met regelbereiken), en waar woont dezelfde IRI-/prefix-/coderings-/termenkennis op twee plekken (namen, termen, codering, rdfmotor, ontologie)? Lever per punt bestand:regel en zeg wat een additieve hersnit zou zijn.` },
  { key: 'arch-naden', prompt: `${ARCH_SKILLS}\nLENS: ARCHITECTUUR — de naden naar de motoren en de cache. Beoordeel of rdfmotor + het GraafLezer-protocol de pyoxigraph/rdflib-naad VOLLEDIG dragen: grep naar 'pyoxigraph', 'rdflib', 'oxigraph' buiten rdfmotor/graaf en beoordeel elke treffer. Beoordeel of de cache-laag (cache.py, bestand.py) een echte seam is: kan er een andere backend of een ander formaat dan pickle achter zonder dataset/inlezen aan te raken? Hoe zit de lui-vs-eager-splitsing (graafpickle niet laden op het luie pad) in de code, en is de invalidatie (LADER_VERSIE, bronvingerafdruk, ontologieversie) op een plek gedefinieerd? Toets de belofte 'de cache leest mee met de lader' aan de code. Bewijs: bestand:regel.` },
  { key: 'arch-evolutie', prompt: `${EVO_SKILLS}\nLENS: ARCHITECTUUR — evolueerbaarheid en diepe modules. Tel concreet wat een GWSW 1.8, een derde gebundelde ontologie, pyoxigraph 1.0 en rdflib 8 kosten in te wijzigen bestanden en regels (noem ze). Zijn de publieke modules diep (smalle interface, veel verborgen complexiteit) of ondiep? Waar dwingt het bevroren nlriochecker-oppervlak (tests/test_publieke_api.py) een ontwerp af dat alleen additief kan groeien, en hoe ziet een schone 1.0-laag naast de bevroren laag eruit (raaktContract=true waar het pin raakt)? Wat is de rol van domein.py, klassen.py, ontologie.py en netwerk.py ten opzichte van elkaar: is er een begrippenmodel dat op een plek woont? Bewijs: bestand:regel en tellingen.` },
  { key: 'arch-clip-schrijf', prompt: `${ARCH_SKILLS}\nLENS: ARCHITECTUUR — de clip/-package en de schrijfweg. Is clip/ echt langs zijn fasen gesneden (plan → bereik → knip → stroom → merge, orkest erbovenop)? Volg de dataflow van clip_orox en merge_orox door de modules: welke tussenstructuren reizen mee, waar wordt state gedeeld, waar leest een fase de bron opnieuw (het N+1-lezen uit het 28-08-rapport: is dat een ontwerpkeuze die in architectuur.md staat of een toevalligheid)? Beoordeel schrijven.py als stroom: is de belofte 'schrijfweg is lui' waar in de code, en draagt de deterministische modus (#58) die belofte of breekt hij hem? Bewijs: bestand:regel.` },
  { key: 'perf-laadpad', prompt: `${PERF_SKILLS}\nLENS: PERFORMANCE — het laadpad (load_dataset, koud: cache leeg). Profileer met scripts/benchmark.py --profiel-map en lees het cProfile-profiel: wat zijn de top-10 cumulatieve hotspots boven de pyoxigraph-parse, en welk deel van de ~20 s is Python-overhead versus Rust-vloer (meet de kale pyoxigraph-parse van de export los als vloer)? Zoek algoritmische verspilling in inlezen/dataset/graaf: per-knoop lookups die een index zouden kunnen zijn, herhaalde IRI-string-bewerkingen, tussenlijsten, objectconstructie (RdfNode/dataclasses) per triple. Bouw hooguit EEN prototype als monkeypatch in ${SCRATCH}/perf-laadpad/ en meet gepaard achter flock. Lees eerst RAPPORT.md van 28-08 zodat je de +8% en de twee regressies niet herhaalt.` },
  { key: 'perf-clip-merge', prompt: `${PERF_SKILLS}\nLENS: PERFORMANCE — clip_orox en merge_orox (~39 s, piek < 1,3 GB). Profileer beide via scripts/benchmark.py --profiel-map. Waar gaat de tijd heen: bron opnieuw lezen per deel (N+1), shapely-predicaten per geometrie (is er een STRtree of wordt elke geometrie tegen elke grens getoetst?), pyoxigraph-queries per fase, serialisatie? Wat is de complexiteit in het aantal delen k (meet met 2 en met alle grenzen als dat kan) en in het aantal knopen? Het 28-08-rapport gaf +38% door rijen te cachen tegen +891 MiB: is er een route die de N+1 vermijdt ZONDER de lui-belofte te breken (bv. een pass die alleen de toewijzing knoop→deel bewaart)? Prototype in ${SCRATCH}/perf-clip-merge/, gepaard meten achter flock.` },
  { key: 'perf-warm-en-cache', prompt: `${PERF_SKILLS}\nLENS: PERFORMANCE — het warme pad en de cache. Meet load_dataset met warme cache (tweede run) versus koud: hoe groot is de pickle, hoe lang duurt unpickle + rehydratie, en welk deel daarvan is vermijdbaar (bv. graafpickle die op het luie pad toch geladen wordt, dubbele structuren in de pickle, shapely-geometrieen die opnieuw geparsed worden)? Profileer de checkfase-achtige toegang die nlriochecker doet: is_a/of_class/graph_types_of/kenmerken-lookup per knoop over alle 46.925 objecten (scripts/benchmark_is_a.py, benchmark_graph_types_of.py). Zoek O(n^2)- of herhaalde-lineaire-scans in dataset.py/graaf.py/klassen.py/netwerk.py op het warme pad. Bewijs: profiel of gepaarde meting achter flock; prototypes in ${SCRATCH}/perf-warm-en-cache/.` },
  { key: 'perf-klasse-c', prompt: `${PERF_SKILLS} Plus mattpocock-skills:codebase-design voor de seam-vraag.\nLENS: PERFORMANCE — klasse-C-routes: een andere weg door de motoren. Het rapport van 28-08 concludeert dat 50% alleen met klasse C kan. Ontwerp en MEET er minstens een, als throwaway-prototype in ${SCRATCH}/perf-klasse-c/ (nooit in src/). Kandidaten: (1) de index niet uit Python-iteratie over quads bouwen maar uit een handvol SPARQL-queries op de pyoxigraph-store (of pyoxigraph's eigen serialisatie naar een kolomformaat); (2) rdflib volledig van het leespad halen (waar wordt naar_rdflib nog aangeroepen en wat kost dat, meet het); (3) de schrijfweg via pyoxigraph's parse→serialize met een filter in Rust-land i.p.v. Python-iteratie per quad; (4) geometrie in bulk via shapely.from_wkt/from_ragged_array op arrays i.p.v. per-object; (5) de cache als pyoxigraph-store op schijf (of een compact tussenformaat) i.p.v. pickle van Python-objecten. Kies op basis van het profiel de een of twee met het meeste potentieel, bouw ze minimaal, meet gepaard achter flock tegen de referentie, en rapporteer eerlijk: gemeten winst, wat het aan geheugen kost, welke seam (rdfmotor? cache? inlezen?) het raakt en of het bevroren oppervlak intact blijft. Een negatieve uitkomst (route X geeft niets) is ook een bevinding met bewijs.` },
  { key: 'perf-geheugen-schaal', prompt: `${PERF_SKILLS}\nLENS: PERFORMANCE — geheugen en schaalbaarheid. Meet ru_maxrss per pad (benchmark.py --json) en verklaar de piek: welke structuren houden de 1,88 M triples in Python-objecten vast naast de pyoxigraph-store (dubbele representatie?), wat kost een knoop/streng in bytes (sys.getsizeof-boom of tracemalloc-snapshot op een subset), en waar leeft de graaf twee keer (index + rdflib-graaf via naar_rdflib?). Extrapoleer naar een 5x grotere export (Rotterdam-schaal, ~500 MB): welk pad breekt eerst en waarom (geheugen, kwadratisch, cache-pickle)? Zoek generatoren die naar lijsten worden gematerialiseerd en structuren die na de bouw niet meer nodig zijn maar blijven leven. Bewijs: meting of profiel; prototypes in ${SCRATCH}/perf-geheugen-schaal/.` },
]

const RECS_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['bevindingen', 'sterkePunten'],
  properties: {
    sterkePunten: { type: 'array', items: { type: 'string' }, description: 'wat aantoonbaar goed is en bewaard moet blijven, met bestand:regel of meting' },
    bevindingen: {
      type: 'array', maxItems: 5,
      items: {
        type: 'object', additionalProperties: false,
        required: ['title', 'soort', 'probleem', 'bewijs', 'zekerheid', 'ernst', 'bestanden', 'fixrichting', 'winst', 'raaktContract'],
        properties: {
          title: { type: 'string' },
          soort: { type: 'string', enum: ['architectuur', 'performance'] },
          probleem: { type: 'string', description: 'verwacht vs werkelijk, concreet' },
          bewijs: { type: 'string', description: 'bestand:regel-citaat, importgraaf-uitvoer, profiel-uittreksel of gepaarde meting met ruwe getallen' },
          zekerheid: { type: 'string', enum: ['aangetoond', 'vermoeden'] },
          ernst: { type: 'string', enum: ['laag', 'midden', 'hoog', 'kritiek'], description: 'architectuur: hoe duur wordt een toekomstige wijziging; performance: hoeveel tijd/geheugen kost het een afnemer' },
          bestanden: { type: 'array', items: { type: 'string' } },
          fixrichting: { type: 'string', description: 'kortste additieve fix' },
          winst: { type: 'string', description: 'performance: gemeten of geschatte winst (%, s, MiB) met de meetbasis; architectuur: wat er goedkoper wordt' },
          raaktContract: { type: 'boolean' },
        },
      },
    },
  },
}

const VERDICT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['isEcht', 'bewijsGecontroleerd', 'binnenScope', 'additief', 'ernst', 'redenering'],
  properties: {
    isEcht: { type: 'boolean', description: 'true alleen als jij het citaat/de meting zelf bevestigde' },
    bewijsGecontroleerd: { type: 'boolean' },
    binnenScope: { type: 'boolean', description: 'gaat dit echt over architectuur of performance (niet security/packaging/docs/tests)' },
    additief: { type: 'boolean', description: 'fix mogelijk zonder bevroren contract te breken' },
    ernst: { type: 'string', enum: ['laag', 'midden', 'hoog', 'kritiek'], description: 'jouw eigen inschatting, niet die van de vinder' },
    redenering: { type: 'string' },
  },
}

const PLAN_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['architectuurOordeel', 'performanceOordeel', 'plan50', 'aanbevelingen', 'themas', 'slotnoot'],
  properties: {
    plan50: {
      type: 'array', description: 'per doel (load, clip, merge, schrijf, geheugen, wijzigingsmoeite, afnemer-oppervlak) de route naar 50%: haalbaar ja/nee, gemeten basis, samengestelde ingrepen met klasse A/B/C, verwachte optelsom, contract-rakers',
      items: {
        type: 'object', additionalProperties: false,
        required: ['doel', 'nu', 'streef', 'haalbaar', 'route', 'klasse', 'raaktContract', 'eerlijkeNoot'],
        properties: {
          doel: { type: 'string' },
          nu: { type: 'string', description: 'gemeten uitgangswaarde met bron' },
          streef: { type: 'string' },
          haalbaar: { type: 'string', enum: ['ja-gemeten', 'ja-aannemelijk', 'deels', 'nee'] },
          route: { type: 'array', items: { type: 'string' }, description: 'ingrepen in volgorde, elk met verwachte bijdrage en aanbevelingsrang' },
          klasse: { type: 'string', enum: ['A', 'B', 'C', 'B+C', 'A+B+C'] },
          raaktContract: { type: 'boolean' },
          eerlijkeNoot: { type: 'string', description: 'wat onzeker is, wat het kost (geheugen, belofte in architectuur.md, auteursbeslissing)' },
        },
      },
    },
    architectuurOordeel: {
      type: 'object', additionalProperties: false,
      required: ['cijfer', 'sterk', 'zwak', 'richting10'],
      properties: {
        cijfer: { type: 'integer', minimum: 1, maximum: 10 },
        sterk: { type: 'array', items: { type: 'string' }, description: 'wat de auteur moet bewaren' },
        zwak: { type: 'array', items: { type: 'string' }, description: 'de structurele zwaktes, met bestand' },
        richting10: { type: 'string', description: 'het pad naar een 9-10, additief waar het kan, contract-rakers benoemd' },
      },
    },
    performanceOordeel: {
      type: 'object', additionalProperties: false,
      required: ['cijfer', 'vloer', 'grootsteWinst', 'schaalgrens'],
      properties: {
        cijfer: { type: 'integer', minimum: 1, maximum: 10, description: '10 = op de Rust-vloer, geen Python-verspilling' },
        vloer: { type: 'string', description: 'per pad: gemeten Rust-vloer versus huidige tijd, en dus de theoretische ruimte' },
        grootsteWinst: { type: 'string', description: 'de een of twee ingrepen met de meeste gemeten winst per uur werk' },
        schaalgrens: { type: 'string', description: 'wat breekt eerst bij 5x data, en wat dat vergt' },
      },
    },
    aanbevelingen: {
      type: 'array', maxItems: 20,
      items: {
        type: 'object', additionalProperties: false,
        required: ['rang', 'titel', 'soort', 'ernst', 'lens', 'bewijs', 'fixrichting', 'winst', 'additief', 'inspanning', 'bestanden'],
        properties: {
          rang: { type: 'integer' },
          titel: { type: 'string' },
          soort: { type: 'string', enum: ['architectuur', 'performance'] },
          ernst: { type: 'string', enum: ['laag', 'midden', 'hoog', 'kritiek'] },
          lens: { type: 'string' },
          bewijs: { type: 'string' },
          fixrichting: { type: 'string' },
          winst: { type: 'string' },
          additief: { type: 'boolean' },
          inspanning: { type: 'string', enum: ['S', 'M', 'L', 'XL'] },
          bestanden: { type: 'array', items: { type: 'string' } },
        },
      },
    },
    themas: { type: 'array', items: { type: 'string' } },
    slotnoot: { type: 'string', description: 'contract-rakers en auteursbeslissingen (o.a. de lui-belofte versus +38% clip); wat een agent additief mag oppakken' },
  },
}

const auditeer = (d) => agent(
  `${CONTEXT}\n\n${d.prompt}\n\nLever maximaal 5 bevindingen; liever 2 aangetoonde dan 5 vermoedens. Noem ook de sterke punten. Werkmap: ${SCRATCH}/${d.key}/.`,
  { label: `audit:${d.key}`, phase: 'Audit', model: 'fable', schema: RECS_SCHEMA, effort: 'high' },
)

phase('Audit')
log(`Fable-archperf: ${DIMENSIONS.length} lenzen (4 architectuur, 4 performance), werk in ${SCRATCH}`)

if (args && args.stap === 'audit') {
  const ruw = await parallel(DIMENSIONS.map((d) => () => auditeer(d).then((r) => ({ lens: d.key, ...(r || { bevindingen: [], sterkePunten: [] }) }))))
  const n = ruw.filter(Boolean).reduce((s, r) => s + r.bevindingen.length, 0)
  log(`Audit klaar: ${n} ruwe bevindingen, geen verify (stap=audit)`)
  return { stap: 'audit', ruw: ruw.filter(Boolean) }
}

const reviewed = await pipeline(
  DIMENSIONS,
  auditeer,
  (review, d) => parallel(((review && review.bevindingen) || []).map((r, i) => () =>
    agent(
      `${CONTEXT}\n\nJij bent de SKEPTICUS. Probeer deze bevinding te weerleggen (lens ${d.key}).\nTITEL: ${r.title}\nSOORT: ${r.soort}\nPROBLEEM: ${r.probleem}\nGECLAIMD BEWIJS: ${r.bewijs}\nGECLAIMDE WINST: ${r.winst}\nCLAIM ernst=${r.ernst}, zekerheid=${r.zekerheid}, raaktContract=${r.raaktContract}.\n\nBij architectuur: controleer elk citaat in de echte code, bouw zo nodig zelf de importgraaf of de telling na, en toets of docs/architectuur.md dit al als bewuste keuze benoemt. Bij performance: controleer het profiel of draai de gepaarde meting zelf na achter flock (werkmap ${SCRATCH}/verify-${d.key}-${i}/); een claim zonder eenduidige gepaarde meting is hooguit 'vermoeden' en dan isEcht alleen als het profiel de hotspot wel bewijst. Is het buiten scope (security/packaging/docs/tests), gedocumenteerd, bedoeld, of al gedaan/onderzocht (#1-#58, rapport 28-08)? Is de fix additief? isEcht=true ALLEEN als jij het zelf bevestigde.`,
      { label: `verify:${d.key}:${i}`, phase: 'Verify', model: 'fable', schema: VERDICT_SCHEMA, effort: 'medium' },
    ).then((v) => (v ? { ...r, lens: d.key, verdict: v } : null)),
  )).then((vs) => ({ lens: d.key, sterkePunten: (review && review.sterkePunten) || [], items: vs })),
)

const alle = reviewed.filter(Boolean)
const overleefd = alle.flatMap((r) => r.items).filter(Boolean).filter((x) => x.verdict && x.verdict.isEcht && x.verdict.binnenScope)
const gesneuveld = alle.flatMap((r) => r.items).filter(Boolean).length - overleefd.length
const sterk = alle.flatMap((r) => r.sterkePunten.map((s) => `[${r.lens}] ${s}`))
log(`Verify: ${overleefd.length} bevestigd, ${gesneuveld} afgevallen; ${sterk.length} sterke punten`)

phase('Regie')
const bundel = overleefd.map((x, i) => ({
  n: i + 1, lens: x.lens, soort: x.soort, titel: x.title, probleem: x.probleem, bewijs: x.bewijs,
  winst: x.winst, ernstVinder: x.ernst, ernstSkepticus: x.verdict.ernst, bestanden: x.bestanden,
  fixrichting: x.fixrichting, additief: x.verdict.additief, raaktContract: x.raaktContract,
  verifyNoot: x.verdict.redenering,
}))

const plan = await agent(
  `${CONTEXT}\n\nJij bent de REGISSEUR. ${bundel.length} bevestigde bevindingen uit 10 lenzen:\n\n${JSON.stringify(bundel, null, 1)}\n\nSTERKE PUNTEN volgens de lenzen:\n${sterk.map((s) => `- ${s}`).join('\n')}\n\nLaad eerst mattpocock-skills:codebase-design. Geef een eigen architectuuroordeel (cijfer 1-10, sterk/zwak, pad naar 9-10); lees daarvoor zelf docs/architectuur.md en bouw de importgraaf, leun niet alleen op de vijf architectuurlenzen. Geef een eigen performance-oordeel: per pad de Rust-vloer tegenover de huidige tijd (haal de cijfers uit de bevindingen en RAPPORT.md van 28-08; meet zelf alleen als een twijfelgeval het vereist), de een of twee ingrepen met de meeste gemeten winst per uur werk, en de schaalgrens bij 5x data. Stel dan het 50%-PLAN op: per doel (load, clip, merge, schrijf, piekgeheugen, wijzigingsmoeite, afnemer-oppervlak) de route naar 50%: welke ingrepen in welke volgorde, klasse A/B/C, of de optelsom gemeten of aannemelijk is, en eerlijk 'nee' waar 50% niet kan zonder de motoren te vervangen. Ontdubbel (zelfde oorzaak = een punt), rangschik op ernst x zekerheid x winst, geef per punt de kortste additieve fixrichting en inspanning. Contract-rakers en auteursbeslissingen (o.a. lui-belofte versus +38% clip) apart en achteraan. Benoem de rode draden; zet in de slotnoot wat de auteur zelf beslist versus wat een agent additief mag oppakken.`,
  { label: 'regisseur:fable', phase: 'Regie', model: 'fable', schema: PLAN_SCHEMA, effort: 'high' },
)

return { bevestigd: overleefd.length, afgevallen: gesneuveld, sterkePunten: sterk, plan }
