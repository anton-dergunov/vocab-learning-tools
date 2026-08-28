FROM alpine:3.22

ARG PB_VERSION=0.39.10
ARG TARGETARCH

RUN apk add --no-cache ca-certificates unzip wget \
    && DETECTED_ARCH="${TARGETARCH:-$(apk --print-arch)}" \
    && case "$DETECTED_ARCH" in \
         amd64|x86_64) PB_ARCH="amd64" ;; \
         arm64|aarch64) PB_ARCH="arm64" ;; \
         *) echo "Unsupported architecture: $DETECTED_ARCH"; exit 1 ;; \
       esac \
    && wget -q -O /tmp/pocketbase.zip \
       "https://github.com/pocketbase/pocketbase/releases/download/v${PB_VERSION}/pocketbase_${PB_VERSION}_linux_${PB_ARCH}.zip" \
    && unzip /tmp/pocketbase.zip -d /pb \
    && rm /tmp/pocketbase.zip

WORKDIR /pb
COPY deploy/acervo/pocketbase/pb_hooks /pb/pb_hooks
COPY deploy/acervo/pocketbase/pb_migrations /pb/pb_migrations
COPY deploy/acervo/pocketbase/pb_public /pb/pb_public
RUN mkdir -p /pb/downloads /pb/pb_data \
    && chmod -R a+rX /pb/pb_hooks /pb/pb_migrations /pb/pb_public \
    && chmod a+rx /pb /pb/downloads /pb/pb_data

EXPOSE 8090
CMD ["/pb/pocketbase", "serve", "--http=0.0.0.0:8090"]
