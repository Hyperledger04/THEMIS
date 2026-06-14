"""Tests for RBAC permission matrix — themis/security/permissions.py."""
import pytest
from themis.security.permissions import (
    PERMISSION_MATRIX,
    _has_permission,
    check_permission,
)


class TestHasPermission:
    # --- admin role ---
    def test_admin_has_all_matter_permissions(self):
        assert _has_permission("admin", "matter.create")
        assert _has_permission("admin", "matter.read")
        assert _has_permission("admin", "matter.delete")

    def test_admin_has_user_management(self):
        assert _has_permission("admin", "user.create")
        assert _has_permission("admin", "user.delete")

    def test_admin_has_key_rotate(self):
        assert _has_permission("admin", "key.rotate")

    def test_admin_has_gdpr(self):
        assert _has_permission("admin", "gdpr.export")
        assert _has_permission("admin", "gdpr.erase")

    # --- partner role ---
    def test_partner_can_create_matter(self):
        assert _has_permission("partner", "matter.create")

    def test_partner_can_read_audit(self):
        assert _has_permission("partner", "audit.read")

    def test_partner_cannot_rotate_key(self):
        assert not _has_permission("partner", "key.rotate")

    def test_partner_cannot_manage_users(self):
        assert not _has_permission("partner", "user.create")
        assert not _has_permission("partner", "user.delete")

    # --- associate role ---
    def test_associate_can_draft(self):
        assert _has_permission("associate", "draft.create")
        assert _has_permission("associate", "draft.read")

    def test_associate_can_research(self):
        assert _has_permission("associate", "research.run")

    def test_associate_cannot_read_audit(self):
        assert not _has_permission("associate", "audit.read")

    def test_associate_cannot_manage_users(self):
        assert not _has_permission("associate", "user.create")

    # --- viewer role ---
    def test_viewer_can_read_matter(self):
        assert _has_permission("viewer", "matter.read")

    def test_viewer_cannot_create_matter(self):
        assert not _has_permission("viewer", "matter.create")

    def test_viewer_cannot_run_research(self):
        assert not _has_permission("viewer", "research.run")

    def test_viewer_cannot_draft(self):
        assert not _has_permission("viewer", "draft.create")

    # --- unknown role ---
    def test_unknown_role_has_no_permissions(self):
        assert not _has_permission("unknown_role", "matter.read")
        assert not _has_permission("", "draft.create")

    # --- wildcard matching ---
    def test_wildcard_draft_covers_subpermissions(self):
        # admin has "draft.*" which should cover any draft.X
        assert _has_permission("admin", "draft.create")
        assert _has_permission("admin", "draft.approve")
        assert _has_permission("admin", "draft.archive")

    def test_partial_namespace_does_not_match(self):
        # "matter.*" should not grant "matter_archive.read"
        assert not _has_permission("admin", "matter_archive.read")


class TestCheckPermission:
    def test_delegates_to_has_permission(self):
        assert check_permission("admin", "key.rotate")
        assert not check_permission("viewer", "key.rotate")


class TestPermissionMatrix:
    def test_all_four_roles_defined(self):
        for role in ("admin", "partner", "associate", "viewer"):
            assert role in PERMISSION_MATRIX

    def test_admin_is_superset_of_associate(self):
        # Every explicit (non-wildcard) associate permission is also in admin
        associate_perms = {
            p for p in PERMISSION_MATRIX["associate"] if "*" not in p
        }
        for perm in associate_perms:
            assert _has_permission("admin", perm), f"admin missing: {perm}"

    def test_partner_is_superset_of_associate(self):
        associate_perms = {
            p for p in PERMISSION_MATRIX["associate"] if "*" not in p
        }
        for perm in associate_perms:
            assert _has_permission("partner", perm), f"partner missing: {perm}"
