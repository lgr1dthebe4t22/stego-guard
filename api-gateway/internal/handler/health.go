package handler

import "github.com/gofiber/fiber/v2"

// Health — liveness-проба: GET /healthz. Для оркестратора и фронта.
func (d *Deps) Health(c *fiber.Ctx) error {
	return c.JSON(fiber.Map{
		"status":     "ok",
		"ml_service": d.Config.MLServiceAddr,
	})
}
