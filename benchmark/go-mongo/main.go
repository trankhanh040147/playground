package main

import (
	"context"
	"fmt"
	"log"
	"sync"
	"time"

	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

const (
	uri          = "mongodb://localhost:27017/"
	dbName       = "stress_db"
	collName     = "go_test_data"
	workers      = 50
	opsPerWorker = 3000
)

func hammerDB(ctx context.Context, coll *mongo.Collection, workerID int, wg *sync.WaitGroup) {
	defer wg.Done()
	for i := 0; i < opsPerWorker; i++ {
		// 1. Ghi dữ liệu
		_, err := coll.InsertOne(ctx, bson.M{"worker": workerID, "iteration": i})
		if err != nil {
			log.Printf("Insert failed on worker %d: %v", workerID, err)
			continue
		}

		// 2. Đọc dữ liệu vừa ghi
		var result bson.M
		err = coll.FindOne(ctx, bson.M{"worker": workerID, "iteration": i}).Decode(&result)
		if err != nil {
			log.Printf("Find failed on worker %d: %v", workerID, err)
		}
	}
}

func printTotalRecordInserted(ctx context.Context, coll *mongo.Collection) {
	result, err := coll.CountDocuments(ctx, bson.M{})
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("Total records inserted successfully: %d\n", result)
}

func main() {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	defer cancel()

	// Thiết lập connection pool lớn hơn mặc định để chịu tải
	clientOpts := options.Client().ApplyURI(uri).SetMaxPoolSize(100)
	client, err := mongo.Connect(ctx, clientOpts)
	if err != nil {
		log.Fatal(err)
	}
	defer client.Disconnect(ctx)

	coll := client.Database(dbName).Collection(collName)

	// Xóa data cũ để test được khách quan
	coll.Drop(ctx)

	fmt.Println("Initiating brutal stress test with Go...")
	startTime := time.Now()

	var wg sync.WaitGroup
	wg.Add(workers)

	// Kích hoạt các goroutines
	for i := 0; i < workers; i++ {
		go hammerDB(ctx, coll, i, &wg)
	}

	// Đợi tất cả goroutines hoàn thành
	wg.Wait()

	duration := time.Since(startTime).Seconds()
	totalQueries := float64(workers * opsPerWorker * 2) // Insert + Find

	fmt.Printf("Test complete: %.2f seconds.\n", duration)
	fmt.Printf("Throughput: %.2f QPS.\n", totalQueries/duration)
	printTotalRecordInserted(ctx, coll)
}
