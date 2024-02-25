from pymongo import UpdateOne
from bson import ObjectId
from database import client
from cache import cache_data, get_cached_data, get_keys, invalidate_cache

# Redis key prefix and lock key
KEY_PREFIX_INSERT = 'session_id_to_insert_'
KEY_PREFIX_UPDATE = 'session_id_to_update_'
WRITE_BACK_LOCK_KEY = 'write_back_lock'
PREVIOUS_TWO_SESSION_IDS_KEY = 'previous_two_session_ids_'

def perform_write_back_to_db():
    # import ipdb; ipdb.set_trace()
    # Set the write back lock key in Redis
    cache_data(WRITE_BACK_LOCK_KEY, '1', 60 * 60)

    # Find all keys in Redis for insertion
    session_ids_to_insert = []
    insert_keys = get_keys(f'{KEY_PREFIX_INSERT}*')
    insert_operations = []
    for key in insert_keys:
        session_id = key.split('_')[-1]
        session_data = get_cached_data(f"session_{session_id}")
        if session_data:
            session_ids_to_insert.append(session_id)
            insert_operations.append(session_data)

    # Bulk insert into MongoDB
    try:
        if len(insert_operations) > 0:
            inserted_result = client.quiz.sessions.insert_many(insert_operations)
            if len(inserted_result.inserted_ids) != len(insert_operations):
                raise Exception("Some sessions were not inserted")
            else:
                for session_id in inserted_result.inserted_ids:
                    invalidate_cache(f"{KEY_PREFIX_INSERT}{session_id}")
                    invalidate_cache(f"session_{session_id}")

    except Exception as e:
        print(f"Error while inserting: {e}")
        invalidate_cache(WRITE_BACK_LOCK_KEY)
        return

    # Find all keys in Redis for update
    session_ids_to_update = []
    update_keys = get_keys(f'{KEY_PREFIX_UPDATE}*')
    update_operations = []
    for key in update_keys:
        session_id = key.split('_')[-1]
        session_data = get_cached_data(f"session_{session_id}")
        if session_data:
            session_ids_to_update.append(session_id)
            update_operations.append(UpdateOne({'_id': f"{session_id}"}, {'$set': session_data}, upsert=True))

    # Bulk update in MongoDB
    try:
        if update_operations:
            update_result = client.quiz.sessions.bulk_write(update_operations)
            if update_result.modified_count != len(update_operations):
                raise Exception("Some sessions were not updated")
            else:
                for session_id in session_ids_to_update:
                    invalidate_cache(f"{KEY_PREFIX_UPDATE}{session_id}")
                    invalidate_cache(f"session_{session_id}")
    except Exception as e:
        print(f"Error while updating: {e}")
        invalidate_cache(WRITE_BACK_LOCK_KEY)
        return

    previous_two_session_keys = get_keys(f'{PREVIOUS_TWO_SESSION_IDS_KEY}*')
    for key in previous_two_session_keys:
        invalidate_cache(key)

    # Release the write back lock key in Redis
    invalidate_cache(WRITE_BACK_LOCK_KEY)


if __name__ == '__main__':
    perform_write_back_to_db()