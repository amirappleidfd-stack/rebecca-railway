# syntax=docker/dockerfile:1

ARG REBECCA_VERSION=v0.1.4

FROM debian:bookworm-slim AS builder

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    tar \
    bash \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

RUN curl -L \
https://github.com/rebeccapanel/Rebecca/releases/download/${REBECCA_VERSION}/rebecca-linux-amd64.tar.gz \
-o rebecca.tar.gz \
&& tar -xzf rebecca.tar.gz \
&& rm rebecca.tar.gz


FROM debian:bookworm-slim


ENV TZ=UTC \
    REBECCA_HOME=/app \
    PORT=8080


RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    bash \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*


WORKDIR /app


COPY --from=builder /build /app


COPY start.sh /app/start.sh

RUN chmod +x /app/start.sh


RUN useradd -m -u 1000 rebecca \
    && chown -R rebecca:rebecca /app


USER rebecca


EXPOSE 8080


HEALTHCHECK --interval=30s \
--timeout=5s \
--start-period=30s \
--retries=5 \
CMD curl -fsS http://127.0.0.1:${PORT}/ || exit 1


ENTRYPOINT ["/app/start.sh"]
