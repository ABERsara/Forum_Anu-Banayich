"""
Pydantic schemas for AI agent domains.
"""

from pydantic import BaseModel


class AgentDomainResponse(BaseModel):
    """GET /agents – one agent domain in the catalog visible to the user."""

    id: str
    name: str
    description: str

    model_config = {"from_attributes": True}
