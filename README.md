# playground

Playground for benchmarking and testing languages.

## Mongo benchmark

The Mongo benchmarks under `benchmark/py-mongo` and `benchmark/go-mongo` are intended to be a fair comparison.

### Benchmark contract

Both implementations now use the same workload:
- 50 concurrent workers/threads
- 2000 insert + find pairs per worker/thread
- collection: `stress_db.mongo_benchmark`
- inserted document shape: `{worker, iteration}`
- read-after-write query: `{worker, iteration}`
- compound index on `(worker, iteration)` created before the timed section starts

### Result reporting

Both benchmarks report:
- test duration
- successful throughput
- attempted throughput
- insert attempts / successes / failures
- find attempts / successes / failures
- total records inserted successfully

### Running benchmarks

Python benchmark:
- `cd benchmark/py-mongo && python3 mongo.py`

Go benchmark:
- `cd benchmark/go-mongo && go run .`

### Capturing benchmark logs

Python benchmark runner:
- `cd benchmark/py-mongo && ./bench_mongo.sh`

Go benchmark runner:
- `cd benchmark/go-mongo && ./bench_mongo.sh`

The Go runner writes logs under `benchmark/benchmark_logs/go-mongo/<timestamp>/`.
