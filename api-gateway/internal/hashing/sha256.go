// Package hashing — SHA-256 документа (аудит и сверки).
package hashing

import (
	"crypto/sha256"
	"encoding/hex"
)

// Sum256 возвращает hex-строку SHA-256 содержимого.
func Sum256(data []byte) string {
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}
