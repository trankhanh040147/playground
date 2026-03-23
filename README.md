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

Both runners now write every artifact for a run into a single timestamped directory under `benchmark/benchmark_logs/`, including:
- `benchmark_output.log`
- `docker_stats.log`
- `mongostat.log`
- `mongotop.log`
- `report.html`
- `report.json`

Each run generates a self-contained HTML report with summary cards, charts, parsed metrics, and the raw benchmark output for easier inspection.
