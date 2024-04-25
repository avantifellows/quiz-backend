from pymongo import MongoClient
import os
import json

if __name__ == "__main__":
    if "MONGO_AUTH_CREDENTIALS" not in os.environ:
        from dotenv import load_dotenv

        load_dotenv("../../.env")
    client = MongoClient(os.getenv("MONGO_AUTH_CREDENTIALS"))
    session_collection = client.quiz.sessions
    # create a key value pair array
    # each element of the array will be a dict.
    #  The dict will have two keys. one is the old user id that we're looking for in the sessions collection
    #  and another key will be the new user_id that we want to replace with
    key_value_pair_arr = []

    # read the mapping json file
    mapping_data = {}
    with open("mapping.json", "r") as f:
        mapping_data = json.load(f)

    for key, value in mapping_data.items():
        key_value_pair_arr.append({"old_user_id": key, "new_user_id": value})

    list_of_old_user_ids = list(map((lambda x: x["old_user_id"]), key_value_pair_arr))
    response = session_collection.update_many(
        {"user_id": {"$in": list_of_old_user_ids}},
        [
            {
                "$set": {
                    "user_id": {
                        "$let": {
                            "vars": {
                                "obj": {
                                    "$arrayElemAt": [
                                        {
                                            "$filter": {
                                                "input": key_value_pair_arr,
                                                "as": "kvpa",
                                                "cond": {
                                                    "$eq": [
                                                        "$$kvpa.old_user_id",
                                                        "$user_id",
                                                    ]
                                                },
                                            }
                                        },
                                        0,
                                    ]
                                }
                            },
                            "in": "$$obj.new_user_id",
                        }
                    }
                }
            }
        ],
    )
    print(response)
    print(response.acknowledged)
    print(response.matched_count)
    print(response.modified_count)
    print(response.upserted_id)
