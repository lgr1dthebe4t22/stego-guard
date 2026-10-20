// Package config — конфигурация гейтвея из переменных окружения.
// Значения по умолчанию подходят для локальной разработки.
package config

import (
	"log"
	"os"
	"strconv"
)

// Config — параметры запуска API-гейтвея.
type Config struct {
	Port          int    // HTTP-порт гейтвея
	MLServiceAddr string // адрес ML-сервиса по gRPC
	MaxUploadMB   int64  // лимит размера загрузки в мегабайтах
}

// Load читает конфиг из окружения, подставляя значения по умолчанию.
func Load() Config {
	return Config{
		Port:          getEnvInt("PORT", 8080),
		MLServiceAddr: getEnv("ML_SERVICE_ADDR", "localhost:50051"),
		MaxUploadMB:   int64(getEnvInt("MAX_UPLOAD_MB", 25)),
	}
}

func getEnv(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func getEnvInt(key string, def int) int {
	v := os.Getenv(key)
	if v == "" {
		return def
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		log.Printf("config: %s=%q не число, использую %d", key, v, def)
		return def
	}
	return n
}
