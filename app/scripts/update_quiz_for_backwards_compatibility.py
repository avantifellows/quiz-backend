from pymongo import MongoClient
import os
"""
#     if given quiz contains question sets that do not have max_questions_allowed_to_attempt key,
#     update the question sets (in-place) with the key and value as len(questions) in that set.
#     Additionally, add a default title and marking scheme for the set.
#     Finally, add quiz to quiz_collection
#     (NOTE: this is a primitive form of versioning)
#     """

if __name__ == "__main__":
  if "MONGO_AUTH_CREDENTIALS" not in os.environ:
        from dotenv import load_dotenv

        load_dotenv("../.env")
  # import ipdb; ipdb.set_trace()
  client = MongoClient(os.getenv("MONGO_AUTH_CREDENTIALS"))

  done_ids = []
  for quiz_index, quiz in enumerate(client.quiz.quizzes.find()):
      quiz_id = quiz["_id"]
      print(quiz_id)
      is_backwards_compatibile = True

      for question_set_index, question_set in enumerate(quiz["question_sets"]):
        if "max_questions_allowed_to_attempt" not in question_set:
          is_backwards_compatibile = False
          question_set["max_questions_allowed_to_attempt"] = len(
              question_set["questions"]
          )
          question_set["title"] = "Section A"

        if (
            "marking_scheme" not in question_set
            or question_set["marking_scheme"] is None
        ):
            is_backwards_compatibile = False
            question_marking_scheme = None

            if (
               "questions" in question_set and 
               len(question_set["questions"]) > 0 and
               "marking_scheme" in question_set["questions"][0]
            ): question_marking_scheme = question_set["questions"][0]["marking_scheme"] 


            if question_marking_scheme is not None:
                question_set["marking_scheme"] = question_marking_scheme
            else:
                question_set["marking_scheme"] = {
                    "correct": 1,
                    "wrong": 0,
                    "skipped": 0,
                }  # default
      if not is_backwards_compatibile:
        # client.quiz.quizzes.update_one({"_id": quiz_id}, {"$set": quiz})
        done_ids.append(quiz_id)
        print(f"{quiz_id} done")

  print(done_ids)
  print(len(done_ids))