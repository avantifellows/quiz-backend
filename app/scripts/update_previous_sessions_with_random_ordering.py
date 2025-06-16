from pymongo import MongoClient, UpdateOne
import os
from dotenv import load_dotenv


def get_db_client():
    """Connect to MongoDB and return the client"""
    if "MONGO_AUTH_CREDENTIALS" not in os.environ:
        load_dotenv("../../.env")  # Adjust path if needed

    client = MongoClient(os.getenv("MONGO_AUTH_CREDENTIALS"))
    return client


# Function to update the question_order in sessions
def update_question_order_in_sessions():
    """Update question_order in all sessions where needed"""
    client = get_db_client()
    db_name = "quiz"
    db = client[db_name]

    # Get all quizzes
    # quizzes = db.quizzes.find({})
    quiz_count = 0
    total_sessions_updated = 0

    quiz_ids = []
    for quiz_id in quiz_ids:
        quiz_count += 1
        quiz = db.quizzes.find_one({"_id": quiz_id})
        quiz_id = quiz["_id"]

        print(f"Processing quiz {quiz_count}: {quiz_id}")

        # Calculate question_order for this quiz
        question_sets = quiz.get("question_sets", [])
        total_questions = sum(
            len(question_set.get("questions", [])) for question_set in question_sets
        )
        question_order = list(range(0, total_questions))

        # Find all sessions for this quiz that don't have question_order
        sessions_for_quiz = db.sessions.find(
            {
                "quiz_id": quiz_id,
                "$or": [{"question_order": {"$exists": False}}, {"question_order": []}],
            }
        )

        operations = []
        for session in sessions_for_quiz:
            operations.append(
                UpdateOne(
                    {"_id": session["_id"]},
                    {"$set": {"question_order": question_order}},
                )
            )

        print(operations)

        # Update all sessions for this quiz
        if operations:
            result = db.sessions.bulk_write(operations)
            print(f"  Updated {result.modified_count} sessions for this quiz")
            total_sessions_updated += result.modified_count
        else:
            print("  No sessions to update for this quiz")

    print(
        f"Total: Updated {total_sessions_updated} sessions across {quiz_count} quizzes"
    )

    client.close()


if __name__ == "__main__":
    update_question_order_in_sessions()
