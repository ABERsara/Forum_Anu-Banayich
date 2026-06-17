"""
Re-exports all schemas for convenience.

When you add a new schema file, export its classes here.
"""

from app.schemas.auth import (
    LoginRequest,
    OtpVerifyRequest,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.forum import (
    ConversationSummary,
    DirectMessageCreate,
    DirectMessageResponse,
    ForumPostCreate,
    ForumPostListResponse,
    ForumPostResponse,
)
from app.schemas.professional import (
    ProfessionalAnswerRequest,
    ProfessionalQueryCreate,
    ProfessionalQueryResponse,
    PublicQAResponse,
)
from app.schemas.report import (
    ReportCreate,
    ReportDecideRequest,
    ReportListResponse,
    ReportResponse,
)
from app.schemas.user import (
    ProfessionalProfile,
    RegistrationRejectRequest,
    SuspendUserRequest,
    UserAdminView,
    UserProfile,
    UserPublic,
)

__all__ = [
    "RegisterRequest",
    "OtpVerifyRequest",
    "LoginRequest",
    "TokenResponse",
    "UserPublic",
    "UserProfile",
    "UserAdminView",
    "ProfessionalProfile",
    "RegistrationRejectRequest",
    "SuspendUserRequest",
    "ForumPostCreate",
    "ForumPostResponse",
    "ForumPostListResponse",
    "DirectMessageCreate",
    "DirectMessageResponse",
    "ConversationSummary",
    "ProfessionalQueryCreate",
    "ProfessionalQueryResponse",
    "ProfessionalAnswerRequest",
    "PublicQAResponse",
    "ReportCreate",
    "ReportResponse",
    "ReportDecideRequest",
    "ReportListResponse",
]
