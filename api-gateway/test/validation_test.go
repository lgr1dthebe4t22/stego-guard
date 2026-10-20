package validation_test

import (
	"bytes"
	"testing"

	"github.com/lgr1dthebe4t22/stego-guard/api-gateway/internal/validation"
)

var pngHeader = []byte{0x89, 'P', 'N', 'G', 0x0D, 0x0A, 0x1A, 0x0A}

func TestDetectFormatPNG(t *testing.T) {
	data := append(append([]byte{}, pngHeader...), []byte("данные")...)
	if got := validation.DetectFormat(data); got != "png" {
		t.Errorf("DetectFormat(PNG) = %q, ожидалось png", got)
	}
}

func TestDetectFormatJPEG(t *testing.T) {
	data := []byte{0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10}
	if got := validation.DetectFormat(data); got != "jpeg" {
		t.Errorf("DetectFormat(JPEG) = %q, ожидалось jpeg", got)
	}
}

func TestDetectFormatUnknown(t *testing.T) {
	if got := validation.DetectFormat([]byte("MZ exe файл")); got != "" {
		t.Errorf("DetectFormat(exe) = %q, ожидалось пустое", got)
	}
	if got := validation.DetectFormat([]byte{0x89, 'P', 'N'}); got != "" {
		t.Errorf("DetectFormat(обрезок) = %q, ожидалось пустое", got)
	}
}

func TestValidateImageLimit(t *testing.T) {
	data := bytes.Repeat([]byte{0xFF}, 100)
	if _, err := validation.ValidateImage(data, 1); err == nil {
		t.Error("ValidateImage должен отклонить файл больше лимита")
	}
}
