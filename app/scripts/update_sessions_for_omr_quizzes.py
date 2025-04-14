from pymongo import MongoClient
import os

if __name__ == "__main__":
    if "MONGO_AUTH_CREDENTIALS" not in os.environ:
        from dotenv import load_dotenv

        load_dotenv("../../.env")

    # Connect to MongoDB
    client = MongoClient(os.getenv("MONGO_AUTH_CREDENTIALS"))

    # Collections
    quiz_collection = client.quiz.quizzes
    session_collection = client.quiz.sessions

    # Find all quiz IDs where metadata.quiz_type is "omr-assessment"
    omr_assessment_quizzes = quiz_collection.find(
        {"metadata.quiz_type": "omr-assessment"}, {"_id": 1}
    )

    # Extract quiz IDs from the query result
    omr_quiz_ids = [quiz["_id"] for quiz in omr_assessment_quizzes]
    print(f"Found {len(omr_quiz_ids)} quizzes with 'omr-assessment' type.")

    session_count = session_collection.count_documents(
        {"quiz_id": {"$in": omr_quiz_ids}}
    )

    print(f"Found {session_count} sessions that need to be updated.")

    # Update all sessions with these quiz_ids, setting omr_mode to true
    result = session_collection.update_many(
        {"quiz_id": {"$in": omr_quiz_ids}}, {"$set": {"omr_mode": True}}
    )

    print(f"Updated {result.modified_count} sessions to set 'omr_mode' to True.")
