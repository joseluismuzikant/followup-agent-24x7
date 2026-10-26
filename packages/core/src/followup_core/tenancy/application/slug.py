import re
import unicodedata

from ..domain.errors import InvalidTenantNameError


def slugify(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name.strip())
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    if not slug:
        raise InvalidTenantNameError("Tenant name cannot be converted to a slug.")
    return slug
