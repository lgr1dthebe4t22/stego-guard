package handler

import (
	"encoding/base64"

	"github.com/gofiber/fiber/v2"

	"github.com/lgr1dthebe4t22/stego-guard/api-gateway/internal/hashing"
	"github.com/lgr1dthebe4t22/stego-guard/api-gateway/internal/validation"
	stegov1 "github.com/lgr1dthebe4t22/stego-guard/api-gateway/proto-gen"
)

// Verify проверяет документ: POST /api/v1/verify (multipart: file).
// Отдаёт JSON-вердикт; heatmap — base64-PNG, только если есть вмешательство.
func (d *Deps) Verify(c *fiber.Ctx) error {
	maxBytes := d.Config.MaxUploadMB * 1024 * 1024

	data, err := readUpload(c, maxBytes)
	if err != nil {
		return badRequest(c, err)
	}
	if _, err := validation.ValidateImage(data, maxBytes); err != nil {
		return badRequest(c, err)
	}

	resp, err := d.ML.Verify(c.Context(), data)
	if err != nil {
		return c.Status(fiber.StatusBadGateway).
			JSON(fiber.Map{"error": "ML-сервис недоступен: " + err.Error()})
	}
	if resp.GetStatus() == stegov1.AuthenticityStatus_VERIFY_ERROR_INTERNAL {
		return c.Status(fiber.StatusBadGateway).
			JSON(fiber.Map{"error": resp.GetMessage()})
	}

	status := resp.GetStatus()
	d.Audit.Log("verify", map[string]string{
		"sha256":  hashing.Sum256(data),
		"status":  stegov1.AuthenticityStatus_name[int32(status)],
		"user_id": resp.GetExtractedUserId(),
	})

	body := fiber.Map{
		"status":     stegov1.AuthenticityStatus_name[int32(status)],
		"authentic":  status == stegov1.AuthenticityStatus_AUTHENTIC,
		"ber":        resp.GetBer(),
		"hash_match": resp.GetHashMatch(),
		"user_id":    resp.GetExtractedUserId(),
		"sha256":     hashing.Sum256(data),
	}
	if heat := resp.GetHeatmap(); len(heat) > 0 {
		body["heatmap_base64"] = base64.StdEncoding.EncodeToString(heat)
	}
	return c.JSON(body)
}
