from datetime import date, datetime
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

StateCode = Annotated[
    str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z]{2}$")
]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Age = Annotated[int, Field(ge=0, le=120)]


class ProfileIn(BaseModel):
    display_name: str | None = None
    date_of_birth: date | None = None
    playing_age_min: Age | None = None
    playing_age_max: Age | None = None
    genders: list[Label] = []
    location_city: str | None = None
    # Two-letter code: seeking locations arrive as "City, ST".
    location_state: StateCode | None = None
    union_status: str | None = None
    bio: str | None = None
    willing_to_travel: bool = False

    @model_validator(mode="after")
    def playing_range_complete(self) -> Self:
        low, high = self.playing_age_min, self.playing_age_max
        if (low is None) != (high is None):
            raise ValueError("set both playing_age_min and playing_age_max, or neither")
        if low is not None and high is not None and low > high:
            raise ValueError("playing_age_min must not exceed playing_age_max")
        return self


class ProfileOut(ProfileIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    updated_at: datetime
