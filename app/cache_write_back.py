from pymongo import UpdateOne
from bson import ObjectId
from database import client
from cache import cache_data, get_cached_data, get_keys, invalidate_cache

# Redis key prefix and lock key
KEY_PREFIX_INSERT = 'session_id_to_insert_'
KEY_PREFIX_UPDATE = 'session_id_to_update_'
WRITE_BACK_LOCK_KEY = 'write_back_lock'

def perform_write_back_to_db():
    # import ipdb; ipdb.set_trace()
    # Set the write back lock key in Redis
    cache_data(WRITE_BACK_LOCK_KEY, '1', 60)

    # Find all keys in Redis for insertion
    insert_keys = get_keys(f'{KEY_PREFIX_INSERT}*')
    insert_operations = []
    for key in insert_keys:
        session_id = key.split('_')[-1]
        session_data = get_cached_data(f"session_{session_id}")
        if session_data:
            insert_operations.append(session_data)

    # Bulk insert into MongoDB
    if insert_operations:
        client.quiz.sessions.insert_many(insert_operations)

    # Find all keys in Redis for update
    # update_keys = r.keys(f'{KEY_PREFIX_UPDATE}*')
    update_keys = get_keys(f'{KEY_PREFIX_UPDATE}*')
    update_operations = []
    for key in update_keys:
        session_id = key.split('_')[-1]
        session_data = get_cached_data(f"session_{session_id}")
        if session_data:
            update_operations.append(UpdateOne({'_id': f"{session_id}"}, {'$set': session_data}))

    # Bulk update in MongoDB
    if update_operations:
        client.quiz.sessions.bulk_write(update_operations)

    # Release the write back lock key in Redis
    # r.delete(WRITE_BACK_LOCK_KEY)
    invalidate_cache(WRITE_BACK_LOCK_KEY)

if __name__ == '__main__':
    perform_write_back_to_db()