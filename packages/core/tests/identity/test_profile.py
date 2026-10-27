from uuid import uuid4

import pytest
from followup_core.identity.domain.errors import IdentityError
from followup_core.identity.domain.profile import Profile, Role


def test_roles_are_stable_values() -> None:
    assert {role.value for role in Role} == {"owner", "manager", "agent", "viewer"}


def test_profile_normalizes_email() -> None:
    profile = Profile(
        id=uuid4(),
        email="  Owner@Example.com ",
        display_name="Owner",
        tenant_id=uuid4(),
        role=Role.OWNER,
        is_platform_admin=False,
    )

    assert profile.email == "owner@example.com"


def test_profile_rejects_blank_email() -> None:
    with pytest.raises(IdentityError):
        Profile(
            id=uuid4(),
            email="   ",
            display_name="Owner",
            tenant_id=uuid4(),
            role=Role.OWNER,
            is_platform_admin=False,
        )
