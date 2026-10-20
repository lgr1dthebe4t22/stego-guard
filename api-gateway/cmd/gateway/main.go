// Package main — точка входа API-гейтвея Stego-Guard.
// Собирает конфиг, gRPC-клиент к ML-сервису, HTTP-сервер (Fiber).
package main

import (
	"log"
	"os"
	"os/signal"
	"strconv"
	"syscall"

	"github.com/gofiber/fiber/v2"

	"github.com/lgr1dthebe4t22/stego-guard/api-gateway/internal/audit"
	"github.com/lgr1dthebe4t22/stego-guard/api-gateway/internal/config"
	"github.com/lgr1dthebe4t22/stego-guard/api-gateway/internal/grpcclient"
	"github.com/lgr1dthebe4t22/stego-guard/api-gateway/internal/handler"
)

func main() {
	cfg := config.Load()

	ml, err := grpcclient.Dial(cfg.MLServiceAddr)
	if err != nil {
		log.Fatalf("не удалось подключиться к ML-сервису: %v", err)
	}
	defer ml.Close()

	deps := &handler.Deps{Config: cfg, ML: ml, Audit: audit.New()}

	app := fiber.New(fiber.Config{
		BodyLimit: int(cfg.MaxUploadMB) * 1024 * 1024,
	})
	app.Post("/api/v1/embed", deps.Embed)
	app.Post("/api/v1/verify", deps.Verify)
	app.Get("/healthz", deps.Health)

	go func() {
		if err := app.Listen(":" + strconv.Itoa(cfg.Port)); err != nil {
			log.Fatalf("HTTP-сервер упал: %v", err)
		}
	}()
	log.Printf("API-гейтвей слушает порт %d, ML-сервис: %s", cfg.Port, cfg.MLServiceAddr)

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)
	<-stop

	log.Println("остановка...")
	if err := app.Shutdown(); err != nil {
		log.Printf("ошибка остановки: %v", err)
	}
}
