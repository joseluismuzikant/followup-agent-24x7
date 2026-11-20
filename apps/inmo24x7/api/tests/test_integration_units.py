"""Pure pieces of the integrations: Tokko's mapping, the webhook signature and URL rule,
and the summary that goes with every lead."""

import hashlib
import hmac
from datetime import UTC, datetime
from uuid import uuid4

from inmo24x7_api.integrations.qualified import summary
from inmo24x7_api.integrations.tokko import map_property
from inmo24x7_api.integrations.webhook import sign, valid_url
from inmo24x7_api.leads.domain.lead import HandOffReason, Lead
from inmo24x7_api.leads.domain.sinks import QualifiedVisit
from inmo24x7_api.properties.domain.sources import ExternalListing, ListingFailure
from integration_fakes import rent, sale, tokko_property


def test_one_listing_per_operation_with_its_own_price_and_currency() -> None:
    listings = map_property(tokko_property(7, operations=[sale(120000), rent(700000)]))

    assert all(isinstance(item, ExternalListing) for item in listings)
    assert [
        (i.fields.operation.value, i.fields.price, i.fields.currency.value)
        for i in listings
        if isinstance(i, ExternalListing)
    ] == [("rent", 700000, "ARS"), ("sale", 120000, "USD")]


def test_a_regular_rent_wins_over_a_temporary_one() -> None:
    temporary = {
        "operation_type": "Alquiler temporario",
        "prices": [{"currency": "USD", "price": 900}],
    }

    (listing,) = map_property(tokko_property(8, operations=[temporary, rent(650000)]))

    assert isinstance(listing, ExternalListing) and listing.fields.price == 650000


def test_unusable_properties_say_why() -> None:
    no_link = tokko_property(9)
    no_link["public_url"] = ""
    euros = tokko_property(
        10, operations=[{"operation_type": "Venta", "prices": [{"currency": "EUR", "price": 1}]}]
    )

    (link_failure,) = map_property(no_link)
    (euro_failure,) = map_property(euros)
    (none,) = map_property(tokko_property(11, operations=[{"operation_type": "Permuta"}]))

    assert isinstance(link_failure, ListingFailure)
    assert link_failure.reason == "no tiene link público."
    assert isinstance(euro_failure, ListingFailure)
    assert euro_failure.reason == "la venta la moneda no es ARS ni USD."
    assert isinstance(none, ListingFailure) and none.reason == "no está en venta ni en alquiler."


def test_the_zone_falls_back_to_the_last_part_of_the_location() -> None:
    item = tokko_property(12)
    item["location"] = {"full_location": "Argentina | GBA Norte | Vicente López"}

    (listing,) = map_property(item)

    assert isinstance(listing, ExternalListing) and listing.fields.zone == "Vicente López"


def test_the_signature_is_an_hmac_of_the_raw_body() -> None:
    body = b'{"event":"ping"}'
    expected = hmac.new(b"whsec_x", body, hashlib.sha256).hexdigest()

    assert sign("whsec_x", body) == f"sha256={expected}"


def test_webhook_urls_are_https_except_local_development() -> None:
    assert valid_url("https://hooks.zapier.com/hooks/catch/1/abc/")
    assert not valid_url("http://hooks.zapier.com/x")
    assert not valid_url("http://localhost:9000/x")
    assert valid_url("http://localhost:9000/x", allow_http=True)
    assert not valid_url("http://crm.example.com/x", allow_http=True)
    assert not valid_url("https://")


def _lead(**answers) -> Lead:
    now = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)
    lead = Lead.start(
        tenant_id=uuid4(),
        thread_id=uuid4(),
        thread_key="t:whatsapp:5491155550188",
        channel="whatsapp",
        is_test=False,
        now=now,
    )
    return lead.with_details(answers=answers, visitor_name="Ana", contact=None, at=now)


def test_the_summary_reads_like_the_team_would_write_it() -> None:
    lead = _lead(
        operation="alquiler",
        rooms=2,
        zone="Palermo",
        budget={"amount": 900000, "currency": "ARS"},
        garantia="caucion",
    ).hand_off(HandOffReason.VISIT, datetime(2026, 11, 17, 12, 5, tzinfo=UTC))
    visit = QualifiedVisit(
        datetime(2026, 11, 18, 9, 0, tzinfo=UTC), "mié 18/11 09:00", "Gorriti 4800", "proposed"
    )

    assert summary(lead, visit, []) == (
        "Busca alquiler 2 amb. en Palermo, hasta $900.000, garantía: caución. "
        "Pidió visita mié 18/11 09:00 en Gorriti 4800. — vía inmo24x7"
    )


def test_the_summary_says_baja_a_person_and_the_web_button() -> None:
    from dataclasses import replace

    lead = replace(
        _lead(operation="compra").hand_off(HandOffReason.HUMAN, datetime.now(UTC)),
        do_not_contact=True,
        source="web_button",
    )

    assert summary(lead, None, []) == (
        "Busca compra. Pidió hablar con alguien del equipo. Llegó por el botón de la web. "
        "Pidió no ser contactado (BAJA): no le escribas por WhatsApp. — vía inmo24x7"
    )
