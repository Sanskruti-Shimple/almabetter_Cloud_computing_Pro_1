from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing import Annotated


Identifier = Annotated[str, StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")]


class EventType(StrEnum):
    play = "play"
    like = "like"
    skip = "skip"


class EventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: EventType
    user_id: Identifier
    track_id: Identifier


class MusicEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID = Field(default_factory=uuid4)
    event_type: EventType
    user_id: str
    track_id: str
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EventAccepted(BaseModel):
    event_id: UUID
    status: str = "accepted"


class RecommendationResponse(BaseModel):
    user_id: str
    track_ids: list[str]
