// Package grpcclient — клиент к ML-сервису Stego-Guard по gRPC.
// Обёртка над сгенерированным кодом: таймауты, единая точка вызова.
package grpcclient

import (
	"context"
	"fmt"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	stegov1 "github.com/lgr1dthebe4t22/stego-guard/api-gateway/proto-gen"
)

const rpcTimeout = 30 * time.Second // дедлайн одного RPC к ML-сервису

// Client — gRPC-клиент к ML-сервису.
type Client struct {
	conn *grpc.ClientConn
	rpc  stegov1.StegoServiceClient
}

// Dial подключается к ML-сервису. Без TLS — внутренний контур (Фаза 1).
func Dial(addr string) (*Client, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	conn, err := grpc.DialContext(ctx, addr,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithBlock(),
	)
	if err != nil {
		return nil, fmt.Errorf("ML-сервис недоступен (%s): %w", addr, err)
	}
	return &Client{conn: conn, rpc: stegov1.NewStegoServiceClient(conn)}, nil
}

// Close закрывает соединение.
func (c *Client) Close() error { return c.conn.Close() }

// Embed внедряет метку: изображение + ID пользователя -> защищённый файл.
func (c *Client) Embed(ctx context.Context, image []byte, userID, format string) (*stegov1.EmbedResponse, error) {
	ctx, cancel := context.WithTimeout(ctx, rpcTimeout)
	defer cancel()
	return c.rpc.EmbedWatermark(ctx, &stegov1.EmbedRequest{
		Image:        image,
		Payload:      &stegov1.Payload{UserId: userID},
		OutputFormat: format,
	})
}

// Verify проверяет документ: возвращает вердикт, BER, heatmap.
func (c *Client) Verify(ctx context.Context, image []byte) (*stegov1.VerifyResponse, error) {
	ctx, cancel := context.WithTimeout(ctx, rpcTimeout)
	defer cancel()
	return c.rpc.VerifyDocument(ctx, &stegov1.VerifyRequest{Image: image})
}
