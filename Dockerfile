# syntax=docker/dockerfile:1

FROM ubuntu:24.04 AS builder

ARG REBECCA_VERSION=v0.1.4

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    tar \
    gzip \
    file \
    && rm -rf /var/lib/apt/lists/*


WORKDIR /build


RUN curl -fL \
https://github.com/rebeccapanel/Rebecca/releases/download/${REBECCA_VERSION}/rebecca-linux-amd64.tar.gz \
-o rebecca.tar.gz \
&& file rebecca.tar.gz \
&& tar -xzf rebecca.tar.gz \
&& rm rebecca.tar.gz



FROM ubuntu:24.04


ENV DEBIAN_FRONTEND=noninteractive \
    TZ=UTC \
    PORT=8080


RUN apt-get update && apt-get install -y \
    ca-certificates \
    curl \
    bash \
    sqlite3 \
    libffi8 \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*


WORKDIR /app


COPY --from=builder /build /app


COPY start.sh /app/start.sh


RUN chmod +x /app/start.sh \
    && chmod +x /app/rebecca-server \
    && chmod +x /app/rebecca-cli


RUN useradd -m -u 1000 rebecca \
    && chown -R rebecca:rebecca /app


USER rebecca


EXPOSE 8080


HEALTHCHECK --interval=30s \
--timeout=5s \
--start-period=40s \
--retries=5 \
CMD curl -fsS http://127.0.0.1:${PORT}/ || exit 1


ENTRYPOINT ["/app/start.sh"]
