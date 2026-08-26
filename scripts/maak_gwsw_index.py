#!/usr/bin/env python
"""Schrijft de gebundelde `gwsw-vocabulaire-index.json` uit de GWSW-totaalontologie.

De index is een kleine afgeleide van de 2,6 MB grote ontologie die met deze package
meereist: per GWSW-naam de `rdf:type`s die de ontologie eraan geeft -- tegelijk het
antwoord op "bestaat dit begrip" en op "zit het in de juiste collectie" -- plus de
directe `rdfs:subClassOf`-kanten en de directe `hasAspect`/`hasPart`-buren. Een afnemer
die alleen die vragen stelt hoeft de hele ontologie niet te parsen; nlriochecker toetst
er zijn checkdeclaraties en configuratietermen mee.

De ontologie is CC0 (https://stichtingrioned.github.io/GWSW_Ontologie_RDF/), dus aan het
meeleveren van beide staat niets in de weg.

Upgraden blijft handwerk van de auteur, zoals `CLAUDE.md` voorschrijft: hij vervangt
`src/gwsw_orox_helpers/data/Ontologie_GWSW_Totaal.ttl` en draait dit script. Er wordt met
opzet niets bij data.gwsw.nl opgehaald. Vergeet hij het script, dan valt
`test_index_volgt_de_ontologie`.

Gebruik:  uv run python scripts/maak_gwsw_index.py
"""

from __future__ import annotations

import json
from pathlib import Path

from rdflib import OWL, RDF, RDFS, Graph, URIRef

from gwsw_orox_helpers.dataset import GWSW

WORTEL = Path(__file__).resolve().parents[1]
ONTOLOGIE = WORTEL / "src" / "gwsw_orox_helpers" / "data" / "Ontologie_GWSW_Totaal.ttl"
DOEL = WORTEL / "src" / "gwsw_orox_helpers" / "data" / "gwsw-vocabulaire-index.json"


def termen_uit_graaf(graaf: Graph) -> dict[str, list[str]]:
    """Per GWSW-subject de `rdf:type`s die de ontologie eraan geeft.

    Een type binnen de GWSW-naamruimte wordt tot zijn korte naam gekort -- dat is de
    collectie waarin een domeinlijstwaarde zit (`VormLeidingColl`). De rest blijft een
    volledige URI (`owl:Class`), zodat er geen afkortingstabel bij hoort die de lezer
    en de schrijver uit elkaar kan laten lopen.
    """
    termen: dict[str, set[str]] = {}
    for subject, _, soort in graaf.triples((None, RDF.type, None)):
        if not isinstance(subject, URIRef) or not str(subject).startswith(GWSW):
            continue
        termen.setdefault(str(subject).removeprefix(GWSW), set()).add(str(soort).removeprefix(GWSW))
    return {naam: sorted(soorten) for naam, soorten in sorted(termen.items())}


def ouders_uit_graaf(graaf: Graph) -> dict[str, list[str]]:
    """Per GWSW-klasse haar directe GWSW-superklassen.

    Alleen de *directe* kanten, niet de afsluiting: die is uit deze kanten te bouwen en
    zou het bestand een orde van grootte groter maken. Kanten naar buiten de
    GWSW-naamruimte (`owl:Thing`, SKOS) blijven weg -- de vraag die de index hiermee
    beantwoordt is welke GWSW-klassen onder een GWSW-wortel hangen.
    """
    ouders: dict[str, set[str]] = {}
    for kind, ouder in graaf.subject_objects(RDFS.subClassOf):
        if not isinstance(kind, URIRef) or not isinstance(ouder, URIRef):
            continue
        if not str(kind).startswith(GWSW) or not str(ouder).startswith(GWSW):
            continue
        ouders.setdefault(str(kind).removeprefix(GWSW), set()).add(str(ouder).removeprefix(GWSW))
    return {naam: sorted(soorten) for naam, soorten in sorted(ouders.items())}


def _relatie_uit_graaf(graaf: Graph, voorwaarts: str, achterwaarts: str) -> dict[str, list[str]]:
    """Per GWSW-klasse de directe doelen van een relatie, in beide richtingen gevouwen.

    De ontologie hangt onder een klasse blanknode-restricties aan `rdfs:subClassOf`:
    `[ a owl:Restriction ; owl:onProperty gwsw:hasAspect ; owl:onClass gwsw:X ]`. Het
    doel staat als `owl:onClass` (het gros), maar een handvol `hasAspect`-restricties
    bindt via `owl:someValuesFrom` en twee `hasPart`-restricties via `owl:allValuesFrom`
    (`Deksel hasAspect MateriaalDeksel` heeft alleen die vorm); alle drie tellen als de
    directe buur. Ze komen bovendien in twee richtingen voor, want het GWSW declareert
    `isAspectOf owl:inverseOf hasAspect` en `isPartOf owl:inverseOf hasPart`:
    `Putdekselniveau` hangt aan `Dekselorientatie` als `Putdekselniveau isAspectOf
    Dekselorientatie`, niet als `Dekselorientatie hasAspect Putdekselniveau`. Deze functie
    vouwt beide tot dezelfde kant, zodat `aspecten_van` (`voorwaarts=hasAspect`,
    `achterwaarts=isAspectOf`) en `onderdelen_van` (`hasPart`, `isPartOf`) de volledige
    directe buren dragen. Alleen directe kanten, net als `subklasse_van`; de afnemer
    bouwt de bereikbaarheid daaruit op.
    """
    voor = URIRef(f"{GWSW}{voorwaarts}")
    achter = URIRef(f"{GWSW}{achterwaarts}")
    kanten: dict[str, set[str]] = {}
    for houder, restrictie in graaf.subject_objects(RDFS.subClassOf):
        if not isinstance(houder, URIRef) or not str(houder).startswith(GWSW):
            continue
        if (restrictie, RDF.type, OWL.Restriction) not in graaf:
            continue
        prop = graaf.value(restrictie, OWL.onProperty)
        doel = (
            graaf.value(restrictie, OWL.onClass)
            or graaf.value(restrictie, OWL.someValuesFrom)
            or graaf.value(restrictie, OWL.allValuesFrom)
        )
        if not isinstance(doel, URIRef) or not str(doel).startswith(GWSW):
            continue
        bron = str(houder).removeprefix(GWSW)
        naar = str(doel).removeprefix(GWSW)
        if prop == voor:
            kanten.setdefault(bron, set()).add(naar)
        elif prop == achter:
            # De inverse: `houder achterwaarts doel` betekent `doel voorwaarts houder`.
            kanten.setdefault(naar, set()).add(bron)
    return {naam: sorted(doelen) for naam, doelen in sorted(kanten.items())}


def versie_uit_graaf(graaf: Graph) -> str:
    """De `owl:versionInfo` van de ontologie, letterlijk overgenomen.

    Letterlijk, en niet uitgekleed tot "1.6": het nummer hoort in de ontologie thuis
    en `CLAUDE.md` is de enige plek waar het als projectafspraak staat. De regel reist
    hier mee als bewijs bij welke ontologie deze index hoort, niet als tweede
    gezaghebbende bron. Wie hem hier bijwerkt zonder de ontologie te vervangen, krijgt
    `test_index_volgt_de_ontologie` rood.
    """
    for _, _, waarde in graaf.triples((None, OWL.versionInfo, None)):
        return str(waarde)
    raise SystemExit(f"{ONTOLOGIE}: geen owl:versionInfo gevonden.")


def documenttekst(ttl: Path) -> str:
    """De volledige inhoud van het indexbestand voor deze ontologie.

    Handgezet in plaats van `json.dumps(indent=…)`, omdat een regel per term het
    bestand diffbaar houdt: een nieuwe GWSW-versie levert dan een leesbare lijst
    toevoegingen op in plaats van een blok van tienduizend regels.
    """
    graaf = Graph()
    graaf.parse(ttl, format="turtle")

    kop = {
        "bron": ttl.relative_to(WORTEL).as_posix(),
        "gwsw_versie": versie_uit_graaf(graaf),
        "script": Path(__file__).relative_to(WORTEL).as_posix(),
    }
    blokken = (
        ("termen", termen_uit_graaf(graaf)),
        ("subklasse_van", ouders_uit_graaf(graaf)),
        ("aspecten_van", _relatie_uit_graaf(graaf, "hasAspect", "isAspectOf")),
        ("onderdelen_van", _relatie_uit_graaf(graaf, "hasPart", "isPartOf")),
    )
    regels = ["{"]
    regels += [f"  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}," for k, v in kop.items()]
    for blok_nr, (blok, inhoud) in enumerate(blokken, start=1):
        komma_blok = "," if blok_nr != len(blokken) else ""
        regels.append(f'  "{blok}": {{')
        namen = list(inhoud)
        for nummer, naam in enumerate(namen, start=1):
            komma = "" if nummer == len(namen) else ","
            sleutel = json.dumps(naam, ensure_ascii=False)
            waarden = json.dumps(inhoud[naam], ensure_ascii=False)
            regels.append(f"    {sleutel}: {waarden}{komma}")
        regels.append(f"  }}{komma_blok}")
    regels.append("}")
    return "\n".join(regels) + "\n"


def main() -> None:
    """Schrijft de index en meldt hoeveel termen erin staan."""
    if not ONTOLOGIE.exists():
        raise SystemExit(f"{ONTOLOGIE} ontbreekt; zet de GWSW-ontologie terug in de package.")
    tekst = documenttekst(ONTOLOGIE)
    DOEL.write_text(tekst, encoding="utf-8")
    document = json.loads(tekst)
    # Twee getallen die makkelijk verward worden: `subklasse_van` heeft een sleutel per
    # klasse met minstens een GWSW-ouder, en die klassen kunnen er meer dan een hebben.
    # Het aantal sleutels is dus niet het aantal relaties. Beide staan er, met hun
    # eigen naam.
    print(
        f"{DOEL.relative_to(WORTEL)}: {len(document['termen'])} termen, "
        f"{len(document['subklasse_van'])} klassen met een superklasse "
        f"({sum(len(ouders) for ouders in document['subklasse_van'].values())} "
        f"subklasserelaties), {len(document['aspecten_van'])} klassen met een aspect en "
        f"{len(document['onderdelen_van'])} klassen met een onderdeel geschreven "
        f"({DOEL.stat().st_size / 1024:.0f} kB)."
    )


if __name__ == "__main__":
    main()
