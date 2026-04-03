"""
Announcement endpoints for the High School Management System API
"""

from datetime import date
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementBase(BaseModel):
    """Announcement payload used for creation and update."""

    message: str = Field(min_length=1, max_length=500)
    expires_at: date
    starts_at: Optional[date] = None


class AnnouncementResponse(AnnouncementBase):
    """Serialized announcement response returned to clients."""

    id: str


def _assert_teacher(username: Optional[str]) -> None:
    """Validate that the request is authenticated as a teacher."""

    if not username:
        raise HTTPException(status_code=401, detail="Authentication required")

    teacher = teachers_collection.find_one({"_id": username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")


def _validate_dates(starts_at: Optional[date], expires_at: date) -> None:
    """Ensure the optional start date is not after the expiration date."""

    if starts_at and starts_at > expires_at:
        raise HTTPException(
            status_code=400,
            detail="Start date must be on or before expiration date"
        )


def _serialize_announcement(announcement: Dict[str, Any]) -> AnnouncementResponse:
    """Convert DB document to response model."""

    return AnnouncementResponse(
        id=str(announcement["_id"]),
        message=announcement["message"],
        expires_at=announcement["expires_at"],
        starts_at=announcement.get("starts_at")
    )


@router.get("", response_model=List[AnnouncementResponse])
@router.get("/", response_model=List[AnnouncementResponse])
def get_announcements(
    include_inactive: bool = False,
    teacher_username: Optional[str] = Query(None)
) -> List[AnnouncementResponse]:
    """Return announcements.

    Public requests receive currently active announcements only.
    Set include_inactive=true to return all announcements.
    """

    query: Dict[str, Any] = {}

    if include_inactive:
        _assert_teacher(teacher_username)
    else:
        today = date.today().isoformat()
        query = {
            "expires_at": {"$gte": today},
            "$or": [
                {"starts_at": {"$exists": False}},
                {"starts_at": None},
                {"starts_at": {"$lte": today}}
            ]
        }

    announcements: List[AnnouncementResponse] = []
    for announcement in announcements_collection.find(query).sort([
        ("starts_at", 1),
        ("expires_at", 1),
        ("_id", 1)
    ]):
        announcements.append(_serialize_announcement(announcement))

    return announcements


@router.post("", response_model=AnnouncementResponse)
@router.post("/", response_model=AnnouncementResponse)
def create_announcement(
    announcement: AnnouncementBase,
    teacher_username: Optional[str] = Query(None)
) -> AnnouncementResponse:
    """Create an announcement. Requires signed-in teacher."""

    _assert_teacher(teacher_username)
    _validate_dates(announcement.starts_at, announcement.expires_at)

    new_id = str(uuid4())

    new_doc: Dict[str, Any] = {
        "_id": new_id,
        "message": announcement.message.strip(),
        "starts_at": announcement.starts_at.isoformat() if announcement.starts_at else None,
        "expires_at": announcement.expires_at.isoformat()
    }

    announcements_collection.insert_one(new_doc)
    return _serialize_announcement(new_doc)


@router.put("/{announcement_id}", response_model=AnnouncementResponse)
def update_announcement(
    announcement_id: str,
    announcement: AnnouncementBase,
    teacher_username: Optional[str] = Query(None)
) -> AnnouncementResponse:
    """Update an announcement. Requires signed-in teacher."""

    _assert_teacher(teacher_username)
    _validate_dates(announcement.starts_at, announcement.expires_at)

    result = announcements_collection.update_one(
        {"_id": announcement_id},
        {
            "$set": {
                "message": announcement.message.strip(),
                "starts_at": announcement.starts_at.isoformat() if announcement.starts_at else None,
                "expires_at": announcement.expires_at.isoformat()
            }
        }
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    updated = announcements_collection.find_one({"_id": announcement_id})
    return _serialize_announcement(updated)


@router.delete("/{announcement_id}")
def delete_announcement(
    announcement_id: str,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, str]:
    """Delete an announcement. Requires signed-in teacher."""

    _assert_teacher(teacher_username)

    result = announcements_collection.delete_one({"_id": announcement_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}
