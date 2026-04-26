package main

import (
	"github.com/IBM/sarama"
	"github.com/segmentio/kafka-go"
)

func main() {
	_ = kafka.NewWriter(kafka.WriterConfig{
		Brokers: []string{"kafka:9092"},
		Topic:   "tasks.created.v1",
	})
	_ = kafka.NewReader(kafka.ReaderConfig{
		Brokers: []string{"kafka:9092"},
		Topic:   "tasks.assigned.v1",
		GroupID: "geo-service",
	})

	cfg := sarama.NewConfig()
	producer, _ := sarama.NewSyncProducer([]string{"kafka:9092"}, cfg)
	_, _, _ = producer.SendMessage(&sarama.ProducerMessage{Topic: "geo.points.v1"})

	cg, _ := sarama.NewConsumerGroup([]string{"kafka:9092"}, "geo-service", cfg)
	_ = cg
	topics := []string{"profiles.updated.v1"}
	_ = topics
}
