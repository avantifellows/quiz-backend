from pymongo import MongoClient
import os
from dotenv import load_dotenv


def get_db_client():
    """Connect to MongoDB and return the client"""
    if "MONGO_AUTH_CREDENTIALS" not in os.environ:
        load_dotenv("../.env")  # Adjust path if needed

    client = MongoClient(os.getenv("MONGO_AUTH_CREDENTIALS"))
    return client


# Function to update the question_order in sessions
def update_question_order_in_sessions():
    """Update question_order in all sessions where needed"""
    client = get_db_client()

    db_name = "quiz"
    db = client[db_name]

    # Get all sessions that don't have question_order field
    sessions_to_update = db.sessions.find({"question_order": {"$exists": False}})

    update_count = 0
    for session in sessions_to_update:
        # Get quiz ID for the  respective session
        quiz_id = session.get("quiz_id")
        if not quiz_id:
            continue

        # Find the quiz document
        quiz = db.quizzes.find_one({"_id": quiz_id})
        if not quiz:
            continue

        # Get question sets from the quiz to calculate the totalt questions count
        question_sets = quiz.get("question_sets", [])

        # Calculate total number of questions across all sets
        total_questions = sum(
            len(question_set.get("questions", [])) for question_set in question_sets
        )

        # Create question_order array [0,1, 2, ..., total_questions-1]
        question_order = list(range(0, total_questions))

        # Update the session with the new question_order
        result = db.sessions.update_one(
            {"_id": session["_id"]}, {"$set": {"question_order": question_order}}
        )

        if result.modified_count:
            update_count += 1

    print(f"Updated question_order for {update_count} sessions")
    client.close()


if __name__ == "__main__":
    update_question_order_in_sessions()
