"""Allowlisted presentation settings, separate from reading positions."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session
from app.models import ReaderPreferences

Font = Literal["georgia", "palatino", "sans"]
Theme = Literal["light", "sepia", "dark"]
Zoom = Literal["fit-page", "fit-width", "50", "75", "100", "125", "150", "175", "200", "250", "300"]


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, strict=True)
    font_family: Font = "georgia"
    font_size: int = Field(default=19, ge=14, le=36)
    line_height: float = Field(default=1.65, ge=1.2, le=2.2, allow_inf_nan=False)
    margin: int = Field(default=32, ge=8, le=80)
    theme: Theme = "light"
    pdf_zoom: Zoom = "fit-page"


class PreferencesPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    font_family: Font | None = None
    font_size: int | None = Field(default=None, ge=14, le=36)
    line_height: float | None = Field(default=None, ge=1.2, le=2.2, allow_inf_nan=False)
    margin: int | None = Field(default=None, ge=8, le=80)
    theme: Theme | None = None
    pdf_zoom: Zoom | None = None


def load_preferences(db: Session, user_id: int):
    record = db.get(ReaderPreferences, user_id)
    return Preferences.model_validate(record) if record else Preferences()


def patch_preferences(db: Session, user_id: int, patch: PreferencesPatch):
    changes = patch.model_dump(exclude_unset=True)
    if any(value is None for value in changes.values()):
        raise ValueError("Preference values cannot be null.")
    db.commit()
    if changes:
        # Only changed columns are written. A stale font-size change cannot
        # overwrite another device's newer theme or PDF zoom selection.
        db.execute(insert(ReaderPreferences).values(user_id=user_id, **(Preferences().model_dump() | changes)).on_conflict_do_update(index_elements=["user_id"], set_=changes))
        db.commit()
        db.expire_all()
    return load_preferences(db, user_id)
