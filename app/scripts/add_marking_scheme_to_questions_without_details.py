from pymongo import MongoClient
import os
from settings import Settings

settings = Settings()

if __name__ == "__main__":
    if "MONGO_AUTH_CREDENTIALS" not in os.environ:
        from dotenv import load_dotenv

        load_dotenv("../.env")
    # import ipdb; ipdb.set_trace()
    client = MongoClient(os.getenv("MONGO_AUTH_CREDENTIALS"))

    done_ids = []
    for quiz_index, quiz in enumerate(client.quiz.quizzes.find()):
        quiz_id = quiz["_id"]
        for question_set_index, question_set in enumerate(quiz["question_sets"]):
            question_set_id = question_set["_id"]
            subset_with_details = client.quiz.questions.aggregate(
                [
                    {"$match": {"question_set_id": question_set_id}},
                    {"$sort": {"_id": 1}},
                    {"$limit": settings.subset_size},
                ]
            )

            subset_without_details = client.quiz.questions.aggregate(
                [
                    {"$match": {"question_set_id": question_set_id}},
                    {"$sort": {"_id": 1}},
                    {"$skip": settings.subset_size},
                    {
                        "$project": {
                            "graded": 1,
                            "type": 1,
                            "correct_answer": 1,
                            "question_set_id": 1,
                            "marking_scheme": 1,
                        }
                    },
                ]
            )
            aggregated_questions = list(subset_with_details) + list(
                subset_without_details
            )

            quiz["question_sets"][question_set_index][
                "questions"
            ] = aggregated_questions

        client.quiz.quizzes.update_one({"_id": quiz_id}, {"$set": quiz})
        done_ids.append(quiz_id)
        print(f"{quiz_id} done")

    print(done_ids)
    print(len(done_ids))
