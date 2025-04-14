from pymongo import MongoClient
import os

if __name__ == "__main__":
    if "MONGO_AUTH_CREDENTIALS" not in os.environ:
        from dotenv import load_dotenv

        load_dotenv("../.env")
    # import ipdb; ipdb.set_trace()
    client = MongoClient(os.getenv("MONGO_AUTH_CREDENTIALS"))
    quiz_collection = client.quiz.quizzes
    done_ids = []

    for quiz_index, quiz in enumerate(quiz_collection.find()):
        quiz_id = quiz["_id"]
        for question_set_index, question_set in enumerate(quiz["question_sets"]):
            question_set_id = question_set["_id"]
            for question_index, question in enumerate(question_set["questions"]):
                if (
                    "question_set_id" in question
                    and question["question_set_id"] is not None
                    and question["question_set_id"] == question_set_id
                ):
                    continue
                question["question_set_id"] = question_set_id

        quiz_collection.update_one({"_id": quiz_id}, {"$set": quiz})
        done_ids.append(quiz_id)
        print(f"{quiz_id} done")

    print(done_ids)
    print(len(done_ids))
