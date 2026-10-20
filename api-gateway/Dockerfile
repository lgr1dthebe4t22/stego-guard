# API-гейтвей Stego-Guard: мультистейдж-сборка Go
# build — полный образ с компилятором, runtime — лёгкий slim без Go
FROM golang:1.27-bookworm AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /bin/gateway ./cmd/gateway

FROM debian:bookworm-slim
WORKDIR /app
COPY --from=build /bin/gateway .
EXPOSE 8080
CMD ["./gateway"]