package main

import (
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/gin-gonic/gin"
	"github.com/labstack/echo/v4"
)

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/v1/tasks", handler)
	mux.HandleFunc("/api/v1/tasks/", handler)

	r := chi.NewRouter()
	r.Get("/users/{id}", handler)
	r.Post("/users", handler)

	g := gin.Default()
	g.GET("/healthz", handler)
	g.PUT("/items/:id", handler)

	e := echo.New()
	e.DELETE("/files/:name", handler)
}

func handler(http.ResponseWriter, *http.Request) {}
