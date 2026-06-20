from enum import Enum


class UserRole(str, Enum):
    super_admin = "super_admin"
    content_admin = "content_admin"
    premium = "premium"
    user = "user"


_HIERARCHY = [
    UserRole.super_admin,
    UserRole.content_admin,
    UserRole.premium,
    UserRole.user,
]


def has_role(user_role: str, required: UserRole) -> bool:
    """True if user_role is >= required in the hierarchy (i.e. equal or more privileged)."""
    try:
        return _HIERARCHY.index(user_role) <= _HIERARCHY.index(required)
    except ValueError:
        return False
