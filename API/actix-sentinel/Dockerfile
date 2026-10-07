# 1. Chef / Planner Stage
FROM lukemathwalker/cargo-chef:latest-rust-1-bookworm AS chef
WORKDIR /app

FROM chef AS planner
COPY . .
RUN cargo chef prepare --recipe-path recipe.json

# 2. Builder Stage
FROM chef AS builder
RUN apt-get update && apt-get install -y \
    build-essential \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=planner /app/recipe.json recipe.json
# Build dependencies - this is the caching layer
RUN cargo chef cook --release --recipe-path recipe.json
# Build application
COPY . .
RUN cargo build --release --bin actix-sentinel

# 3. Runtime Stage (Must match the builder version)
FROM debian:bookworm-slim AS runtime
WORKDIR /app

# Install runtime dependencies (e.g. OpenSSL/ca-certificates if needed)
RUN apt-get update && apt-get install -y \
    ca-certificates \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/target/release/actix-sentinel /app/actix-sentinel

EXPOSE 8080
CMD ["/app/actix-sentinel"]