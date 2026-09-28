from typing import Literal

from pydantic import BaseModel, field_validator


class ToolInvocation(BaseModel):
    command: str
    args: list[str] = []
    summary: str = ""


class NodeCitation(BaseModel):
    id: str
    role: Literal["primary", "supporting"] = "primary"


class SessionExplain(BaseModel):
    question: str
    answer_markdown: str
    node_ids: list[NodeCitation] = []
    tools_invoked: list[ToolInvocation] = []

    @field_validator("node_ids", mode="before")
    @classmethod
    def _normalize_node_ids(cls, value):
        # Accept a bare node id string (backward compatible with callers that
        # don't distinguish primary/supporting citations) alongside the
        # {"id", "role"} shape.
        if not value:
            return value
        return [{"id": v, "role": "primary"} if isinstance(v, str) else v for v in value]
