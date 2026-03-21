from enum import Enum
from typing import Optional
from dataclasses import dataclass, field
from loguru import logger


class PermissionLevel(Enum):
    """Permission levels for users."""
    GUEST = 0
    USER = 1
    ADMIN = 2
    OWNER = 3


@dataclass
class Permission:
    """Represents a single permission."""
    skill: str
    action: str
    description: str = ""
    min_level: PermissionLevel = PermissionLevel.USER
    default_allowed: bool = True


@dataclass
class UserPermissions:
    """User's permission settings."""
    user_id: int
    level: PermissionLevel = PermissionLevel.USER
    allowed_permissions: set[str] = field(default_factory=set)
    denied_permissions: set[str] = field(default_factory=set)


class PermissionManager:
    """Manages permissions for users and skills."""

    def __init__(self):
        self.users: dict[int, UserPermissions] = {}
        self.permissions: dict[str, Permission] = {}
        self.owner_ids: set[int] = set()
        self.admin_ids: set[int] = set()

    def register_permission(self, permission: Permission):
        """Register a permission."""
        key = f"{permission.skill}.{permission.action}"
        self.permissions[key] = permission
        logger.debug(f"Registered permission: {key}")

    def set_owner(self, user_id: int):
        """Set a user as owner."""
        self.owner_ids.add(user_id)
        self._ensure_user(user_id).level = PermissionLevel.OWNER

    def set_admin(self, user_id: int):
        """Set a user as admin."""
        self.admin_ids.add(user_id)
        self._ensure_user(user_id).level = PermissionLevel.ADMIN

    def _ensure_user(self, user_id: int) -> UserPermissions:
        """Ensure user exists in the system."""
        if user_id not in self.users:
            self.users[user_id] = UserPermissions(user_id=user_id)
        return self.users[user_id]

    def grant(self, user_id: int, skill: str, action: str):
        """Grant a specific permission to a user."""
        user = self._ensure_user(user_id)
        key = f"{skill}.{action}"
        user.allowed_permissions.add(key)
        user.denied_permissions.discard(key)
        logger.info(f"Granted {key} to user {user_id}")

    def deny(self, user_id: int, skill: str, action: str):
        """Deny a specific permission from a user."""
        user = self._ensure_user(user_id)
        key = f"{skill}.{action}"
        user.denied_permissions.add(key)
        user.allowed_permissions.discard(key)
        logger.info(f"Denied {key} from user {user_id}")

    async def check(self, user_id: int, permission: Permission) -> bool:
        """Check if user has a specific permission."""
        user = self._ensure_user(user_id)
        key = f"{permission.skill}.{permission.action}"

        if user.level == PermissionLevel.OWNER:
            return True

        if key in user.denied_permissions:
            logger.debug(f"Permission {key} explicitly denied for user {user_id}")
            return False

        if key in user.allowed_permissions:
            return True

        if user.level.value >= permission.min_level.value:
            return permission.default_allowed

        logger.debug(f"Permission {key} denied for user {user_id} (level: {user.level})")
        return False

    def get_user_level(self, user_id: int) -> PermissionLevel:
        """Get user's permission level."""
        return self._ensure_user(user_id).level
