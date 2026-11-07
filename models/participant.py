from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, HttpUrl

ParticipantType = Literal["host", "guest"]

class Participant(BaseModel):
    # Existing people files carry hand-maintained keys (is_hidden, active, mastodon) that must survive a re-save
    model_config = ConfigDict(extra='allow')

    type: ParticipantType
    username: str  # Unique ID
    title: str
    bio: Optional[str] = None
    avatar: Optional[str] = None
    avatar_small: Optional[str] = None
    homepage: Optional[HttpUrl] = None
    twitter: Optional[HttpUrl] = None
    linkedin: Optional[HttpUrl] = None
    instagram: Optional[HttpUrl] = None
    youtube: Optional[HttpUrl] = None
