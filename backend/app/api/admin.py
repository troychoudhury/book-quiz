"""Admin API endpoints — hydration management, protected by admin key."""

import asyncio
import hmac
import logging
import threading
import time
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal, get_db
from app.models.book import Book
from app.services.hydration_service import GRADE_AGE_MAP, HydrationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

settings = get_settings()

# In-memory task store (production would use Redis). Lost on restart — an
# acceptable limitation (S2): hydrate-all is idempotent (ISBN dedup), so a
# lost task can simply be re-triggered after a restart.
_tasks: dict[str, dict] = {}

# Guards all access to _tasks: worker threads mutate task state while the
# event loop reads it via the status endpoints (H2 fix).
_tasks_lock = threading.Lock()

# Cap for retained terminal (completed/failed) tasks; older entries are
# pruned when a new task is created (M4 fix).
_MAX_TERMINAL_TASKS = 25

# Wall-clock budget for a hydrate-all job. The worker checks this between
# grades and marks remaining grades failed with "timed out" (M3-SEC fix).
HYDRATE_ALL_TIMEOUT_SECONDS = 30 * 60

# Strong references for asyncio background tasks so they are never garbage
# collected mid-execution (see asyncio.create_task documentation).
_background_tasks: set[asyncio.Task] = set()


def _sanitize_error(exc: Exception) -> str:
    """Return a safe, generic error string for task payloads.

    Raw ``str(exc)`` can leak DB credentials or connection internals to
    callers of the status endpoints; full details go to server logs only.
    """
    logger.exception("Admin task failure (details logged server-side)")
    return f"{type(exc).__name__}: operation failed (see server logs)"


def _prune_tasks() -> None:
    """Drop oldest terminal tasks so _tasks does not grow unboundedly."""
    terminal = [
        tid for tid, t in _tasks.items() if t.get("status") in ("completed", "failed")
    ]
    if len(terminal) <= _MAX_TERMINAL_TASKS:
        return
    terminal.sort(key=lambda tid: _tasks[tid].get("created_at", 0))
    for tid in terminal[: len(terminal) - _MAX_TERMINAL_TASKS]:
        _tasks.pop(tid, None)


def _verify_admin_key(
    x_admin_key: str | None = Header(None, alias="X-Admin-Key"),
) -> None:
    """Verify the admin API key header."""
    if not settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Admin API key not configured.",
        )
    # Constant-time comparison (M2-SEC fix) — avoids a timing side-channel
    # that could be used to guess the shared admin key byte by byte.
    if not x_admin_key or not hmac.compare_digest(x_admin_key, settings.admin_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin key.",
        )


class HydrateRequest(BaseModel):
    age: int = Field(..., ge=6, le=18, description="Target age group (6-18)")
    limit: int = Field(100, ge=1, le=500, description="Maximum books to fetch")


class HydrateAllRequest(BaseModel):
    start_grade: int = Field(
        1, ge=1, le=12, description="First grade to hydrate (1-12)"
    )
    end_grade: int = Field(12, ge=1, le=12, description="Last grade to hydrate (1-12)")
    books_per_grade: int = Field(
        100, ge=1, le=500, description="Maximum books per grade"
    )

    @model_validator(mode="after")
    def _validate_grade_range(self) -> "HydrateAllRequest":
        if self.end_grade < self.start_grade:
            raise ValueError("end_grade must be >= start_grade")
        return self


class GenerateQuestionsRequest(BaseModel):
    book_id: str = Field(..., description="UUID of the book")


class GenerateQuestionsAllRequest(BaseModel):
    max_books: int = Field(
        0, ge=0, le=2000, description="Max books to process (0 = all)"
    )


class GenerateQuestionsResponse(BaseModel):
    task_id: str
    status: str
    message: str


class GenerateQuestionsStatusResponse(BaseModel):
    task_id: str
    status: str
    books_processed: int = 0
    questions_generated: int = 0
    errors: list[str] = []


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


class GradeHydrationStatus(BaseModel):
    grade: int
    age: int
    status: str = "pending"  # 'pending', 'processing', 'completed', 'failed'
    books_processed: int = 0
    error: str | None = None


class HydrateAllStatusResponse(BaseModel):
    task_id: str
    status: str  # 'pending', 'processing', 'completed', 'failed'
    start_grade: int
    end_grade: int
    books_per_grade: int
    grades: list[GradeHydrationStatus]
    books_processed: int = 0
    questions_generated: int = 0
    errors: list[str] = []


@router.post(
    "/hydrate", response_model=HydrateResponse, status_code=status.HTTP_202_ACCEPTED
)
def trigger_hydration(
    request: HydrateRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_verify_admin_key),
):
    """Trigger a book data hydration job for a given age group."""
    task_id = str(uuid.uuid4())
    with _tasks_lock:
        _tasks[task_id] = {
            "task_id": task_id,
            "type": "hydrate",
            "status": "processing",
            "books_processed": 0,
            "questions_generated": 0,
            "errors": [],
            "created_at": time.time(),
        }

    logger.info("admin action: hydrate task_id=%s age=%s", task_id, request.age)

    # Run hydration synchronously for now (Celery integration is a separate task)
    try:
        service = HydrationService(db, openai_api_key=settings.openai_api_key)
        books = service.fetch_top_books_for_age(request.age, request.limit)
        with _tasks_lock:
            _tasks[task_id]["books_processed"] = len(books)
            _tasks[task_id]["status"] = "completed"
            _tasks[task_id]["finished_at"] = time.time()
    except Exception as e:
        with _tasks_lock:
            _tasks[task_id]["status"] = "failed"
            _tasks[task_id]["errors"].append(_sanitize_error(e))
            _tasks[task_id]["finished_at"] = time.time()

    with _tasks_lock:
        status_ = _tasks[task_id]["status"]
    return HydrateResponse(
        task_id=task_id,
        status=status_,
        message=f"Hydration job started for age {request.age}",
    )


@router.post(
    "/hydrate-all",
    response_model=HydrateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_hydrate_all(
    request: HydrateAllRequest,
    _: None = Depends(_verify_admin_key),
):
    """Trigger background hydration for a range of grades (1-12).

    Returns 202 immediately (R2 fix); the actual hydration runs in a worker
    thread via ``asyncio.to_thread`` so the HTTP connection is never held
    open for the full 30-60s job.
    """
    # Concurrency guard (S3): only one hydration task may run at a time.
    with _tasks_lock:
        if any(t.get("status") == "processing" for t in _tasks.values()):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A hydration task is already running.",
            )

        _prune_tasks()
        task_id = str(uuid.uuid4())
        _tasks[task_id] = {
            "task_id": task_id,
            "type": "hydrate_all",
            "status": "processing",
            "start_grade": request.start_grade,
            "end_grade": request.end_grade,
            "books_per_grade": request.books_per_grade,
            "grades": {
                str(grade): {
                    "grade": grade,
                    "age": GRADE_AGE_MAP[grade],
                    "status": "pending",
                    "books_processed": 0,
                    "error": None,
                }
                for grade in range(request.start_grade, request.end_grade + 1)
            },
            "books_processed": 0,
            "questions_generated": 0,
            "errors": [],
            "created_at": time.time(),
        }

    logger.info(
        "admin action: hydrate_all task_id=%s grades=%s-%s",
        task_id,
        request.start_grade,
        request.end_grade,
    )

    # The hydration pipeline (httpx + SQLAlchemy) is synchronous, so it is
    # offloaded to a worker thread. Not Celery: ADR-004 defers Celery to the
    # question-generation path, and this is a one-time data load. The worker
    # enforces its own wall-clock deadline (HYDRATE_ALL_TIMEOUT_SECONDS) so a
    # hung upstream API cannot leave the task stuck in "processing".
    background_task = asyncio.create_task(asyncio.to_thread(_run_hydrate_all, task_id))
    _background_tasks.add(background_task)
    background_task.add_done_callback(_background_tasks.discard)

    return HydrateResponse(
        task_id=task_id,
        status="processing",
        message=(
            f"Hydration job started for grades "
            f"{request.start_grade}-{request.end_grade}"
        ),
    )


def _run_hydrate_all(task_id: str) -> None:
    """Synchronous hydrate-all worker, executed in a worker thread.

    Uses a fresh DB session because the request-scoped session is closed as
    soon as the endpoint returns 202. Each grade is independent: a failure
    in one grade is recorded per-grade and does not stop the others.

    The whole body (including session creation) is guarded so any crash
    marks the task "failed" instead of leaving it stuck in "processing"
    and permanently blocking future hydrate-all calls with 409 (T2 fix).
    """
    deadline = time.monotonic() + HYDRATE_ALL_TIMEOUT_SECONDS
    db = None
    try:
        db = SessionLocal()
        with _tasks_lock:
            task = _tasks.get(task_id)
            if task is None:
                return

        service = HydrationService(db, openai_api_key=settings.openai_api_key)
        total = 0
        timed_out = False
        for grade in range(task["start_grade"], task["end_grade"] + 1):
            if time.monotonic() > deadline:
                # Mark every not-yet-started grade as failed and stop. The
                # thread is not killed (threads can't be force-stopped), but
                # the task is marked terminal so a new run may start (M3-SEC).
                timed_out = True
                with _tasks_lock:
                    for g in range(grade, task["end_grade"] + 1):
                        entry = task["grades"][str(g)]
                        if entry["status"] == "pending":
                            entry["status"] = "failed"
                            entry["error"] = "timed out"
                    task["errors"].append(
                        f"timed out after {HYDRATE_ALL_TIMEOUT_SECONDS}s"
                    )
                break

            with _tasks_lock:
                grade_entry = task["grades"][str(grade)]
                grade_entry["status"] = "processing"
            try:
                # commit=True gives per-grade atomicity: either the grade's
                # books all commit or none do (M4-SEC), so books_processed
                # is an exact count of stored books (M2 fix).
                books = service.fetch_top_books_for_age(
                    grade_entry["age"], task["books_per_grade"], commit=True
                )
                with _tasks_lock:
                    grade_entry["books_processed"] = len(books)
                    grade_entry["status"] = "completed"
                total += len(books)
            except Exception as e:
                logger.error(f"Hydration failed for grade {grade}: {e}")
                safe_error = _sanitize_error(e)
                with _tasks_lock:
                    grade_entry["status"] = "failed"
                    grade_entry["error"] = safe_error
                    task["errors"].append(f"grade {grade}: {safe_error}")
            with _tasks_lock:
                task["books_processed"] = total

        with _tasks_lock:
            # Per-grade errors are surfaced individually; the task fails
            # outright if every grade failed or the deadline was hit.
            if timed_out or (total == 0 and task["errors"]):
                task["status"] = "failed"
            else:
                task["status"] = "completed"
            task["finished_at"] = time.time()
    except Exception as e:
        # SessionLocal() or an unexpected crash — never leave the task stuck.
        logger.exception(f"Hydrate-all task {task_id} crashed")
        with _tasks_lock:
            task = _tasks.get(task_id)
            if task is not None:
                task["status"] = "failed"
                task["errors"].append(_sanitize_error(e))
                task["finished_at"] = time.time()
    finally:
        if db is not None:
            db.close()


@router.get("/hydrate/{task_id}/status", response_model=HydrateStatusResponse)
def get_hydration_status(
    task_id: str,
    response: Response,
    _: None = Depends(_verify_admin_key),
):
    """Get the status of a hydration job."""
    # Status is mutable and private — never cache it (H3 fix).
    response.headers["Cache-Control"] = "no-store"
    try:
        uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid task ID."
        )

    with _tasks_lock:
        task = _tasks.get(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found."
        )

    return HydrateStatusResponse(
        task_id=task["task_id"],
        status=task["status"],
        books_processed=task.get("books_processed", 0),
        questions_generated=task.get("questions_generated", 0),
        errors=task.get("errors", []),
    )


@router.get("/hydrate-all/{task_id}/status", response_model=HydrateAllStatusResponse)
def get_hydrate_all_status(
    task_id: str,
    response: Response,
    _: None = Depends(_verify_admin_key),
):
    """Get the per-grade status of a hydrate-all job."""
    # Status is mutable and private — never cache it (H3 fix).
    response.headers["Cache-Control"] = "no-store"
    try:
        uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid task ID."
        )

    with _tasks_lock:
        task = _tasks.get(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found."
        )

    # .get() defaults so this endpoint never KeyErrors on tasks created by
    # other endpoints (e.g. the sync /hydrate task, which has no grades).
    grades_data = task.get("grades", {})
    grades = [
        GradeHydrationStatus(
            grade=entry["grade"],
            age=entry["age"],
            status=entry["status"],
            books_processed=entry["books_processed"],
            error=entry["error"],
        )
        for entry in sorted(grades_data.values(), key=lambda g: g["grade"])
    ]
    return HydrateAllStatusResponse(
        task_id=task["task_id"],
        status=task.get("status", "processing"),
        start_grade=task.get("start_grade", 0),
        end_grade=task.get("end_grade", 0),
        books_per_grade=task.get("books_per_grade", 0),
        grades=grades,
        books_processed=task.get("books_processed", 0),
        questions_generated=task.get("questions_generated", 0),
        errors=task.get("errors", []),
    )


# ── Question Generation Endpoints ────────────────────────────────────────────


def _run_generate_questions(task_id: str, book_ids: list[str]) -> None:
    """Background worker: generate questions for a list of books."""
    db = None
    try:
        db = SessionLocal()
        service = HydrationService(db, openai_api_key=settings.openai_api_key)
        total_questions = 0
        errors: list[str] = []

        for i, book_id_str in enumerate(book_ids):
            try:
                bid = uuid.UUID(book_id_str)
                q_count = service.generate_questions_for_book(bid)
                total_questions += q_count
                with _tasks_lock:
                    _tasks[task_id]["books_processed"] = i + 1
                    _tasks[task_id]["questions_generated"] = total_questions
            except ValueError:
                errors.append(f"Invalid book ID: {book_id_str}")
            except Exception as e:
                errors.append(f"Book {book_id_str}: {_sanitize_error(e)}")
                logger.exception(f"Question generation failed for book {book_id_str}")

        with _tasks_lock:
            _tasks[task_id]["errors"] = errors
            _tasks[task_id]["status"] = "completed"
            _tasks[task_id]["finished_at"] = time.time()
    except Exception as e:
        # SessionLocal() or unexpected crash — never leave the task stuck.
        logger.exception(f"Question generation task {task_id} failed")
        with _tasks_lock:
            if task_id in _tasks:
                _tasks[task_id]["status"] = "failed"
                _tasks[task_id]["errors"] = [_sanitize_error(e)]
                _tasks[task_id]["finished_at"] = time.time()
    finally:
        if db is not None:
            db.close()


@router.post(
    "/generate-questions",
    response_model=GenerateQuestionsResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_question_generation(
    request: GenerateQuestionsRequest,
    _: None = Depends(_verify_admin_key),
):
    """Generate quiz questions for a single book."""
    try:
        uuid.UUID(request.book_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid book ID."
        )

    task_id = str(uuid.uuid4())
    with _tasks_lock:
        _prune_tasks()
        _tasks[task_id] = {
            "task_id": task_id,
            "type": "generate_questions",
            "status": "processing",
            "books_processed": 0,
            "questions_generated": 0,
            "errors": [],
            "created_at": time.time(),
        }

    logger.info(
        "admin action: generate_questions task_id=%s book_id=%s",
        task_id,
        request.book_id,
    )
    asyncio.create_task(
        asyncio.to_thread(_run_generate_questions, task_id, [request.book_id])
    )

    return GenerateQuestionsResponse(
        task_id=task_id, status="processing", message="Question generation started"
    )


@router.post(
    "/generate-questions-all",
    response_model=GenerateQuestionsResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_question_generation_all(
    request: GenerateQuestionsAllRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_verify_admin_key),
):
    """Generate quiz questions for all books that don't have any yet."""
    # Concurrency guard
    with _tasks_lock:
        for t in _tasks.values():
            if t.get("status") == "processing" and t.get("type") in (
                "generate_questions",
                "generate_questions_all",
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A question generation job is already running.",
                )

    from app.models.question import Question

    all_book_ids = [row[0] for row in db.query(Book.id).all()]
    books_with_q = {row[0] for row in db.query(Question.book_id).distinct().all()}
    pending = [str(bid) for bid in all_book_ids if bid not in books_with_q]

    if request.max_books > 0:
        pending = pending[: request.max_books]

    if not pending:
        return GenerateQuestionsResponse(
            task_id="none",
            status="completed",
            message="All books already have questions.",
        )

    task_id = str(uuid.uuid4())
    with _tasks_lock:
        _prune_tasks()
        _tasks[task_id] = {
            "task_id": task_id,
            "type": "generate_questions_all",
            "status": "processing",
            "books_processed": 0,
            "questions_generated": 0,
            "total_books": len(pending),
            "errors": [],
            "created_at": time.time(),
        }

    logger.info(
        "admin action: generate_questions_all task_id=%s books=%d",
        task_id,
        len(pending),
    )
    asyncio.create_task(asyncio.to_thread(_run_generate_questions, task_id, pending))

    return GenerateQuestionsResponse(
        task_id=task_id,
        status="processing",
        message=f"Question generation started for {len(pending)} books",
    )


@router.get(
    "/generate-questions/{task_id}/status",
    response_model=GenerateQuestionsStatusResponse,
)
def get_generate_questions_status(
    task_id: str,
    response: Response,
    _: None = Depends(_verify_admin_key),
):
    """Get the status of a question generation job."""
    # Status is mutable and private — never cache it (H3 fix).
    response.headers["Cache-Control"] = "no-store"
    try:
        uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid task ID."
        )

    with _tasks_lock:
        task = _tasks.get(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found."
        )

    return GenerateQuestionsStatusResponse(
        task_id=task["task_id"],
        status=task["status"],
        books_processed=task.get("books_processed", 0),
        questions_generated=task.get("questions_generated", 0),
        errors=task.get("errors", []),
    )
