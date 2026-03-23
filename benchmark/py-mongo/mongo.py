import concurrent.futures
import time

import pymongo

MONGO_URI = "mongodb://localhost:27017/"
THREADS = 50
OPS_PER_THREAD = 2000
DB_NAME = "stress_db"
COLLECTION_NAME = "mongo_benchmark"
MAX_POOL_SIZE = 100

client = pymongo.MongoClient(MONGO_URI, maxPoolSize=MAX_POOL_SIZE)
collection = client[DB_NAME][COLLECTION_NAME]


def ensure_benchmark_index():
    collection.create_index([("worker", pymongo.ASCENDING), ("iteration", pymongo.ASCENDING)])


def hammer_db(thread_id):
    insert_attempts = 0
    insert_successes = 0
    insert_failures = 0
    find_attempts = 0
    find_successes = 0
    find_failures = 0

    for i in range(OPS_PER_THREAD):
        doc = {"worker": thread_id, "iteration": i}
        filter_doc = {"worker": thread_id, "iteration": i}

        insert_attempts += 1
        try:
            collection.insert_one(doc)
            insert_successes += 1
        except pymongo.errors.PyMongoError as err:
            insert_failures += 1
            print(f"Insert failed on worker {thread_id} iteration {i}: {err}")
            continue

        find_attempts += 1
        try:
            result = collection.find_one(filter_doc)
            if result is None:
                find_failures += 1
                print(f"Find failed on worker {thread_id} iteration {i}: no document returned")
            else:
                find_successes += 1
        except pymongo.errors.PyMongoError as err:
            find_failures += 1
            print(f"Find failed on worker {thread_id} iteration {i}: {err}")

    return {
        "insert_attempts": insert_attempts,
        "insert_successes": insert_successes,
        "insert_failures": insert_failures,
        "find_attempts": find_attempts,
        "find_successes": find_successes,
        "find_failures": find_failures,
    }


def print_total_record_inserted():
    total_record = collection.count_documents({})
    print(f"Total records inserted successfully: {total_record}")


collection.drop()
ensure_benchmark_index()

print("Initiating stress test...")
start_time = time.time()

summary = {
    "insert_attempts": 0,
    "insert_successes": 0,
    "insert_failures": 0,
    "find_attempts": 0,
    "find_successes": 0,
    "find_failures": 0,
}

with concurrent.futures.ThreadPoolExecutor(max_workers=THREADS) as executor:
    futures = [executor.submit(hammer_db, i) for i in range(THREADS)]
    for future in concurrent.futures.as_completed(futures):
        worker_summary = future.result()
        for key, value in worker_summary.items():
            summary[key] += value

duration = time.time() - start_time
successful_operations = summary["insert_successes"] + summary["find_successes"]
attempted_operations = summary["insert_attempts"] + summary["find_attempts"]

print(f"Test complete: {duration:.2f} seconds.")
print(f"Successful throughput: {successful_operations / duration:.2f} QPS.")
print(f"Attempted throughput: {attempted_operations / duration:.2f} QPS.")
print(f"Insert attempts: {summary['insert_attempts']}")
print(f"Insert successes: {summary['insert_successes']}")
print(f"Insert failures: {summary['insert_failures']}")
print(f"Find attempts: {summary['find_attempts']}")
print(f"Find successes: {summary['find_successes']}")
print(f"Find failures: {summary['find_failures']}")
print_total_record_inserted()
