"""Hydrate quiz questions for all books using DeepSeek AI."""
import sys
import time
from app.core.database import SessionLocal
from app.models.book import Book
from app.models.question import Question
from app.core.config import get_settings
from app.services.hydration_service import HydrationService

db = SessionLocal()

# Find books without questions
all_ids = [row[0] for row in db.query(Book.id).all()]
existing = {row[0] for row in db.query(Question.book_id).distinct().all()}
pending = [bid for bid in all_ids if bid not in existing]

print(f"Books: {len(all_ids)} total, {len(existing)} with questions, {len(pending)} pending")
print(f"Model: {get_settings().openai_model} @ {get_settings().openai_base_url}")
print()

if not pending:
    print("All books already have questions!")
    db.close()
    sys.exit(0)

svc = HydrationService(db, openai_api_key=get_settings().openai_api_key)
start = time.time()
total_qs = 0

for i, bid in enumerate(pending):
    try:
        book = db.query(Book).filter(Book.id == bid).first()
        title = book.title if book else "unknown"
        q_count = svc.generate_questions_for_book(bid)
        total_qs += q_count
        elapsed = time.time() - start
        rate = (i + 1) / elapsed * 60 if elapsed > 0 else 0
        remaining = len(pending) - (i + 1)
        eta_min = remaining / rate if rate > 0 else 0
        print(f"[{i+1}/{len(pending)}] {q_count}qs — '{title[:50]}' | {rate:.1f}/min | ETA {eta_min:.0f}min")
    except Exception as e:
        print(f"[{i+1}/{len(pending)}] ERROR on {bid}: {e}")

elapsed = time.time() - start
print(f"\n✅ Done: {len(pending)} books, {total_qs} questions in {elapsed/60:.1f} minutes")
db.close()
