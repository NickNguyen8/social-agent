"""
types.py - Shared enums, constants, and exceptions for Social Agent.
"""

from enum import Enum

# Mapping target type → platform string used in FormatRenderer
PLATFORM_MAP = {
    "page": "facebook",
    "group": "facebook",
    "profile": "facebook",
    "linkedin_profile": "linkedin",
    "linkedin_company": "linkedin",
}


class TargetType(str, Enum):
    """Enum cho target types — loại bỏ magic strings rải rác."""
    PAGE = "page"
    GROUP = "group"
    PROFILE = "profile"
    LINKEDIN_PROFILE = "linkedin_profile"
    LINKEDIN_COMPANY = "linkedin_company"

    @property
    def platform(self) -> str:
        return PLATFORM_MAP.get(self.value, "facebook")

    @property
    def is_facebook(self) -> bool:
        return self in (self.PAGE, self.GROUP, self.PROFILE)

    @property
    def is_linkedin(self) -> bool:
        return self in (self.LINKEDIN_PROFILE, self.LINKEDIN_COMPANY)


class SocialAgentError(Exception):
    """Base exception for Social Agent errors."""


class ConfigError(SocialAgentError):
    """Config loading or validation error."""


class PostingError(SocialAgentError):
    """Error while dispatching a post."""
