FROM rust:1-alpine AS builder

RUN apk add --no-cache musl-dev
WORKDIR /app

COPY . .
RUN cargo build --release

FROM alpine:3

ARG BIN_NAME=api
RUN addgroup -S app && adduser -S app -G app
WORKDIR /app
COPY --from=builder /app/target/release/${BIN_NAME} /usr/local/bin/api
USER app
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/api"]
