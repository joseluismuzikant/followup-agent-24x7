"""Property conditions without a database: requirements vs features, unknown values,
several failures, the agency's defaults under a property's own values, the ordering of
options, and the import parsing of the new columns."""

import pytest
from inmo24x7_api.properties.application.rows import (
    CellError,
    ColumnMap,
    ParsedRow,
    parse_flag,
    parse_guarantees,
    parse_row,
)
from inmo24x7_api.properties.domain.conditions import (
    ConditionSettings,
    ConditionsInvalidError,
    Guarantee,
    LeadConditions,
    MatchStatus,
    PropertyConditions,
    Requirement,
    common_failure,
    evaluate,
    months_label,
)
from inmo24x7_api.properties.domain.property import Currency, Operation
from inmo24x7_api.properties.domain.search import Listing, PropertyQuery, rank

CAUCION = frozenset({Guarantee.CAUCION})


def lead(**facts) -> LeadConditions:
    return LeadConditions.from_answers(facts)


@pytest.mark.parametrize(
    ("conditions", "facts", "status", "reason"),
    [
        (
            PropertyConditions(garantias=CAUCION),
            {"garantia": "propietaria"},
            MatchStatus.NO_CUMPLE,
            "pide seguro de caución; tiene garantía propietaria",
        ),
        (
            PropertyConditions(garantias=frozenset({Guarantee.CAUCION, Guarantee.PROPIETARIA})),
            {"garantia": "ninguna"},
            MatchStatus.NO_CUMPLE,
            "pide seguro de caución o garantía propietaria; no tiene garantía",
        ),
        (PropertyConditions(garantias=CAUCION), {"garantia": "caucion"}, MatchStatus.CUMPLE, None),
        (
            PropertyConditions(contrato_minimo_meses=24),
            {"plazo_meses": 6},
            MatchStatus.NO_CUMPLE,
            "pide contrato de 2 años; busca 6 meses",
        ),
        (
            PropertyConditions(contrato_minimo_meses=24),
            {"plazo_meses": 36},
            MatchStatus.CUMPLE,
            None,
        ),
        (
            PropertyConditions(temporal=False),
            {"temporal": True},
            MatchStatus.NO_CUMPLE,
            "no acepta alquiler temporario; busca temporario",
        ),
        (
            PropertyConditions(mascotas=False),
            {"tiene_mascota": True},
            MatchStatus.NO_CUMPLE,
            "no acepta mascotas; tiene mascota",
        ),
        (PropertyConditions(mascotas=False), {"tiene_mascota": False}, MatchStatus.CUMPLE, None),
    ],
)
def test_each_requirement(
    conditions: PropertyConditions, facts: dict, status: MatchStatus, reason: str | None
) -> None:
    match = evaluate(lead(**facts), conditions)

    assert match.status is status
    assert [item.reason for item in match.failed] == ([reason] if reason else [])


def test_unknown_on_either_side_is_never_a_mismatch() -> None:
    assert evaluate(lead(), PropertyConditions(garantias=CAUCION, mascotas=False)).status is (
        MatchStatus.SIN_DATOS
    )
    assert evaluate(lead(garantia="ninguna", tiene_mascota=True), PropertyConditions()).status is (
        MatchStatus.SIN_DATOS
    )


def test_features_order_and_note_but_never_fail() -> None:
    conditions = PropertyConditions(apto_credito=False, acepta_permuta=True, mascotas=True)

    match = evaluate(
        lead(necesita_credito=True, ofrece_permuta=True, tiene_mascota=True), conditions
    )

    assert match.status is MatchStatus.CUMPLE
    assert match.features == ("acepta mascotas", "acepta permuta")
    assert match.notes == ("no es apta crédito",)
    assert match.summary == "Cumple"


def test_several_failures_are_all_reported() -> None:
    conditions = PropertyConditions(garantias=CAUCION, contrato_minimo_meses=24, mascotas=False)

    match = evaluate(lead(garantia="otra", plazo_meses=1, tiene_mascota=True), conditions)

    assert [item.requirement for item in match.failed] == [
        Requirement.GARANTIA,
        Requirement.CONTRATO_MINIMO,
        Requirement.MASCOTAS,
    ]
    assert match.summary.startswith("No cumple: pide seguro de caución; tiene otra garantía; ")


def test_a_requirement_the_lead_can_meet_anyway_counts_as_met() -> None:
    match = evaluate(
        lead(garantia="propietaria", acepta_requisitos=["garantia"]),
        PropertyConditions(garantias=CAUCION),
    )

    assert match.status is MatchStatus.CUMPLE
    assert match.accepted == ("seguro de caución",)
    assert match.summary == "Cumple (dijo que puede: seguro de caución)"


def test_the_agency_default_applies_unless_the_property_says_otherwise() -> None:
    settings = ConditionSettings(
        rent=PropertyConditions(garantias=CAUCION, contrato_minimo_meses=24, apto_credito=True)
    )
    own = PropertyConditions(contrato_minimo_meses=12)

    effective = settings.effective(Operation.RENT, own)

    assert effective.garantias == CAUCION  # the default
    assert effective.contrato_minimo_meses == 12  # the property's own
    assert effective.apto_credito is None  # a sale field never applies to a rent
    assert own.from_defaults(settings.defaults(Operation.RENT)) == {"garantias"}


def test_the_old_mortgage_answer_is_read_as_needing_credit() -> None:
    assert lead(mortgage_approved=True).necesita_credito is True
    # "No" to an approved mortgage says nothing about needing credit.
    assert lead(mortgage_approved=False).necesita_credito is None
    assert lead(mortgage_approved=True, necesita_credito=False).necesita_credito is False


def test_validation_and_json_round_trip() -> None:
    conditions = PropertyConditions(
        garantias=frozenset({Guarantee.CAUCION, Guarantee.PROPIETARIA}),
        contrato_minimo_meses=24,
        mascotas=False,
        condiciones="  requiere   dos garantías ",
    )

    assert PropertyConditions.from_json(conditions.to_json()) == conditions
    assert conditions.condiciones == "requiere dos garantías"
    assert conditions.to_json()["garantias"] == ["caucion", "propietaria"]
    with pytest.raises(ConditionsInvalidError):
        PropertyConditions(contrato_minimo_meses=0)
    with pytest.raises(ConditionsInvalidError):
        PropertyConditions(condiciones="x" * 301)
    assert months_label(24) == "2 años" and months_label(6) == "6 meses"


def listing(name: str, price: int, **conditions) -> Listing:
    return Listing(
        id=name,
        title=name,
        address=f"{name} 100",
        operation=Operation.RENT,
        zone="Palermo",
        price=price,
        currency=Currency.ARS,
        rooms=2,
        link=f"https://x.test/{name}",
        is_sample=False,
        conditions=PropertyConditions(**conditions),
    )


def test_options_are_ordered_fit_first_then_unknown_then_not_fitting() -> None:
    listings = [
        listing("sin-mascotas", 500_000, mascotas=False),
        listing("sin-datos", 600_000),
        listing("con-mascotas", 700_000, mascotas=True),
    ]

    plain = rank(listings, PropertyQuery(operation=Operation.RENT))
    with_lead = rank(
        listings, PropertyQuery(operation=Operation.RENT, lead=lead(tiene_mascota=True))
    )

    # Nothing is hidden: the lead's situation only changes the order.
    assert [item.listing.id for item in plain] == ["sin-mascotas", "sin-datos", "con-mascotas"]
    assert [item.listing.id for item in with_lead] == ["con-mascotas", "sin-datos", "sin-mascotas"]
    assert [item.match.status for item in with_lead] == [
        MatchStatus.CUMPLE,
        MatchStatus.SIN_DATOS,
        MatchStatus.NO_CUMPLE,
    ]


def test_the_requirement_every_option_fails_on() -> None:
    first = evaluate(lead(plazo_meses=1), PropertyConditions(contrato_minimo_meses=24))
    second = evaluate(
        lead(plazo_meses=1, garantia="ninguna"),
        PropertyConditions(contrato_minimo_meses=36, garantias=CAUCION),
    )

    failure = common_failure([first, second])

    assert failure is not None and failure.requirement is Requirement.CONTRATO_MINIMO
    assert common_failure([first, evaluate(lead(), PropertyConditions())]) is None


HEADER = [
    "titulo",
    "direccion",
    "operacion",
    "zona",
    "precio",
    "ambientes",
    "link",
    "garantias",
    "contrato_minimo_meses",
    "temporal",
    "mascotas",
    "apto_credito",
    "condiciones",
]
COLUMNS = ColumnMap.of(HEADER)


def row(operation: str = "alquiler", **cells: str) -> list[str]:
    base = {
        "titulo": "2 ambientes",
        "direccion": "Gorriti 4800",
        "operacion": operation,
        "zona": "Palermo",
        "precio": "850.000",
        "ambientes": "2",
        "link": "https://x.test/gorriti",
    }
    return [{**base, **cells}.get(name, "") for name in HEADER]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Sí", True),
        ("si", True),
        ("S", True),
        ("yes", True),
        ("x", True),
        ("1", True),
        ("No", False),
        ("n", False),
        ("0", False),
        ("", None),
    ],
)
def test_yes_no_cells(text: str, expected: bool | None) -> None:
    assert parse_flag(text) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("caución", {"caucion"}),
        ("Seguro de caución / garantía propietaria", {"caucion", "propietaria"}),
        ("propietaria, recibo", {"propietaria", "recibo_de_sueldo"}),
        ("Recibo de sueldo y otra", {"recibo_de_sueldo", "otra"}),
    ],
)
def test_guarantee_aliases(text: str, expected: set[str]) -> None:
    assert {item.value for item in parse_guarantees(text) or ()} == expected


def test_a_row_with_conditions() -> None:
    parsed = parse_row(
        COLUMNS,
        row(
            garantias="caución",
            contrato_minimo_meses="24",
            mascotas="no",
            condiciones="Dos garantías",
        ),
    )

    assert isinstance(parsed, ParsedRow)
    conditions = parsed.fields.conditions
    assert (conditions.garantias, conditions.contrato_minimo_meses, conditions.mascotas) == (
        CAUCION,
        24,
        False,
    )
    assert conditions.condiciones == "Dos garantías"
    assert parsed.ignored == ()


def test_a_field_of_the_other_operation_is_ignored_with_a_warning() -> None:
    parsed = parse_row(COLUMNS, row(apto_credito="sí", mascotas="sí"))

    assert isinstance(parsed, ParsedRow)
    assert parsed.ignored == ("apto_credito",)
    assert parsed.fields.conditions.apto_credito is None
    assert parsed.fields.conditions.mascotas is True


@pytest.mark.parametrize(
    ("cells", "message"),
    [
        ({"garantias": "fiador"}, "«garantias» tiene un valor que no entiendo: «fiador»."),
        ({"mascotas": "a veces"}, "«mascotas» tiene un valor que no entiendo: «a veces»."),
        (
            {"contrato_minimo_meses": "dos años"},
            "«contrato_minimo_meses» tiene que ser un número de meses entre 1 y 120: «dos años».",
        ),
    ],
)
def test_condition_cells_that_cannot_be_read(cells: dict, message: str) -> None:
    parsed = parse_row(COLUMNS, row(**cells))

    assert isinstance(parsed, CellError)
    assert parsed.message == message


def test_files_without_the_new_columns_import_as_before() -> None:
    old = ColumnMap.of(["titulo", "direccion", "operacion", "zona", "precio", "ambientes", "link"])
    parsed = parse_row(
        old, ["2 amb", "Gorriti 4800", "alquiler", "Palermo", "850000", "2", "https://x.test/a"]
    )

    assert isinstance(parsed, ParsedRow)
    assert parsed.fields.conditions == PropertyConditions()
