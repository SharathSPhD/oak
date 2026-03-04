FROM alpine:3.20
RUN apk add --no-cache bash curl docker-cli jq
COPY scripts/oak-daemon.sh /usr/local/bin/oak-daemon.sh
RUN chmod +x /usr/local/bin/oak-daemon.sh
CMD ["/usr/local/bin/oak-daemon.sh"]
