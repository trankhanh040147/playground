#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="mongo01"
LOG_ROOT="../benchmark_logs/go-mongo"
TIMESTAMP="$(date -u +%Y%m%d_%H%M%S)"
LOG_DIR="${LOG_ROOT}/${TIMESTAMP}"

mkdir -p "$LOG_DIR"

echo "Igniting monitoring daemons..."

docker stats --format "{{.Name}} | CPU: {{.CPUPerc}} | Mem: {{.MemUsage}} | Net: {{.NetIO}} | I/O: {{.BlockIO}}" "$CONTAINER_NAME" > "${LOG_DIR}/docker_stats.log" &
pid_docker=$!

mongostat > "${LOG_DIR}/mongostat.log" &
pid_mongostat=$!

mongotop > "${LOG_DIR}/mongotop.log" &
pid_mongotop=$!

cleanup() {
  echo "Benchmark finished. Terminating monitoring..."
  kill "$pid_docker" "$pid_mongostat" "$pid_mongotop" 2>/dev/null || true
  wait "$pid_docker" "$pid_mongostat" "$pid_mongotop" 2>/dev/null || true
  echo "Done. Logs are resting quietly in $LOG_DIR/"
}
trap cleanup EXIT

echo "Executing Go benchmark..."
go run . | tee "${LOG_DIR}/benchmark_output.log"
