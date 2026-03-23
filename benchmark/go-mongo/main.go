package main

import (
	"context"
	"fmt"
	"log"
	"sync"
	"sync/atomic"
	"time"

	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

const (
	uri              = "mongodb://localhost:27017/"
	dbName           = "stress_db"
	collName         = "mongo_benchmark"
	workers          = 50
	opsPerWorker     = 2000
	maxPoolSize      = 100
	operationTimeout = 10 * time.Second
)

type counters struct {
	insertAttempts int64
	insertSuccess  int64
	insertFailures int64
	findAttempts   int64
	findSuccess    int64
	findFailures   int64
}

func hammerDB(coll *mongo.Collection, workerID int, stats *counters, wg *sync.WaitGroup) {
	defer wg.Done()

	for i := 0; i < opsPerWorker; i++ {
		doc := bson.M{"worker": workerID, "iteration": i}
		filter := bson.M{"worker": workerID, "iteration": i}

		atomic.AddInt64(&stats.insertAttempts, 1)
		insertCtx, cancelInsert := context.WithTimeout(context.Background(), operationTimeout)
		_, err := coll.InsertOne(insertCtx, doc)
		cancelInsert()
		if err != nil {
			atomic.AddInt64(&stats.insertFailures, 1)
			log.Printf("Insert failed on worker %d iteration %d: %v", workerID, i, err)
			continue
		}
		atomic.AddInt64(&stats.insertSuccess, 1)

		atomic.AddInt64(&stats.findAttempts, 1)
		findCtx, cancelFind := context.WithTimeout(context.Background(), operationTimeout)
		var result bson.M
		err = coll.FindOne(findCtx, filter).Decode(&result)
		cancelFind()
		if err != nil {
			atomic.AddInt64(&stats.findFailures, 1)
			log.Printf("Find failed on worker %d iteration %d: %v", workerID, i, err)
			continue
		}
		atomic.AddInt64(&stats.findSuccess, 1)
	}
}

func countRecords(coll *mongo.Collection) int64 {
	countCtx, cancel := context.WithTimeout(context.Background(), operationTimeout)
	defer cancel()

	result, err := coll.CountDocuments(countCtx, bson.M{})
	if err != nil {
		log.Fatal(err)
	}

	return result
}

func ensureBenchmarkIndex(coll *mongo.Collection) {
	indexCtx, cancel := context.WithTimeout(context.Background(), operationTimeout)
	defer cancel()

	_, err := coll.Indexes().CreateOne(indexCtx, mongo.IndexModel{
		Keys: bson.D{{Key: "worker", Value: 1}, {Key: "iteration", Value: 1}},
	})
	if err != nil {
		log.Fatal(err)
	}
}

func main() {
	setupCtx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	clientOpts := options.Client().ApplyURI(uri).SetMaxPoolSize(maxPoolSize)
	client, err := mongo.Connect(setupCtx, clientOpts)
	if err != nil {
		log.Fatal(err)
	}
	defer func() {
		disconnectCtx, disconnectCancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer disconnectCancel()
		if err := client.Disconnect(disconnectCtx); err != nil {
			log.Printf("disconnect failed: %v", err)
		}
	}()

	coll := client.Database(dbName).Collection(collName)

	dropCtx, dropCancel := context.WithTimeout(context.Background(), operationTimeout)
	if err := coll.Drop(dropCtx); err != nil {
		dropCancel()
		log.Fatal(err)
	}
	dropCancel()

	ensureBenchmarkIndex(coll)

	fmt.Println("Initiating stress test with Go...")
	startTime := time.Now()

	var wg sync.WaitGroup
	stats := &counters{}
	wg.Add(workers)

	for i := 0; i < workers; i++ {
		go hammerDB(coll, i, stats, &wg)
	}

	wg.Wait()

	duration := time.Since(startTime).Seconds()
	successfulOperations := atomic.LoadInt64(&stats.insertSuccess) + atomic.LoadInt64(&stats.findSuccess)
	attemptedOperations := atomic.LoadInt64(&stats.insertAttempts) + atomic.LoadInt64(&stats.findAttempts)

	fmt.Printf("Test complete: %.2f seconds.\n", duration)
	fmt.Printf("Successful throughput: %.2f QPS.\n", float64(successfulOperations)/duration)
	fmt.Printf("Attempted throughput: %.2f QPS.\n", float64(attemptedOperations)/duration)
	fmt.Printf("Insert attempts: %d\n", atomic.LoadInt64(&stats.insertAttempts))
	fmt.Printf("Insert successes: %d\n", atomic.LoadInt64(&stats.insertSuccess))
	fmt.Printf("Insert failures: %d\n", atomic.LoadInt64(&stats.insertFailures))
	fmt.Printf("Find attempts: %d\n", atomic.LoadInt64(&stats.findAttempts))
	fmt.Printf("Find successes: %d\n", atomic.LoadInt64(&stats.findSuccess))
	fmt.Printf("Find failures: %d\n", atomic.LoadInt64(&stats.findFailures))
	fmt.Printf("Total records inserted successfully: %d\n", countRecords(coll))
}
