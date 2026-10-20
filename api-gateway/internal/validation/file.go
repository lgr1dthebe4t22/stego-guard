// Package validation — проверка загружаемых файлов ПО МАГИЧЕСКИМ БАЙТАМ,
// а не по расширению или Content-Type (их клиент подделывает за секунду).
package validation

import (
	"bytes"
	"errors"
	"fmt"
)

// ErrBadFormat — файл не распознан как поддерживаемое изображение.
var ErrBadFormat = errors.New("файл не является PNG или JPEG (по магическим байтам)")

var pngMagic = []byte{0x89, 'P', 'N', 'G', 0x0D, 0x0A, 0x1A, 0x0A}

// DetectFormat возвращает "png", "jpeg" или "" если формат неизвестен.
func DetectFormat(data []byte) string {
	switch {
	case len(data) >= len(pngMagic) && bytes.Equal(data[:len(pngMagic)], pngMagic):
		return "png"
	case len(data) >= 3 && data[0] == 0xFF && data[1] == 0xD8 && data[2] == 0xFF:
		return "jpeg"
	default:
		return ""
	}
}

// ValidateImage проверяет, что данные — корректное PNG/JPEG изображение
// разумного размера. Возвращает формат ("png"/"jpeg") или ошибку.
func ValidateImage(data []byte, maxBytes int64) (string, error) {
	if int64(len(data)) > maxBytes {
		return "", fmt.Errorf("файл больше лимита %d МБ", maxBytes/(1024*1024))
	}
	format := DetectFormat(data)
	if format == "" {
		return "", ErrBadFormat
	}
	return format, nil
}
