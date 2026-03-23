#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BENCHMARK_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BENCHMARK_NAME="py-mongo"
CONTAINER_NAME="mongo01"
TIMESTAMP="$(date -u +%Y%m%d_%H%M%S)"
LOG_DIR="${BENCHMARK_ROOT}/benchmark_logs/${BENCHMARK_NAME}_${TIMESTAMP}"

mkdir -p "$LOG_DIR"

echo "Igniting monitoring daemons..."
echo "Logs will be written to: $LOG_DIR"

docker stats --no-stream=false --format "{{.Name}} | CPU: {{.CPUPerc}} | Mem: {{.MemUsage}} | Net: {{.NetIO}} | I/O: {{.BlockIO}}" "$CONTAINER_NAME" > "${LOG_DIR}/docker_stats.log" &
pid_docker=$!

mongostat > "${LOG_DIR}/mongostat.log" &
pid_mongostat=$!

mongotop > "${LOG_DIR}/mongotop.log" &
pid_mongotop=$!

cleanup() {
  echo "Benchmark finished. Terminating monitoring..."
  kill "$pid_docker" "$pid_mongostat" "$pid_mongotop" 2>/dev/null || true
  wait "$pid_docker" "$pid_mongostat" "$pid_mongotop" 2>/dev/null || true
  python3 "${BENCHMARK_ROOT}/report.py" "$LOG_DIR" --benchmark-name "Python Mongo benchmark" >/tmp/py_mongo_report.log 2>&1 || {
    cat /tmp/py_mongo_report.log
    return
  }
  cat /tmp/py_mongo_report.log
  echo "Done. Logs are resting quietly in $LOG_DIR/"
}
trap cleanup EXIT

echo "Executing benchmark..."
(
  cd "$SCRIPT_DIR"
  python3 mongo.py
) | tee "${LOG_DIR}/benchmark_output.log"
