"""
Backfill all legacy quiz documents with missing backwards-compatibility fields.

Applies the same fixup logic as update_quiz_for_backwards_compatibility() in
quizzes.py: adds max_questions_allowed_to_attempt, title, and marking_scheme
to question sets that are missing them.

Run this script once against production MongoDB before deploying the
cache-aware application code so the runtime fixup becomes a no-op.

Usage:
    python backfill_quiz_backwards_compatibility.py              # apply changes
    python backfill_quiz_backwards_compatibility.py --dry-run    # report only
"""

import argparse
import os

from pymongo import MongoClient


def needs_fixup(quiz):
    """Return True if any question set in the quiz needs backwards-compat fixup."""
    for question_set in quiz.get("question_sets", []):
        if "max_questions_allowed_to_attempt" not in question_set:
            return True
        if (
            "marking_scheme" not in question_set
            or question_set["marking_scheme"] is None
        ):
            return True
    return False


def apply_fixup(quiz):
    """Apply backwards-compatibility fixup to quiz in-place.

    Mirrors the exact logic of update_quiz_for_backwards_compatibility()
    in app/routers/quizzes.py.
    """
    for question_set in quiz["question_sets"]:
        if "max_questions_allowed_to_attempt" not in question_set:
            question_set["max_questions_allowed_to_attempt"] = len(
                question_set["questions"]
            )
            question_set["title"] = "Section A"

        if (
            "marking_scheme" not in question_set
            or question_set["marking_scheme"] is None
        ):
            question_marking_scheme = question_set["questions"][0]["marking_scheme"]
            if question_marking_scheme is not None:
                question_set["marking_scheme"] = question_marking_scheme
            else:
                question_set["marking_scheme"] = {
                    "correct": 1,
                    "wrong": 0,
                    "skipped": 0,
                }


def main():
    parser = argparse.ArgumentParser(
        description="Backfill quiz documents with missing backwards-compatibility fields."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing to the database.",
    )
    args = parser.parse_args()

    if "MONGO_AUTH_CREDENTIALS" not in os.environ:
        from dotenv import load_dotenv

        load_dotenv("../.env")

    credentials = os.getenv("MONGO_AUTH_CREDENTIALS")
    if not credentials:
        print("ERROR: MONGO_AUTH_CREDENTIALS not set")
        return

    db_name = os.getenv("MONGO_DB_NAME", "quiz")
    client = MongoClient(credentials)
    db = client[db_name]

    total = 0
    updated = 0
    already_compatible = 0
    errors = 0

    for quiz in db.quizzes.find():
        total += 1
        quiz_id = quiz["_id"]

        if not needs_fixup(quiz):
            already_compatible += 1
            continue

        if args.dry_run:
            print(f"  [dry-run] would update quiz {quiz_id}")
            updated += 1
            continue

        apply_fixup(quiz)
        try:
            result = db.quizzes.update_one({"_id": quiz_id}, {"$set": quiz})
            if result.acknowledged:
                updated += 1
                print(f"  updated quiz {quiz_id}")
            else:
                errors += 1
                print(f"  ERROR: update not acknowledged for quiz {quiz_id}")
        except Exception as e:
            errors += 1
            print(f"  ERROR: failed to update quiz {quiz_id}: {e}")

    prefix = "[DRY RUN] " if args.dry_run else ""
    print(
        f"\n{prefix}Done. total={total} updated={updated} already_compatible={already_compatible} errors={errors}"
    )

    client.close()


if __name__ == "__main__":
    main()
