from pymongo import MongoClient
import os

# test session["_id"] in prod: 633646b0639829dad5a896b4

if __name__ == "__main__":
    if "MONGO_AUTH_CREDENTIALS" not in os.environ:
        from dotenv import load_dotenv

        load_dotenv("../.env.local")
    client = MongoClient(os.getenv("MONGO_AUTH_CREDENTIALS"))
    session_collection = client.quiz.sessions

    # Iterate through all documents with an 'events' key
    for session in session_collection.find(
        {"events": {"$exists": True}, "$expr": {"$gt": [{"$size": "$events"}, 1000]}}
    ):
        print(session["_id"])

        if session["events"] is None:
            continue

        # Initialize variables for squashing dummy event
        squashed_dummy_event = None

        updated_session_events = []

        # Loop through all events in the session
        for event in session["events"]:
            # Check if the event is a dummy event
            if event["event_type"] == "dummy-event":
                # Check if we've already seen a dummy event
                if squashed_dummy_event is None:
                    # Set the squashed_dummy_event to the first dummy event
                    squashed_dummy_event = event
                else:
                    # If this is not the first dummy event, update the updated_at time of the previous event
                    squashed_dummy_event["updated_at"] = event["created_at"]
            else:
                # If the current event is not a dummy event, check if there was a squashed_dummy_event
                if squashed_dummy_event is not None:
                    print("reached!!")
                    updated_session_events.append(squashed_dummy_event)
                    squashed_dummy_event = None
                # Add an 'updated_at' key to the current event if it doesn't already exist
                # useful for start_quiz, end_quiz, resume_quiz events

                if "updated_at" not in event:
                    event["updated_at"] = event["created_at"]
                    updated_session_events.append(event)

        # Check if there was a squashed_dummy_event left over at the end
        if squashed_dummy_event is not None:
            if "updated_at" not in squashed_dummy_event:
                squashed_dummy_event["updated_at"] = squashed_dummy_event["created_at"]
            updated_session_events.append(squashed_dummy_event)

        print([ev["event_type"] for ev in session["events"]])
        print("****")
        print([ev for ev in updated_session_events])

        print("*******")
        break

        # Update the session in the database with the modified events list
        # session_collection.update_one({"_id": session["_id"]}, {"$set": {"events": updated_session_events}})
