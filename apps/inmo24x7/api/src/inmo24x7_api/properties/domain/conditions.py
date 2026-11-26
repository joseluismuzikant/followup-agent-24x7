"""A property's conditions and the lead's situation, compared.

Two different things, kept apart in the model, the panel and the matching:

- **Requirements** are set by the property: the guarantees it accepts, a minimum contract,
  whether it takes temporary rentals, whether pets are allowed. Failing one means
  "No cumple".
- **Features** answer the lead's wishes: furnished, professional use, apt for mortgage
  credit, financing, swap (permuta), pets allowed. Never a mismatch: they order the options
  and give Sofía a positive line ("acepta mascotas"). A wish the property does not meet is
  a note for the team, not a failure.

Every field is optional: empty means "no informado" and is never a mismatch. A property's
own value wins over the agency's default for its operation (`effective`). `condiciones` is
free text Sofía may mention; it never takes part in matching.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields, replace
from enum import StrEnum
from typing import Any

from .operation import Operation

MAX_CONDITIONS_TEXT = 300
MAX_CONTRACT_MONTHS = 120


class Guarantee(StrEnum):
    PROPIETARIA = "propietaria"
    CAUCION = "caucion"
    RECIBO_DE_SUELDO = "recibo_de_sueldo"
    OTRA = "otra"


GUARANTEE_LABELS: Mapping[Guarantee, str] = {
    Guarantee.PROPIETARIA: "garantía propietaria",
    Guarantee.CAUCION: "seguro de caución",
    Guarantee.RECIBO_DE_SUELDO: "recibo de sueldo",
    Guarantee.OTRA: "otra garantía",
}

# The lead's answer to "¿con qué garantía contás?": the guarantees plus "none".
LEAD_GUARANTEES = (*(item.value for item in Guarantee), "ninguna")


class ConditionsInvalidError(ValueError):
    def __init__(self, field_name: str) -> None:
        super().__init__(field_name)
        self.field = field_name


# Which fields apply to each operation (`condiciones` applies to both).
RENT_FIELDS = (
    "garantias",
    "contrato_minimo_meses",
    "temporal",
    "amueblado",
    "mascotas",
    "apto_profesional",
)
SALE_FIELDS = (
    "apto_credito",
    "acepta_financiacion",
    "acepta_permuta",
    "mascotas",
    "apto_profesional",
)
FIELDS_BY_OPERATION: Mapping[Operation, tuple[str, ...]] = {
    Operation.RENT: (*RENT_FIELDS, "condiciones"),
    Operation.SALE: (*SALE_FIELDS, "condiciones"),
}


@dataclass(frozen=True, slots=True)
class PropertyConditions:
    """None = no informado."""

    garantias: frozenset[Guarantee] | None = None
    contrato_minimo_meses: int | None = None
    temporal: bool | None = None
    amueblado: bool | None = None
    mascotas: bool | None = None
    apto_profesional: bool | None = None
    apto_credito: bool | None = None
    acepta_financiacion: bool | None = None
    acepta_permuta: bool | None = None
    condiciones: str | None = None

    def __post_init__(self) -> None:
        if self.garantias is not None:
            if not self.garantias:
                object.__setattr__(self, "garantias", None)
            else:
                object.__setattr__(
                    self, "garantias", frozenset(Guarantee(g) for g in self.garantias)
                )
        months = self.contrato_minimo_meses
        if months is not None and (
            isinstance(months, bool) or not 1 <= months <= MAX_CONTRACT_MONTHS
        ):
            raise ConditionsInvalidError("contrato_minimo_meses")
        if self.condiciones is not None:
            text = " ".join(self.condiciones.split())
            if len(text) > MAX_CONDITIONS_TEXT:
                raise ConditionsInvalidError("condiciones")
            object.__setattr__(self, "condiciones", text or None)

    @property
    def is_empty(self) -> bool:
        return all(getattr(self, item.name) is None for item in fields(self))

    def for_operation(self, operation: Operation) -> "PropertyConditions":
        """Only the fields that apply to the operation (the rest are dropped)."""
        allowed = FIELDS_BY_OPERATION[operation]
        return PropertyConditions(
            **{item.name: getattr(self, item.name) for item in fields(self) if item.name in allowed}
        )

    def over(self, defaults: "PropertyConditions") -> "PropertyConditions":
        """This property's values, and the agency's default where it has none."""
        return replace(
            defaults,
            **{
                item.name: getattr(self, item.name)
                for item in fields(self)
                if getattr(self, item.name) is not None
            },
        )

    def from_defaults(self, defaults: "PropertyConditions") -> frozenset[str]:
        """The fields whose effective value comes from the agency's default."""
        return frozenset(
            item.name
            for item in fields(self)
            if getattr(self, item.name) is None and getattr(defaults, item.name) is not None
        )

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for item in fields(self):
            value = getattr(self, item.name)
            if value is None:
                continue
            data[item.name] = sorted(g.value for g in value) if item.name == "garantias" else value
        return data

    @classmethod
    def from_json(cls, data: Mapping[str, Any] | None) -> "PropertyConditions":
        if not data:
            return cls()
        known = {item.name for item in fields(cls)}
        values = {key: value for key, value in data.items() if key in known}
        if "garantias" in values and values["garantias"] is not None:
            values["garantias"] = frozenset(Guarantee(g) for g in values["garantias"])
        return cls(**values)


@dataclass(frozen=True, slots=True)
class ConditionSettings:
    """The agency's "Condiciones generales": defaults per operation and Sofía's behavior."""

    rent: PropertyConditions = field(default_factory=PropertyConditions)
    sale: PropertyConditions = field(default_factory=PropertyConditions)
    # Before offering visit times, say which requirement the lead does not meet.
    warn_before_visit: bool = True
    # When every option fails on the same requirement, ask once about it.
    offer_alternatives: bool = True
    # Email the team about leads that do not meet the conditions of what they chose.
    notify_mismatches: bool = True

    def defaults(self, operation: Operation) -> PropertyConditions:
        chosen = self.rent if operation is Operation.RENT else self.sale
        return chosen.for_operation(operation)

    def effective(self, operation: Operation, own: PropertyConditions) -> PropertyConditions:
        return own.for_operation(operation).over(self.defaults(operation))


@dataclass(frozen=True, slots=True)
class LeadConditions:
    """What the lead said about their situation (None = not said)."""

    garantia: str | None = None  # LEAD_GUARANTEES
    plazo_meses: int | None = None
    temporal: bool | None = None
    quiere_amueblado: bool | None = None
    tiene_mascota: bool | None = None
    uso_profesional: bool | None = None
    necesita_credito: bool | None = None
    necesita_financiacion: bool | None = None
    ofrece_permuta: bool | None = None
    # Requirements the lead said they can meet anyway ("sí, consigo el seguro de caución").
    acepta: frozenset[str] = frozenset()

    @classmethod
    def from_answers(cls, answers: Mapping[str, Any]) -> "LeadConditions":
        def flag(key: str) -> bool | None:
            value = answers.get(key)
            return value if isinstance(value, bool) else None

        guarantee = answers.get("garantia")
        months = answers.get("plazo_meses")
        credit = flag("necesita_credito")
        if credit is None and answers.get("mortgage_approved") is True:
            # Before the conditions, sales asked "mortgage_approved": an approved mortgage
            # means buying with credit. A "no" says nothing about needing one.
            credit = True
        accepted = answers.get("acepta_requisitos")
        return cls(
            garantia=guarantee if guarantee in LEAD_GUARANTEES else None,
            plazo_meses=months
            if isinstance(months, int) and not isinstance(months, bool) and months > 0
            else None,
            temporal=flag("temporal"),
            quiere_amueblado=flag("quiere_amueblado"),
            tiene_mascota=flag("tiene_mascota"),
            uso_profesional=flag("uso_profesional"),
            necesita_credito=credit,
            necesita_financiacion=flag("necesita_financiacion"),
            ofrece_permuta=flag("ofrece_permuta"),
            acepta=frozenset(str(item) for item in accepted)
            if isinstance(accepted, list)
            else frozenset(),
        )


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


class MatchStatus(StrEnum):
    CUMPLE = "cumple"
    NO_CUMPLE = "no_cumple"
    SIN_DATOS = "sin_datos"


# Presenting options: what fits first, unknown next, what does not fit last.
STATUS_ORDER: Mapping[MatchStatus, int] = {
    MatchStatus.CUMPLE: 0,
    MatchStatus.SIN_DATOS: 1,
    MatchStatus.NO_CUMPLE: 2,
}


class Requirement(StrEnum):
    GARANTIA = "garantia"
    CONTRATO_MINIMO = "contrato_minimo"
    TEMPORAL = "temporal"
    MASCOTAS = "mascotas"


@dataclass(frozen=True, slots=True)
class Failure:
    requirement: Requirement
    # For the team: "pide seguro de caución; tiene garantía propietaria".
    reason: str
    # For Sofía, before the visit: "pide seguro de caución".
    asks: str


@dataclass(frozen=True, slots=True)
class Match:
    status: MatchStatus
    failed: tuple[Failure, ...] = ()
    # Wishes this property meets: "acepta mascotas".
    features: tuple[str, ...] = ()
    # Wishes it does not meet (never a failure): "no es apta crédito".
    notes: tuple[str, ...] = ()
    # Requirements the lead said they can meet anyway.
    accepted: tuple[str, ...] = ()

    @property
    def summary(self) -> str:
        """One line for the inbox and the email."""
        if self.status is MatchStatus.NO_CUMPLE:
            return "No cumple: " + "; ".join(item.reason for item in self.failed)
        if self.status is MatchStatus.CUMPLE:
            extra = f" (dijo que puede: {', '.join(self.accepted)})" if self.accepted else ""
            return "Cumple" + extra
        return "Sin datos"

    def to_json(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "failed": [
                {"requirement": item.requirement.value, "reason": item.reason, "asks": item.asks}
                for item in self.failed
            ],
            "features": list(self.features),
            "notes": list(self.notes),
            "accepted": list(self.accepted),
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "Match":
        return cls(
            status=MatchStatus(data.get("status", MatchStatus.SIN_DATOS.value)),
            failed=tuple(
                Failure(Requirement(item["requirement"]), item["reason"], item["asks"])
                for item in data.get("failed", [])
            ),
            features=tuple(data.get("features", [])),
            notes=tuple(data.get("notes", [])),
            accepted=tuple(data.get("accepted", [])),
        )


def months_label(months: int) -> str:
    if months % 12 == 0:
        years = months // 12
        return "1 año" if years == 1 else f"{years} años"
    return "1 mes" if months == 1 else f"{months} meses"


def _guarantees(items: frozenset[Guarantee]) -> str:
    labels = [GUARANTEE_LABELS[item] for item in sorted(items)]
    return labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + " o " + labels[-1]


def _lead_guarantee(value: str) -> str:
    if value == "ninguna":
        return "no tiene garantía"
    return "tiene " + GUARANTEE_LABELS[Guarantee(value)]


# (lead wish, property field, positive line, note when the property does not meet it)
_FEATURES: tuple[tuple[str, str, str, str], ...] = (
    ("quiere_amueblado", "amueblado", "está amueblada", "no está amueblada"),
    (
        "uso_profesional",
        "apto_profesional",
        "es apta uso profesional",
        "no es apta uso profesional",
    ),
    ("necesita_credito", "apto_credito", "es apta crédito", "no es apta crédito"),
    (
        "necesita_financiacion",
        "acepta_financiacion",
        "acepta financiación",
        "no acepta financiación",
    ),
    ("ofrece_permuta", "acepta_permuta", "acepta permuta", "no acepta permuta"),
)

REQUIREMENT_LABELS: Mapping[Requirement, str] = {
    Requirement.GARANTIA: "la garantía",
    Requirement.CONTRATO_MINIMO: "el plazo del contrato",
    Requirement.TEMPORAL: "el alquiler temporario",
    Requirement.MASCOTAS: "las mascotas",
}


def evaluate(lead: LeadConditions, conditions: PropertyConditions) -> Match:
    """Compares the lead with a property's effective conditions (`ConditionSettings.
    effective`). A field unknown on either side is never a mismatch; with nothing to compare
    the status is `sin_datos`."""
    failed: list[Failure] = []
    accepted: list[str] = []
    features: list[str] = []
    notes: list[str] = []
    compared = False

    def fail(requirement: Requirement, reason: str, asks: str) -> None:
        if requirement.value in lead.acepta:
            accepted.append(asks.removeprefix("pide ").removeprefix("no acepta "))
        else:
            failed.append(Failure(requirement, reason, asks))

    if conditions.garantias is not None and lead.garantia is not None:
        compared = True
        if lead.garantia == "ninguna" or Guarantee(lead.garantia) not in conditions.garantias:
            asked = _guarantees(conditions.garantias)
            fail(
                Requirement.GARANTIA,
                f"pide {asked}; {_lead_guarantee(lead.garantia)}",
                f"pide {asked}",
            )
    minimum = conditions.contrato_minimo_meses
    if minimum is not None and lead.plazo_meses is not None:
        compared = True
        if lead.plazo_meses < minimum:
            fail(
                Requirement.CONTRATO_MINIMO,
                f"pide contrato de {months_label(minimum)}; busca {months_label(lead.plazo_meses)}",
                f"pide contrato de {months_label(minimum)}",
            )
    if conditions.temporal is not None and lead.temporal is True:
        compared = True
        if conditions.temporal:
            features.append("acepta alquiler temporario")
        else:
            fail(
                Requirement.TEMPORAL,
                "no acepta alquiler temporario; busca temporario",
                "no acepta alquiler temporario",
            )
    if conditions.mascotas is not None and lead.tiene_mascota is not None:
        compared = True
        if lead.tiene_mascota and not conditions.mascotas:
            fail(Requirement.MASCOTAS, "no acepta mascotas; tiene mascota", "no acepta mascotas")
        elif lead.tiene_mascota:
            features.append("acepta mascotas")
    for wish, property_field, positive, negative in _FEATURES:
        wanted = getattr(lead, wish)
        offered = getattr(conditions, property_field)
        if wanted is not True or offered is None:
            continue
        compared = True
        (features if offered else notes).append(positive if offered else negative)

    if failed:
        status = MatchStatus.NO_CUMPLE
    elif compared:
        status = MatchStatus.CUMPLE
    else:
        status = MatchStatus.SIN_DATOS
    return Match(status, tuple(failed), tuple(features), tuple(notes), tuple(accepted))


def common_failure(matches: Sequence[Match]) -> Failure | None:
    """The requirement every option fails on (the "nothing fits" question), if there is one."""
    if not matches or any(match.status is not MatchStatus.NO_CUMPLE for match in matches):
        return None
    shared = set.intersection(*({item.requirement for item in match.failed} for match in matches))
    if not shared:
        return None
    requirement = sorted(shared)[0]
    return next(item for item in matches[0].failed if item.requirement is requirement)


_FLAG_PHRASES: tuple[tuple[str, str, str], ...] = (
    ("temporal", "acepta alquiler temporario", "no acepta alquiler temporario"),
    ("amueblado", "está amueblada", "no está amueblada"),
    ("mascotas", "acepta mascotas", "no acepta mascotas"),
    ("apto_profesional", "es apta uso profesional", "no es apta uso profesional"),
    ("apto_credito", "es apta crédito", "no es apta crédito"),
    ("acepta_financiacion", "acepta financiación", "no acepta financiación"),
    ("acepta_permuta", "acepta permuta", "no acepta permuta"),
)


def condition_phrases(conditions: PropertyConditions) -> list[str]:
    """The informed conditions as short phrases ("acepta mascotas", "pide contrato de 2
    años"), for answering a lead's question. Unknown fields say nothing."""
    phrases: list[str] = []
    if conditions.garantias:
        phrases.append(f"acepta {_guarantees(conditions.garantias)}")
    if conditions.contrato_minimo_meses:
        phrases.append(f"pide contrato de {months_label(conditions.contrato_minimo_meses)}")
    for name, yes, no in _FLAG_PHRASES:
        value = getattr(conditions, name)
        if value is not None:
            phrases.append(yes if value else no)
    return phrases
