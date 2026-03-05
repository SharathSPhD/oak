FROM alpine:3.19

RUN apk add --no-cache docker-cli docker-cli-compose curl jq bash

COPY docker/watchdog/watchdog.sh /usr/local/bin/watchdog.sh
RUN chmod +x /usr/local/bin/watchdog.sh

ENTRYPOINT ["/usr/local/bin/watchdog.sh"]
