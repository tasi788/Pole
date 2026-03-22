import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict
from loguru import logger


@dataclass
class UserProfile:
    """User profile with personality traits learned by AI."""
    user_id: int
    name: str = ""
    username: str = ""
    traits: list[str] = field(default_factory=list)
    notes: str = ""
    interaction_count: int = 0

    def to_prompt(self) -> str:
        """Convert profile to prompt text for AI."""
        parts = []
        if self.name:
            parts.append(f"名字：{self.name}")
        if self.username:
            parts.append(f"用戶名：@{self.username}")
        if self.traits:
            parts.append(f"性格特點：{', '.join(self.traits)}")
        if self.notes:
            parts.append(f"備註：{self.notes}")
        return "\n".join(parts) if parts else "（尚無資料）"


class UserProfileManager:
    """Manages user profiles stored in JSON file."""

    def __init__(self, storage_path: str = "data/user_profiles.json"):
        self.storage_path = Path(storage_path)
        self.profiles: dict[int, UserProfile] = {}
        self._load()

    def _load(self):
        """Load profiles from JSON file."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for user_id_str, profile_data in data.items():
                    user_id = int(user_id_str)
                    self.profiles[user_id] = UserProfile(
                        user_id=user_id,
                        name=profile_data.get("name", ""),
                        username=profile_data.get("username", ""),
                        traits=profile_data.get("traits", []),
                        notes=profile_data.get("notes", ""),
                        interaction_count=profile_data.get("interaction_count", 0),
                    )
                logger.info(f"Loaded {len(self.profiles)} user profiles")
            except Exception as e:
                logger.error(f"Failed to load user profiles: {e}")

    def _save(self):
        """Save profiles to JSON file."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = {}
            for user_id, profile in self.profiles.items():
                data[str(user_id)] = {
                    "name": profile.name,
                    "username": profile.username,
                    "traits": profile.traits,
                    "notes": profile.notes,
                    "interaction_count": profile.interaction_count,
                }
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save user profiles: {e}")

    def get_profile(self, user_id: int) -> Optional[UserProfile]:
        """Get user profile by ID."""
        return self.profiles.get(user_id)

    def get_or_create_profile(
        self,
        user_id: int,
        name: str = "",
        username: str = "",
    ) -> UserProfile:
        """Get existing profile or create new one."""
        if user_id not in self.profiles:
            self.profiles[user_id] = UserProfile(
                user_id=user_id,
                name=name,
                username=username,
            )
            self._save()
        else:
            profile = self.profiles[user_id]
            updated = False
            if name and profile.name != name:
                profile.name = name
                updated = True
            if username and profile.username != username:
                profile.username = username
                updated = True
            if updated:
                self._save()
        return self.profiles[user_id]

    def update_profile(
        self,
        user_id: int,
        traits: Optional[list[str]] = None,
        notes: Optional[str] = None,
    ):
        """Update user profile traits or notes."""
        if user_id not in self.profiles:
            return

        profile = self.profiles[user_id]
        if traits is not None:
            profile.traits = traits
        if notes is not None:
            profile.notes = notes
        self._save()

    def add_trait(self, user_id: int, trait: str):
        """Add a trait to user profile."""
        if user_id not in self.profiles:
            return
        profile = self.profiles[user_id]
        if trait not in profile.traits:
            profile.traits.append(trait)
            self._save()

    def increment_interaction(self, user_id: int):
        """Increment interaction count for user."""
        if user_id in self.profiles:
            self.profiles[user_id].interaction_count += 1
            if self.profiles[user_id].interaction_count % 10 == 0:
                self._save()
