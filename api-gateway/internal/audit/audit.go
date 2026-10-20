// Package audit — журнал операций гейтвея (embed/verify) в JSON-строках.
// Фаза 1: пишем в stdout (соберёт Docker-логированием).
// Фаза 3: сюда же придёт запись в БД.
package audit

import (
	"encoding/json"
	"log"
	"time"
)

// Logger пишет аудит в стандартный лог.
type Logger struct {
	log *log.Logger
}

// New создаёт Logger.
func New() *Logger {
	return &Logger{log: log.New(log.Writer(), "AUDIT ", log.LstdFlags|log.Lmsgprefix)}
}

// Log фиксирует операцию с меткой времени и полями.
func (l *Logger) Log(op string, fields map[string]string) {
	entry := map[string]any{
		"ts":     time.Now().UTC().Format(time.RFC3339),
		"op":     op,
		"fields": fields,
	}
	data, err := json.Marshal(entry)
	if err != nil {
		l.log.Printf("op=%s (marshal error: %v) fields=%v", op, err, fields)
		return
	}
	l.log.Println(string(data))
}
