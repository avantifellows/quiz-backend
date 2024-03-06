from pymongo import MongoClient
import os

if __name__ == "__main__":
    if "MONGO_AUTH_CREDENTIALS" not in os.environ:
        from dotenv import load_dotenv

        load_dotenv("../../.env")
    client = MongoClient(os.getenv("MONGO_AUTH_CREDENTIALS"))
    quiz_collection = client.quiz.quizzes
    question_collection = client.quiz.questions

    changed_questions = []
    changed_quizzes = set()

    # search in the quiz collection, and in each quiz and each question set, find a the question
    # which are the respective text you're looking to replace
    # then update the question inside the quiz and separately in the questions collection as well
    for quiz_index, quiz in enumerate(quiz_collection.find()):
        quiz_id = quiz["_id"]
        does_quiz_need_to_change = False
        for question_set_index, question_set in enumerate(quiz["question_sets"]):
            question_set_id = question_set["_id"]
            for question_index, question in enumerate(question_set["questions"]):
                if "text" in question and "\u20d7" in question["text"]:
                    does_quiz_need_to_change = True
                    changed_questions.append(question["_id"])
                    changed_quizzes.add(quiz_id)
                    question["text"] = question["text"].replace("\u20d7", "\\vec.")

                    # update the question also inside question collection
                    question_collection.update_one(
                        {"_id": question["_id"]}, {"$set": {"text": question["text"]}}
                    )

        if does_quiz_need_to_change:
            print("quiz needs to be updated")
            quiz_collection.update_one({"_id": quiz_id}, {"$set": quiz})

    # search in the questions collection
    # we need to because the new subset pattern will cause not all questions ka text to exist in the QUIZZES collection
    # so we need to check the QUESTIONS collection as well
    for question_index, question in enumerate(question_collection.find()):
        if "text" in question and "\u20d7" in question["text"]:
            question["text"] = question["text"].replace("\u20d7", "\\vec.")
            # update the question also inside question collection
            question_collection.update_one(
                {"_id": question["_id"]}, {"$set": {"text": question["text"]}}
            )

    print("DONE!")
    print(len(changed_questions))
    print(changed_questions)

    print(len(changed_quizzes))
    print(changed_quizzes)
