from app.roles import UserRole, has_role


def test_super_admin_has_all_roles():
    assert has_role("super_admin", UserRole.super_admin)
    assert has_role("super_admin", UserRole.content_admin)
    assert has_role("super_admin", UserRole.premium)
    assert has_role("super_admin", UserRole.user)


def test_content_admin_cannot_act_as_super_admin():
    assert not has_role("content_admin", UserRole.super_admin)


def test_content_admin_has_content_and_below():
    assert has_role("content_admin", UserRole.content_admin)
    assert has_role("content_admin", UserRole.premium)
    assert has_role("content_admin", UserRole.user)


def test_premium_cannot_act_as_admin():
    assert not has_role("premium", UserRole.super_admin)
    assert not has_role("premium", UserRole.content_admin)


def test_user_only_has_user_role():
    assert has_role("user", UserRole.user)
    assert not has_role("user", UserRole.premium)
    assert not has_role("user", UserRole.content_admin)
    assert not has_role("user", UserRole.super_admin)


def test_unknown_role_returns_false():
    assert not has_role("hacker", UserRole.user)
    assert not has_role("", UserRole.user)
