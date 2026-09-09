"""
Pydantic schemas for likes.
"""

from pydantic import BaseModel


class LikeResponse(BaseModel):
    """PATCH .../like – result of toggling a like."""

    liked: bool
    like_count: int
