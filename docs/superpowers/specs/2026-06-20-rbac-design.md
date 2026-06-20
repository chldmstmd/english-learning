# RBAC Design — Role-Based Access Control

**Date:** 2026-06-20  
**Status:** Approved  
**Scope:** Backend only — adds role field to User, role hierarchy, require_role dependencies, admin route protection, and first-admin bootstrap.

---

## Context

The app currently has authentication (JWT) and per-user data isolation, but no role differentiation. All authenticated users have identical permissions. The `/admin/*` routes are completely unprotected. This spec adds a minimal RBAC layer to distinguish admin roles from regular users, enabling admin content management in future work.

---

## Role Hierarchy

Four roles, ordered from most to least privileged:

```
super_admin > content_admin > premium > user
```

| Role | Description |
|------|-------------|
| `super_admin` | All permissions including user and role management |
| `content_admin` | Can manage public library content (create, edit, publish, trigger translations) |
| `premium` | Placeholder for future paid tier; no special permissions yet |
| `user` | Default role for all registered users |

A higher-privileged role implicitly has all permissions of lower roles. Permission checks use hierarchy index comparison, not explicit role lists per endpoint.

---

## Data Model

Add `role` column to the `users` table:

```python
# app/models/user.py
role: Mapped[str] = mapped_column(
    String(32), nullable=False, server_default="user"
)
```

- Stored as a plain string (not PostgreSQL native ENUM) to avoid `ALTER TYPE` complexity
- DB default `"user"` ensures safety if existing rows exist
- Since the project is in pure dev stage with no data to preserve, `create_all` on restart handles the migration

---

## Role Logic — `app/roles.py` (new file)

```python
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
    """True if user_role is >= required in the hierarchy."""
    try:
        return _HIERARCHY.index(user_role) <= _HIERARCHY.index(required)
    except ValueError:
        return False
```

All role hierarchy knowledge lives here. No role strings scattered across route files.

---

## Dependencies — `app/dependencies.py`

Add to existing file:

```python
from app.roles import UserRole, has_role

def require_role(required: UserRole):
    async def _check(current_user: User = Depends(get_current_user)):
        if not has_role(current_user.role, required):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return _check

require_content_admin = require_role(UserRole.content_admin)
require_super_admin = require_role(UserRole.super_admin)
```

Usage in route handlers:
```python
async def some_admin_endpoint(
    current_user: User = Depends(require_content_admin),
):
```

---

## First Admin Bootstrap

Add optional env var to `backend/.env`:
```
ADMIN_EMAIL=your@email.com
```

In `app/main.py` lifespan, after `create_all`:
- If `ADMIN_EMAIL` is set and a user with that email exists and their role is `"user"`, promote to `super_admin`
- If the email doesn't exist yet (not registered), skip silently — user registers first, then restarts the server
- No-op if already `super_admin`

This requires no separate script. Dev workflow: register → add email to `.env` → restart server.

Add `ADMIN_EMAIL` as an optional field in `app/config.py` (Settings).

---

## Existing Routes to Protect

| Route | Current | After |
|-------|---------|-------|
| `POST /admin/sync-voa` | No auth | `require_content_admin` |
| `GET /admin/sync-voa/logs` | No auth | `require_content_admin` |

---

## `/auth/me` Response

Add `role` to the `UserOut` schema so the frontend can conditionally show admin UI in future:

```python
class UserOut(BaseModel):
    id: str
    email: str
    role: str
```

---

## Out of Scope

- Frontend changes (no admin UI yet)
- `premium` role enforcement (placeholder only)
- User role management API (super_admin managing other users' roles — future work)
- Alembic migrations (not used in this project)
