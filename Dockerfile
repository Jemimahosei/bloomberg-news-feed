# Multi-stage build: compile the React frontend, then the Go binary
# (which embeds the frontend), then ship one slim runtime image.
# The sample dataset is embedded in the binary (go:embed), so no data
# files need to be copied into the runtime image.

# Stage 1: React frontend (Vite build -> static dist/)
FROM node:20-alpine AS frontend
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# Stage 2: Go backend. The built frontend is copied into cmd/server/dist
# so the binary embeds it and serves the UI from the same port as the API.
FROM golang:1.23-alpine AS build
WORKDIR /src
COPY go.mod ./
COPY . .
COPY --from=frontend /web/dist ./cmd/server/dist
RUN CGO_ENABLED=0 go build -trimpath -o /out/newsfeed ./cmd/server

# Stage 3: slim runtime. No Node, no Go toolchain, just the binary.
FROM alpine:3.20
RUN apk --no-cache add ca-certificates
COPY --from=build /out/newsfeed /usr/local/bin/newsfeed
EXPOSE 8080
ENTRYPOINT ["newsfeed"]
