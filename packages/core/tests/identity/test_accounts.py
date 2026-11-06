"""Invitation-only accounts: the temporary password, the link, the forced change."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from followup_core.identity.application.accounts import (
    INVITATION_EMAIL_JOB,
    AcceptInvitation,
    ChangePassword,
    GetInvitation,
    InviteOwner,
    ResendInvitation,
    ResetTemporaryPassword,
)
from followup_core.identity.application.invitation_email import (
    InvitationEmailData,
    SendInvitationEmail,
)
from followup_core.identity.domain.account import (
    Account,
    check_password,
    temporary_password,
)
from followup_core.identity.domain.errors import (
    InvitationExpiredError,
    InvitationNotFoundError,
    InvitationUsedError,
    OwnerAlreadyJoinedError,
    WeakPasswordError,
)
from followup_core.identity.domain.invitation import (
    Invitation,
    InvitationStatus,
    hash_token,
)
from followup_core.identity.infrastructure.directories import hash_password, password_matches
from followup_core.notifications.domain.email import Email
from followup_core.scheduling.domain.jobs import Job, JobStatus, NewJob
from followup_core.tenancy.domain.audit import AuditEvent
from followup_core.tenancy.domain.owner_claims import OwnerClaim
from followup_core.tenancy.domain.product import Product
from followup_core.tenancy.domain.tenant import Tenant

NOW = datetime(2026, 11, 6, 12, tzinfo=UTC)
PRODUCT = Product.INMO24X7


class Accounts:
    def __init__(self) -> None:
        self.items: dict[UUID, Account] = {}

    def get(self, user_id: UUID) -> Account | None:
        return self.items.get(user_id)

    def get_by_email(self, email: str) -> Account | None:
        return next((a for a in self.items.values() if a.email == email.lower()), None)

    def add(self, account: Account) -> None:
        self.items[account.user_id] = account

    def set_must_change(self, user_id: UUID, value: bool, at: datetime | None = None) -> None:
        self.items[user_id] = replace(
            self.items[user_id], must_change_password=value, password_changed_at=at
        )


class Directory:
    def __init__(self) -> None:
        self.passwords: dict[str, str] = {}

    def create_user(self, email: str, password: str) -> UUID:
        self.passwords[email] = password
        return uuid4()

    def set_password(self, user_id: UUID, email: str, password: str) -> None:
        self.passwords[email] = password


class Invitations:
    def __init__(self) -> None:
        self.items: list[Invitation] = []

    def get_by_token(self, token: str) -> Invitation | None:
        return next((i for i in self.items if i.token_hash == hash_token(token)), None)

    def latest_for(self, product: Product, email: str) -> Invitation | None:
        found = [i for i in self.items if i.product == product and i.email == email]
        return found[-1] if found else None

    def add(self, invitation: Invitation) -> None:
        self.items = [
            replace(i, revoked_at=invitation.created_at)
            if i.email == invitation.email and i.accepted_at is None and i.revoked_at is None
            else i
            for i in self.items
        ]
        self.items.append(invitation)

    def mark_accepted(self, invitation_id: UUID, at: datetime) -> None:
        self.items = [i.accept(at) if i.id == invitation_id else i for i in self.items]


class Claims:
    def __init__(self) -> None:
        self.items: dict[str, OwnerClaim] = {}

    def get_open(self, email: str) -> OwnerClaim | None:
        claim = self.items.get(email)
        return claim if claim and claim.claimed_at is None else None

    def get_for_tenant(self, tenant_id: UUID) -> OwnerClaim | None:
        return next((c for c in self.items.values() if c.tenant_id == tenant_id), None)

    def exists(self, email: str) -> bool:
        return email in self.items

    def add(self, claim: OwnerClaim) -> None:
        self.items[claim.email] = claim

    def mark_claimed(self, email: str, at: datetime) -> None:
        self.items[email] = replace(self.items[email], claimed_at=at)


class Queue:
    def __init__(self) -> None:
        self.jobs: list[NewJob] = []

    def enqueue(self, job: NewJob) -> bool:
        self.jobs.append(job)
        return True


class Audit:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        self.events.append(event)

    def latest(self, tenant_id: UUID, limit: int) -> list[AuditEvent]:
        return []

    def actions(self) -> list[str]:
        return [str(e.action) for e in self.events]


class Tenants:
    def __init__(self, tenant: Tenant) -> None:
        self.tenant = tenant

    def get_by_id(self, tenant_id: UUID) -> Tenant | None:
        return self.tenant if tenant_id == self.tenant.id else None


class World:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now
        self.accounts = Accounts()
        self.directory = Directory()
        self.invitations = Invitations()
        self.claims = Claims()
        self.queue = Queue()
        self.audit = Audit()
        self.tenant = Tenant.create("Villa Urquiza Propiedades")
        self.claims.add(OwnerClaim("duenia@villa.test", self.tenant.id, now))
        self.passwords = iter(["Temporal-1", "Temporal-2", "Temporal-3"])

    def clock(self) -> datetime:
        return self.now

    def invite(self) -> InviteOwner:
        return InviteOwner(
            PRODUCT,
            self.accounts,
            self.directory,
            self.claims,
            self.invitations,
            self.queue,
            self.audit,
            self.clock,
            lambda: next(self.passwords),
        )

    def accept(self) -> AcceptInvitation:
        return AcceptInvitation(
            self.invitations, self.accounts, self.directory, self.audit, self.clock
        )

    def view(self, token: str):
        return GetInvitation(
            self.invitations, self.accounts, Tenants(self.tenant), self.clock
        ).execute(token)


def test_password_rules() -> None:
    check_password("una-clave-larga", "a@b.test")
    for password, code in [
        ("corta", "password_too_short"),
        ("x" * 73, "password_too_long"),
        ("A@B.test", "password_is_email"),
    ]:
        with pytest.raises(WeakPasswordError) as raised:
            check_password(password, "a@b.test")
        assert raised.value.code == code


def test_temporary_passwords_are_long_and_unambiguous() -> None:
    password = temporary_password()
    assert len(password) == 12
    assert not set(password) & set("0O1lI")


def test_dev_password_hashes_verify_only_the_same_password() -> None:
    stored = hash_password("local-1234")
    assert password_matches("local-1234", stored)
    assert not password_matches("local-12345", stored)
    assert hash_password("local-1234") != stored  # salted


def test_inviting_a_new_owner_creates_the_account_with_a_temporary_password() -> None:
    world = World()

    result = world.invite().execute(uuid4(), world.tenant.id)

    assert result.temporary_password == "Temporal-1"
    account = world.accounts.get_by_email("duenia@villa.test")
    assert account is not None and account.must_change_password
    assert world.directory.passwords["duenia@villa.test"] == "Temporal-1"
    (job,) = world.queue.jobs
    assert job.kind == INVITATION_EMAIL_JOB and job.payload["token"] == result.token
    assert world.audit.events[0].details == {"source": "new_account"}
    assert "Temporal-1" not in str(job.payload)


def test_a_person_with_an_account_keeps_their_password() -> None:
    world = World()
    user_id = uuid4()
    world.accounts.add(Account(user_id, "duenia@villa.test", False, NOW, NOW))

    result = world.invite().execute(uuid4(), world.tenant.id)

    assert result.temporary_password is None
    assert world.directory.passwords == {}
    assert world.view(result.token).needs_password is False
    with pytest.raises(InvitationUsedError):
        world.accept().execute(result.token, "otra-clave-nueva")


def test_the_link_sets_the_password_once() -> None:
    world = World()
    token = world.invite().execute(uuid4(), world.tenant.id).token
    assert world.view(token).status is InvitationStatus.VALID

    email = world.accept().execute(token, "mi-clave-nueva")

    assert email == "duenia@villa.test"
    assert world.directory.passwords[email] == "mi-clave-nueva"
    account = world.accounts.get_by_email(email)
    assert account is not None and not account.must_change_password
    assert world.view(token).status is InvitationStatus.USED
    with pytest.raises(InvitationUsedError):
        world.accept().execute(token, "otra-clave-nueva")
    assert world.audit.actions()[-1] == "invitation_accepted"


def test_the_link_rejects_weak_passwords_and_unknown_tokens() -> None:
    world = World()
    token = world.invite().execute(uuid4(), world.tenant.id).token

    with pytest.raises(WeakPasswordError):
        world.accept().execute(token, "corta")
    with pytest.raises(InvitationNotFoundError):
        world.accept().execute("no-existe", "mi-clave-nueva")
    with pytest.raises(InvitationNotFoundError):
        world.view("no-existe")


def test_a_link_expires_after_seven_days() -> None:
    world = World()
    token = world.invite().execute(uuid4(), world.tenant.id).token
    world.now = NOW + timedelta(days=7)

    assert world.view(token).status is InvitationStatus.EXPIRED
    with pytest.raises(InvitationExpiredError):
        world.accept().execute(token, "mi-clave-nueva")


def test_resending_replaces_the_previous_link() -> None:
    world = World()
    first = world.invite().execute(uuid4(), world.tenant.id).token

    second = ResendInvitation(
        PRODUCT, world.claims, world.invitations, world.queue, world.audit, world.clock
    ).execute(uuid4(), world.tenant.id)

    assert world.view(first).status is InvitationStatus.EXPIRED
    assert world.view(second).status is InvitationStatus.VALID
    assert world.audit.actions() == ["owner_invited", "invitation_resent"]


def test_a_new_temporary_password_only_before_the_owner_chose_theirs() -> None:
    world = World()
    token = world.invite().execute(uuid4(), world.tenant.id).token
    reset = ResetTemporaryPassword(
        world.accounts,
        world.directory,
        world.claims,
        world.audit,
        world.clock,
        lambda: next(world.passwords),
    )

    assert reset.execute(uuid4(), world.tenant.id) == "Temporal-2"
    assert world.directory.passwords["duenia@villa.test"] == "Temporal-2"

    world.accept().execute(token, "mi-clave-nueva")
    with pytest.raises(OwnerAlreadyJoinedError):
        reset.execute(uuid4(), world.tenant.id)


def test_after_the_owner_signs_up_there_is_nothing_to_resend() -> None:
    world = World()
    world.invite().execute(uuid4(), world.tenant.id)
    world.claims.mark_claimed("duenia@villa.test", NOW)

    with pytest.raises(OwnerAlreadyJoinedError):
        ResendInvitation(
            PRODUCT, world.claims, world.invitations, world.queue, world.audit
        ).execute(uuid4(), world.tenant.id)


def test_changing_the_password_clears_the_forced_change() -> None:
    world = World()
    world.invite().execute(uuid4(), world.tenant.id)
    account = world.accounts.get_by_email("duenia@villa.test")
    assert account is not None

    ChangePassword(world.accounts, world.directory, world.clock).execute(
        account.user_id, account.email, "mi-clave-nueva"
    )

    changed = world.accounts.get(account.user_id)
    assert changed is not None and not changed.must_change_password
    assert changed.password_changed_at == NOW
    with pytest.raises(WeakPasswordError):
        ChangePassword(world.accounts, world.directory).execute(
            account.user_id, account.email, account.email
        )


def test_the_invitation_email_has_the_link_and_never_the_password() -> None:
    sent: list[Email] = []

    class Sender:
        def send(self, email: Email) -> None:
            sent.append(email)

    handler = SendInvitationEmail(
        lambda _id: InvitationEmailData("duenia@villa.test", "Villa Urquiza"),
        Sender(),
        "inmo24x7",
        "http://localhost:5173/",
    )
    handler(
        Job(
            uuid4(),
            INVITATION_EMAIL_JOB,
            {"invitation_id": str(uuid4()), "token": "abc"},
            NOW,
            JobStatus.RUNNING,
            1,
            5,
        )
    )

    (email,) = sent
    assert email.to == ["duenia@villa.test"]
    assert "http://localhost:5173/invitacion?token=abc" in email.text
    assert "Villa Urquiza" in email.subject
