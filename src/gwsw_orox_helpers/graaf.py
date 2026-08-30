"""Eigen graafindexen als vervanger van de rdflib-store (`GwswDataset.graph`).

De rdflib-`Memory`-store bouwt drie geneste indexen (spo, pos, osp) met per triple
dict-in-dict-in-dict-overhead; op de De Wolden en Hoogeveen-export kostte dat minuten
opbouwtijd en gigabytes geheugen. De checks gebruiken maar een handvol leesbewerkingen,
allemaal met gebonden argumenten. `GraafIndex` draagt daarom precies twee indexen
(s->p->[o] en p->o->[s]), gevuld in stream-volgorde uit de pyoxigraph-parse, met
rdflib-termtypen (`URIRef`, `BNode`, `Literal`) als munteenheid zodat de aanroepende
code en alle vergelijkingen ongewijzigd blijven.

Geinventariseerde `Graph`-bewerkingen (stap 0; `grep -rn "\\.graph\\." src/` plus de
interne lezers van de leeslaag, die sinds de hersnit in `inlezen.py` en `klassen.py`
staan en niet meer in `dataset.py`) -- dit is het volledige leescontract, en de tests in
`tests/test_graaf.py` toetsen elk ervan tegen het rdflib-antwoord op dezelfde triples,
inclusief volgorde:

- ``objects(subject, predicate)`` -- beide gebonden. `dataset.py`
  (`GwswDataset.graph_types_of`), `inlezen.py`
  (`parts_of`/`aspects_of`/`part_holders_of`/`aspect_holders_of` -- met als externe
  aanroepers ook `checks/netwerk.py` en `checks/randvoorzieningen.py` -- ,
  `_read_aspects`, `_types`, `_connections`), `checks/administratief.py`
  (hasConnection), `nulbevinding.py` (`_ouders`) en de ontologielezers
  `ontologie.verwachte_property`, `functie_van_klasse` en `datatype_van_kenmerk` (de
  restrictiebron kan deze index zijn).
- ``subjects(predicate, object)`` -- beide gebonden. `dataset.py`
  (`GwswDataset.subjects_of_class`), `inlezen.py` (de vier hasPart/hasAspect-lezers --
  zie hierboven voor hun externe aanroepers -- , `_orientations_of_class`,
  `_orientations_with`, `_leiding_orientations`, `_connections`),
  `checks/administratief.py`, `checks/attributen.py` (`_property_tellingen`),
  `nulbevinding.py`. `klassen._subclass_closure` niet -- die gebruikt
  `subject_objects`.
- ``value(subject, predicate)`` -- het eerste object of None. `dataset.py`
  (`GwswDataset.onderdeel_label`), `inlezen.py` (`_read_aspects`, `_read_inwinning`,
  `_aspect_van_klasse`, `_label`, `_geometry`, `_is_multipart`),
  `checks/attributen.py` en alle vijf de lezers van `ontologie` -- `verwachte_property`,
  `functie_van_klasse`, `datatype_van_kenmerk`, `facetbereik` en (via die laatste)
  `_lijstleden`, dat de `rdf:first`/`rdf:rest`-ketting van een
  `owl:withRestrictions`-lijst er stap voor stap mee afloopt (issue #19). Dat een
  RDF-lijst met alleen `value` te wandelen is, is de reden dat deze index geen
  collectie-bewerking hoeft aan te bieden.
- ``subject_objects(predicate)`` -- alleen het predicaat gebonden;
  `klassen._subclass_closure`. rdflib loopt hier de pos-index af (eerst per object,
  dan per subject), niet de triple-volgorde; de index spiegelt die groepering.
- ``(s, p, o) in graaf`` -- volledig gebonden membership. `inlezen.py`
  (`_read_inwinning`, `_aspect_van_klasse`, `_maaiveld_kenmerk`, `_deksel_kenmerk`,
  `_geometry`, `_is_multipart`, `_endpoint`).
- ``len(graaf)`` -- het aantal triples. `load_dataset` (restrictiebron-keuze),
  `cache.py` (logregel) en de cachetests.
- ``heeft_subject(term)`` -- geen rdflib-`Graph`-bewerking maar een eigen aanvulling:
  `GwswDataset._subject_term` kijkt ermee of een URI-tekst als URIRef dan wel als
  gelijknamige BNode in de graaf staat (de `onderdeel_*`-lezers).

Niet gebruikt en dus niet aangeboden: `triples()`, patronen met andere ongebonden
argumenten, iteratie over de hele graaf, en elke schrijfbewerking na het vullen.

Van dat contract is één plak getypt: `GraafLezer` (hieronder) draagt de twee bewerkingen
die `ontologie` gebruikt. De rest van de lijst hierboven blijft proza, en met opzet --
waarom, staat bij het protocol zelf.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Protocol

import pyoxigraph
from rdflib import BNode, Literal, URIRef
from rdflib.term import Node as RdfNode

from gwsw_orox_helpers.namen import XSD_STRING


def _uriref_snel(value: str) -> URIRef:
    """Bouwt een `URIRef` zonder rdflib's eigen IRI-validatie.

    `URIRef.__new__` doet in de tak zonder `base` niets anders dan `_is_valid_uri(value)`
    aanroepen -- een reguliere expressie over de hele tekst, met een `logger.warning` als
    hij niet aanslaat -- en daarna `str.__new__(cls, value)`. pyoxigraph heeft de IRI op
    dat moment al tegen zijn eigen Turtle-grammatica gehouden, dus die tweede controle
    kost alleen tijd. Deze functie neemt het `str.__new__`-pad rechtstreeks.

    De uitkomst is van de trage weg niet te onderscheiden: `type()`, `==`, `hash()`,
    `str()`, `.n3()` en `.toPython()` geven hetzelfde.
    `tests/test_graaf.py::test_uriref_snel_is_niet_te_onderscheiden_van_de_trage_weg` is
    de bewaker voor een rdflib-upgrade die `URIRef.__new__` meer laat doen dan valideren.

    Wat wél wegvalt is de `logger.warning` die `_is_valid_uri` bij een vreemd ogende IRI
    zou loggen. Bij het *vullen* was die er toch al niet -- `bestand._parse` dempt
    `rdflib.term` met `_quiet_rdflib` -- maar wie `GraafIndex.vul_uit` rechtstreeks
    aanroept, ziet hem voortaan ook niet. Sinds issue #23 geldt dat ook voor twee
    *opvraag*plekken buiten die demping: `dataset.GwswDataset.graph_types_of` en
    `subjects_of_class` bouwen hun term hiermee, dus een afnemer die daar een misvormde
    IRI in stopt krijgt geen waarschuwing meer te zien. De term zelf blijft dezelfde en
    het antwoord dus ook -- dit gaat alleen over de logregel.

    Eén randgeval erbij, en het ligt buiten de getypeerde afspraak: `URIRef(123)` liep op
    een `TypeError` stuk (`_is_valid_uri` itereert over zijn argument), terwijl dit pad er
    `URIRef("123")` van maakt. Beide parameters heten `str` en mypy bewaakt dat; wie er
    iets anders in stopt kreeg een fout en krijgt nu een misser.
    """
    return str.__new__(URIRef, value)


def _literal_string_snel(value: str) -> Literal:
    """Bouwt een kale `Literal` (geen taal, geen datatype) zonder de constructor.

    Dit is verreweg de vaakst voorkomende literaalvorm in een OroX-export, en juist voor
    deze vorm rekent `Literal.__new__` niets uit: zonder datatype mapt het lexicale pad de
    tekst een-op-een op zichzelf, dus de vier interne velden landen altijd op
    `_language=None`, `_datatype=None`, `_value=<dezelfde tekst>` en `_ill_typed=None`.
    Die vier zet deze functie rechtstreeks.

    **Dit reikt naar rdflib-interne veldnamen** (rdflib 7.6.0), en dat is bewust: er is
    geen publieke weg om een literaal te bouwen zonder de constructor. De bewaker is
    `tests/test_graaf.py::test_literal_string_snel_is_niet_te_onderscheiden_van_de_trage_weg`,
    dat het snelpad tegen `Literal(value)` houdt op `type()`, `==`, `hash()`, `str()`,
    `.n3()`, `.datatype`, `.language`, `.value`, `.ill_typed` en `.toPython()`. Hernoemt
    een rdflib-upgrade een van die velden of verandert hun betekenis, dan wordt die test
    rood -- en dat is de enige plek waar dat opvalt.
    """
    literal = str.__new__(Literal, value)
    literal._language = None
    literal._datatype = None
    literal._value = value
    literal._ill_typed = None
    return literal


def naar_rdflib(
    term: pyoxigraph.NamedNode | pyoxigraph.BlankNode | pyoxigraph.Literal | pyoxigraph.Triple,
) -> RdfNode:
    """Zet een pyoxigraph-term om naar de bijbehorende rdflib-term.

    Een gewone (ongetypeerde) string-literaal wordt `Literal(waarde)` met datatype `None`,
    net als rdflib's eigen Turtle-parser. Een expliciet getypeerde `"x"^^xsd:string` is
    niet te onderscheiden en dus niet exact te reconstrueren: pyoxigraph vouwt die (RDF 1.1)
    al samen met de gewone vorm tot dezelfde term, terwijl rdflib's parser hem als een aparte
    term zou bewaren. De byte-voor-byte-gelijkheid van de uitvoer steunt er daarom op dat de
    ingelezen bestanden geen expliciet `^^xsd:string` dragen (nagegaan voor de totaal-ontologie
    en de OroX-export), niet op een algemene reconstructiegarantie.

    Andere termsoorten (RDF-ster-triples, benoemde grafen) horen niet in een Turtle-parse en
    vallen luid om op een `TypeError` in plaats van stilzwijgend verkeerd om te zetten.

    De twee vormen die het gros van een OroX-export uitmaken -- een `URIRef` en een kale
    `xsd:string`-`Literal` -- gaan via `_uriref_snel` en `_literal_string_snel`; de
    taal-literaal, elk ander datatype en de `BNode` blijven op de generieke weg.
    """
    if isinstance(term, pyoxigraph.NamedNode):
        return _uriref_snel(term.value)
    if isinstance(term, pyoxigraph.BlankNode):
        return BNode(term.value)
    if not isinstance(term, pyoxigraph.Literal):
        raise TypeError(f"onverwachte termsoort in een Turtle-parse: {term!r}")
    if term.language is not None:
        return Literal(term.value, lang=term.language)
    datatype = term.datatype.value
    if datatype == XSD_STRING:
        return _literal_string_snel(term.value)
    return Literal(term.value, datatype=URIRef(datatype))


class GraafLezer(Protocol):
    """Opzoeken met gebonden subject en predicaat -- wat `ontologie` van een graaf vraagt.

    De getypte vorm van het deel van het leescontract hierboven dat de vijf lezers van
    `ontologie` gebruiken (`facetbereik`, `datatype_van_kenmerk`, `kenmerkbereik`,
    `verwachte_property`, `functie_van_klasse`, plus het interne `_lijstleden`). Zij
    namen `Graph | GraafIndex` als union; met dit protocol staat er wat ze werkelijk
    nodig hebben in plaats van een opsomming van de twee vormen die dat toevallig
    kunnen. `GraafIndex` en `rdflib.Graph` vervullen het allebei **structureel** -- geen
    van beide erft ervan, geen van beide weet ervan.

    **Twee leden, en geen derde.** Dat is geen halve vertaling van de moduledocstring
    maar de smalste vorm die werkt, en de smalste vorm is hier het doel: elk lid erbij
    is een eis aan wie het protocol wil vervullen, niet een dienst aan wie het aanroept.
    De vier andere bewerkingen van het contract (`subjects`, `subject_objects`,
    `__contains__`, `__len__`) worden door `ontologie` niet aangeroepen, en
    `heeft_subject` is bovendien een eigen aanvulling die `rdflib.Graph` niet heeft --
    dat lid opnemen zou de `Graph`-kant per direct onvervulbaar maken. Meldt zich een
    lezer die meer nodig heeft, dan is het protocol verbreden een additieve stap; hem
    nu al breder maken dan de aanroepers zijn, sluit een vorm uit zonder dat iemand er
    iets aan heeft. `test_het_protocol_is_precies_zo_breed_als_ontologie_het_gebruikt`
    (in `tests/test_ontologie.py`) houdt de twee kanten aan elkaar: het protocol noemt
    exact de bewerkingen die `ontologie` op zijn graafparameter aanroept.

    **De parameters staan positioneel** (de `/`), en de types zijn zo ruim als
    `GraafIndex` ze aanbiedt. Allebei de bedoelingen zijn defensief tegen de andere
    vervuller, die van ons niet is: `rdflib.Graph.objects` draagt een derde parameter
    (`unique`) en `Graph.value` is vijfvoudig overladen (`object`, `default`, `any`) --
    extra parameters mét default breken de structurele vervulling niet, een afwijkende
    parameter*naam* zou dat wel doen zodra rdflib er een hernoemt. Positioneel is dus de
    vorm die een rdflib-upgrade overleeft; dat mypy het accepteert, staat vast in
    `tests/typecheck/graaflezer.py`, dat de poort meeneemt (zie `[tool.mypy]` in
    `pyproject.toml`).
    """

    def objects(self, subject: RdfNode, predicate: RdfNode, /) -> Iterator[RdfNode]:
        """De objecten van (subject, predicate)."""
        ...

    def value(self, subject: RdfNode, predicate: RdfNode, /) -> RdfNode | None:
        """Het eerste object van (subject, predicate), of None."""
        ...


class GraafIndex:
    """Twee dicts met het volledige leescontract van de checks (zie de moduledocstring).

    De volgordegarantie is die van rdflib's `Memory`-store: binnen `objects(s, p)` en
    `subjects(p, o)` de eerste-toevoegvolgorde van de triples, en in
    `subject_objects(p)` de pos-groepering (objecten in eerste-toevoegvolgorde onder
    het predicaat, daarbinnen de subjecten). Duplicaten tellen een keer, net als in
    een rdflib-graaf.
    """

    def __init__(self) -> None:
        # De objecten per (s, p) zijn een insertie-geordende dict met None-waarden,
        # geen lijst: het duplicaatfilter bij het vullen en de membership-test zijn
        # daarmee O(1). Met een lijst kostte de dedupescan op de De Wolden en
        # Hoogeveen-export 57 van de 97 seconden -- een gemeentebrede bucket draagt
        # tienduizenden hasPart-objecten aan hetzelfde subject.
        self._spo: dict[RdfNode, dict[RdfNode, dict[RdfNode, None]]] = {}
        self._pos: dict[RdfNode, dict[RdfNode, list[RdfNode]]] = {}
        self._aantal = 0

    def voeg_toe(self, subject: RdfNode, predicate: RdfNode, object_: RdfNode) -> None:
        """Voegt een triple toe; een duplicaat verandert niets, ook de volgorde niet."""
        objecten = self._spo.setdefault(subject, {}).setdefault(predicate, {})
        if object_ in objecten:
            return
        objecten[object_] = None
        self._pos.setdefault(predicate, {}).setdefault(object_, []).append(subject)
        self._aantal += 1

    def vul_uit(self, quads: Iterable[pyoxigraph.Quad]) -> None:
        """Vult de index in stream-volgorde uit een pyoxigraph-parse.

        Gelijke termen worden geinterneerd: elke unieke URI, blanke knoop of literaal
        bestaat een keer als rdflib-object en wordt in alle triples gedeeld. Dat
        scheelt op de De Wolden en Hoogeveen-export honderden megabytes -- elke triple
        draagt drie verwijzingen in plaats van drie verse objecten.

        De lus herhaalt `voeg_toe` bewust inline: een functieaanroep per term en per
        triple kostte op de De Wolden en Hoogeveen-export (1,9 miljoen quads) tientallen
        seconden. `tests/test_graaf.py` houdt de twee routes gelijk.
        """
        termen: dict[object, RdfNode] = {}
        spo = self._spo
        pos = self._pos
        aantal = self._aantal
        try:
            for quad in quads:
                ruw_s, ruw_p, ruw_o = quad.subject, quad.predicate, quad.object
                s = termen.get(ruw_s)
                if s is None:
                    s = termen[ruw_s] = naar_rdflib(ruw_s)
                p = termen.get(ruw_p)
                if p is None:
                    p = termen[ruw_p] = naar_rdflib(ruw_p)
                o = termen.get(ruw_o)
                if o is None:
                    o = termen[ruw_o] = naar_rdflib(ruw_o)
                per_predicaat = spo.get(s)
                if per_predicaat is None:
                    per_predicaat = spo[s] = {}
                objecten = per_predicaat.get(p)
                if objecten is None:
                    objecten = per_predicaat[p] = {}
                elif o in objecten:
                    continue
                objecten[o] = None
                per_object = pos.get(p)
                if per_object is None:
                    per_object = pos[p] = {}
                subjecten = per_object.get(o)
                if subjecten is None:
                    subjecten = per_object[o] = []
                subjecten.append(s)
                aantal += 1
        finally:
            # Ook bij een afgebroken stream klopt de teller met wat er wél in de
            # index staat.
            self._aantal = aantal

    def objects(self, subject: RdfNode, predicate: RdfNode) -> Iterator[RdfNode]:
        """De objecten van (subject, predicate), in eerste-toevoegvolgorde."""
        return iter(self._spo.get(subject, _LEEG).get(predicate, ()))

    def subjects(self, predicate: RdfNode, object_: RdfNode) -> Iterator[RdfNode]:
        """De subjecten van (predicate, object), in eerste-toevoegvolgorde."""
        return iter(self._pos.get(predicate, _LEEG_POS).get(object_, ()))

    def value(self, subject: RdfNode, predicate: RdfNode) -> RdfNode | None:
        """Het eerste object van (subject, predicate), of None."""
        objecten = self._spo.get(subject, _LEEG).get(predicate)
        return next(iter(objecten)) if objecten else None

    def subject_objects(self, predicate: RdfNode) -> Iterator[tuple[RdfNode, RdfNode]]:
        """Alle (subject, object)-paren van dit predicaat, in pos-groepering."""
        for object_, subjecten in self._pos.get(predicate, _LEEG_POS).items():
            for subject in subjecten:
                yield subject, object_

    def heeft_subject(self, term: RdfNode) -> bool:
        """Of deze term als subject in de graaf voorkomt."""
        return term in self._spo

    def __contains__(self, triple: tuple[RdfNode, RdfNode, RdfNode]) -> bool:
        """Membership van een volledig gebonden triple, in O(1)."""
        subject, predicate, object_ = triple
        return object_ in self._spo.get(subject, _LEEG).get(predicate, ())

    def __len__(self) -> int:
        """Het aantal triples, zonder duplicaten."""
        return self._aantal


# Gedeelde lege dicts als terugval, zodat een misser geen nieuwe dict aanmaakt.
_LEEG: dict[RdfNode, dict[RdfNode, None]] = {}
_LEEG_POS: dict[RdfNode, list[RdfNode]] = {}
