"""Admin API endpoints — hydration management, protected by admin key."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.services.hydration_service import HydrationService

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

settings = get_settings()

# In-memory task store (production would use Redis)
_tasks: dict[str, dict] = {}


def _verify_admin_key(x_admin_key: str | None = Header(None, alias="X-Admin-Key")) -> None:
    """Verify the admin API key header."""
    if not settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Admin API key not configured.",
        )
    if not x_admin_key or x_admin_key != settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin key.",
        )


class HydrateRequest(BaseModel):
    age: int = Field(..., ge=6, le=18, description="Target age group (6-18)")
    limit: int = Field(100, ge=1, le=500, description="Maximum books to fetch")


class HydrateResponse(BaseModel):
    task_id: str
    status: str
    message: str


class HydrateStatusResponse(BaseModel):
    task_id: str
    status: str  # 'pending', 'processing', 'completed', 'failed'
    books_processed: int = 0
    questions_generated: int = 0
    errors: list[str] = []


@router.post("/hydrate", response_model=HydrateResponse, status_code=status.HTTP_202_ACCEPTED)
def trigger_hydration(
    request: HydrateRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_verify_admin_key),
):
    """Trigger a book data hydration job for a given age group."""
    task_id = str(uuid.uuid4())
    _tasks[task_id] = {
        "task_id": task_id,
        "status": "processing",
        "books_processed": 0,
        "questions_generated": 0,
        "errors": [],
    }

    # Run hydration synchronously for now (Celery integration is a separate task)
    try:
        service = HydrationService(db, openai_api_key=settings.openai_api_key)
        books = service.fetch_top_books_for_age(request.age, request.limit)
        _tasks[task_id]["books_processed"] = len(books)
        _tasks[task_id]["status"] = "completed"
    except Exception as e:
        _tasks[task_id]["status"] = "failed"
        _tasks[task_id]["errors"].append(str(e))

    return HydrateResponse(
        task_id=task_id,
        status=_tasks[task_id]["status"],
        message=f"Hydration job started for age {request.age}",
    )


@router.get("/hydrate/{task_id}/status", response_model=HydrateStatusResponse)
def get_hydration_status(
    task_id: str,
    _: None = Depends(_verify_admin_key),
):
    """Get the status of a hydration job."""
    try:
        uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid task ID.")

    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")

    return HydrateStatusResponse(
        task_id=task["task_id"],
        status=task["status"],
        books_processed=task.get("books_processed", 0),
        questions_generated=task.get("questions_generated", 0),
        errors=task.get("errors", []),
    )
