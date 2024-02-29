from pymongo import UpdateOne
from bson import ObjectId
from database import client
from cache.cache import cache_data, get_cached_data, get_keys, invalidate_cache
import time

# Redis key prefix and lock key
KEY_PREFIX_INSERT = "session_id_to_insert_"
KEY_PREFIX_UPDATE = "session_id_to_update_"
WRITE_BACK_LOCK_KEY = "write_back_lock"
PREVIOUS_TWO_SESSION_IDS_KEY = "previous_two_session_ids_"


def perform_write_back_to_db():
    # import ipdb; ipdb.set_trace()
    print("Checking if lock key is already set")
    # Check if the write back lock key is already set in Redis
    if get_cached_data(WRITE_BACK_LOCK_KEY):
        print("Lock key already set, returning")
        return
    t0 = time.time()
    print("Performing write back to DB")
    # Set the write back lock key in Redis
    cache_data(WRITE_BACK_LOCK_KEY, "1", 60 * 60)
    print("Lock key set")

    # Find all keys in Redis for insertion
    session_ids_to_insert = []
    insert_keys = get_keys(f"{KEY_PREFIX_INSERT}*")
    print("Length of insert keys", len(insert_keys))
    insert_operations = []
    for key in insert_keys:
        session_id = key.split("_")[-1]
        session_data = get_cached_data(f"session_{session_id}")
        if session_data:
            session_ids_to_insert.append(session_id)
            insert_operations.append(session_data)

    # Bulk insert into MongoDB
    try:
        if len(insert_operations) > 0:
            print(f"Inserting {len(insert_operations)} sessions into MongoDB")
            inserted_result = client.quiz.sessions.insert_many(insert_operations)
            print(f"Inserted_result", {inserted_result})
            if len(inserted_result.inserted_ids) != len(insert_operations):
                raise Exception("Some sessions were not inserted")
            else:
                for session_id in inserted_result.inserted_ids:
                    invalidate_cache(f"{KEY_PREFIX_INSERT}{session_id}")
                    invalidate_cache(f"session_{session_id}")
                print("Insertion successful, cache invalidated for inserted sessions")
    except Exception as e:
        print(f"Error while inserting: {e}")
        invalidate_cache(WRITE_BACK_LOCK_KEY)
        print("Lock key released")
        return

    # Find all keys in Redis for update
    session_ids_to_update = []
    update_keys = get_keys(f"{KEY_PREFIX_UPDATE}*")
    print("Length of update keys", len(update_keys))
    update_operations = []
    for key in update_keys:
        session_id = key.split("_")[-1]
        session_data = get_cached_data(f"session_{session_id}")
        if session_data:
            session_ids_to_update.append(session_id)
            update_operations.append(
                UpdateOne({"_id": f"{session_id}"}, {"$set": session_data}, upsert=True)
            )

    # Bulk update in MongoDB
    try:
        if update_operations:
            print(f"Updating {len(update_operations)} sessions in MongoDB")
            update_result = client.quiz.sessions.bulk_write(update_operations)
            print(f"Update_result", {update_result})
            if update_result.modified_count != len(update_operations):
                raise Exception("Some sessions were not updated")
            else:
                for session_id in session_ids_to_update:
                    invalidate_cache(f"{KEY_PREFIX_UPDATE}{session_id}")
                    invalidate_cache(f"session_{session_id}")
                print("Update successful, cache invalidated for updated sessions")
    except Exception as e:
        print(f"Error while updating: {e}")
        invalidate_cache(WRITE_BACK_LOCK_KEY)
        print("Lock key released")
        return

    previous_two_session_keys = get_keys(f"{PREVIOUS_TWO_SESSION_IDS_KEY}*")
    print("Length of previous two session keys", len(previous_two_session_keys))
    for key in previous_two_session_keys:
        invalidate_cache(key)
    print("Cache invalidated for previous two session keys")

    # Release the write back lock key in Redis
    invalidate_cache(WRITE_BACK_LOCK_KEY)
    print("Lock key released")

    print("Write back to DB completed")
    print("Time taken", time.time() - t0)


if __name__ == "__main__":
    perform_write_back_to_db()
