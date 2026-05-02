package main

import "net/http"

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/tasks", nil)
	mux.HandleFunc("/api/v1/tasks/{id}", nil)
}
