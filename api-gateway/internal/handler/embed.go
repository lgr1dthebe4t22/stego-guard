// Package handler — HTTP-обработчики API-гейтвея (Fiber).
package handler

import (
	"fmt"
	"io"

	"github.com/gofiber/fiber/v2"

	"github.com/lgr1dthebe4t22/stego-guard/api-gateway/internal/config"
	"github.com/lgr1dthebe4t22/stego-guard/api-gateway/internal/grpcclient"
	"github.com/lgr1dthebe4t22/stego-guard/api-gateway/internal/hashing"
	"github.com/lgr1dthebe4t22/stego-guard/api-gateway/internal/validation"
	stegov1 "github.com/lgr1dthebe4t22/stego-guard/api-gateway/proto-gen"
)

// Deps — зависимости, которые получают все обработчики (собираются в main).
type Deps struct {
	Config config.Config
	ML     *grpcclient.Client
	Audit  Auditor
}

// Auditor — журнал операций. Реализуется пакетом audit (следующая порция):
// через интерфейс handler не зависит от конкретной реализации.
type Auditor interface {
	Log(op string, fields map[string]string)
}

// readUpload вытаскивает файл из multipart-формы с лимитом размера.
func readUpload(c *fiber.Ctx, maxBytes int64) ([]byte, error) {
	fh, err := c.FormFile("file")
	if err != nil {
		return nil, fmt.Errorf("нет поля 'file': %w", err)
	}
	if fh.Size > maxBytes {
		return nil, fmt.Errorf("файл больше лимита %d МБ", maxBytes/(1024*1024))
	}
	f, err := fh.Open()
	if err != nil {
		return nil, fmt.Errorf("не удалось прочитать файл: %w", err)
	}
	defer f.Close()

	data, err := io.ReadAll(io.LimitReader(f, maxBytes+1))
	if err != nil {
		return nil, fmt.Errorf("ошибка чтения файла: %w", err)
	}
	if int64(len(data)) > maxBytes {
		return nil, fmt.Errorf("файл больше лимита %d МБ", maxBytes/(1024*1024))
	}
	return data, nil
}

// badRequest — единый формат ошибок 400.
func badRequest(c *fiber.Ctx, err error) error {
	return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{"error": err.Error()})
}

// Embed защищает документ: POST /api/v1/embed (multipart: file, user_id).
// Отдаёт защищённый файл на скачивание; хэш и ID — в заголовках ответа.
func (d *Deps) Embed(c *fiber.Ctx) error {
	maxBytes := d.Config.MaxUploadMB * 1024 * 1024

	data, err := readUpload(c, maxBytes)
	if err != nil {
		return badRequest(c, err)
	}
	format, err := validation.ValidateImage(data, maxBytes)
	if err != nil {
		return badRequest(c, err)
	}
	userID := c.FormValue("user_id")
	if userID == "" {
		return badRequest(c, fmt.Errorf("нет поля 'user_id'"))
	}

	resp, err := d.ML.Embed(c.Context(), data, userID, format)
	if err != nil {
		return c.Status(fiber.StatusBadGateway).
			JSON(fiber.Map{"error": "ML-сервис недоступен: " + err.Error()})
	}
	if resp.GetStatus() != stegov1.EmbedStatus_EMBED_OK {
		return c.Status(fiber.StatusUnprocessableEntity).
			JSON(fiber.Map{"error": resp.GetMessage()})
	}

	sha := hashing.Sum256(data)
	d.Audit.Log("embed", map[string]string{
		"user_id": userID, "sha256": sha, "format": format,
	})

	c.Set("X-Content-SHA256", sha)
	c.Set("X-User-Id", userID)
	c.Set("Content-Disposition",
		fmt.Sprintf(`attachment; filename="protected.%s"`, format))
	return c.Type(format).Send(resp.GetWatermarkedImage())
}
