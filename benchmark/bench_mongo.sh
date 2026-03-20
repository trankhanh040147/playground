#!/usr/bin/env fish

# Configuration
set CONTAINER_NAME "mongo01"
set LOG_DIR "./benchmark_logs"

mkdir -p $LOG_DIR

echo "Igniting monitoring daemons..."

# 1. Start docker stats
# The --format flag ensures clean, line-by-line output without ANSI redraw codes
docker stats --format "{{.Name}} | CPU: {{.CPUPerc}} | Mem: {{.MemUsage}} | Net: {{.NetIO}} | I/O: {{.BlockIO}}" $CONTAINER_NAME > $LOG_DIR/docker_stats.log &
set pid_docker $last_pid

# 2. Start mongostat
mongostat > $LOG_DIR/mongostat.log &
set pid_mongostat $last_pid

# 3. Start mongotop
mongotop > $LOG_DIR/mongotop.log &
set pid_mongotop $last_pid

echo "Executing benchmark..."

# Run your existing Python stress test script
python3 mongo.py

echo "Benchmark finished. Terminating monitoring..."

# Clean up the background processes
kill $pid_docker $pid_mongostat $pid_mongotop

echo "Done. Logs are resting quietly in $LOG_DIR/"