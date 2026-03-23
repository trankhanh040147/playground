import pymongo
import concurrent.futures
import time

MONGO_URI = "mongodb://localhost:27017/"
THREADS = 50
OPS_PER_THREAD = 2000

client = pymongo.MongoClient(MONGO_URI)
collection = client["stress_db"]["test_data"]


def hammer_db(thread_id):
    for i in range(OPS_PER_THREAD):
        # Swap this out for your actual application queries
        collection.insert_one({"thread": thread_id, "iteration": i})
        collection.find_one({"thread": thread_id})


def printTotalRecordInserted():
    total_record = collection.count_documents({})
    print(f"Total record inserted successfully: {total_record}")

print("Initiating stress test...")
start_time = time.time()

# Clear collection beforehand
collection.drop()

with concurrent.futures.ThreadPoolExecutor(max_workers=THREADS) as executor:
    futures = [executor.submit(hammer_db, i) for i in range(THREADS)]
concurrent.futures.wait(futures)

duration = time.time() - start_time
total_queries = THREADS * OPS_PER_THREAD * 2  # Insert + Find

print(f"Test complete: {duration:.2f} seconds.")
print(f"Throughput: {total_queries / duration:.2f} QPS.")
printTotalRecordInserted()
