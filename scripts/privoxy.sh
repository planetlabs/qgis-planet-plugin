#!/usr/bin/env bash

set -e

CMD="${1:-start}"
PRIVOXY_CACHE_DIR="$(pwd)/.privoxy-cache"
PRIVOXY_CONFIG_FILE="$(pwd)/.privoxy-config"
PRIVOXY_PID_FILE="$(pwd)/.privoxy.pid"

mkdir -p "$PRIVOXY_CACHE_DIR"

case "$CMD" in
    start)
        if [ ! -f "$PRIVOXY_CONFIG_FILE" ]; then
            cat >"$PRIVOXY_CONFIG_FILE" <<EOF
listen-address  127.0.0.1:8123
logdir $PRIVOXY_CACHE_DIR
confdir $PRIVOXY_CACHE_DIR
EOF
        fi
        if [ ! -f "$PRIVOXY_PID_FILE" ] || ! kill -0 "$(cat "$PRIVOXY_PID_FILE")" 2>/dev/null; then
            privoxy --pidfile "$PRIVOXY_PID_FILE" "$PRIVOXY_CONFIG_FILE" &
            echo $! >"$PRIVOXY_PID_FILE"
            echo "Started privoxy proxy on 127.0.0.1:8123 (logdir: $PRIVOXY_CACHE_DIR)"
        else
            echo "Privoxy already running (PID: $(cat "$PRIVOXY_PID_FILE"))"
        fi
        ;;
    stop)
        if [ -f "$PRIVOXY_PID_FILE" ]; then
            kill "$(cat "$PRIVOXY_PID_FILE")" && rm "$PRIVOXY_PID_FILE"
            echo "Stopped privoxy."
        else
            echo "Privoxy is not running."
        fi
        ;;
    restart)
        "$0" stop
        sleep 1
        "$0" start
        ;;
    status)
        if [ -f "$PRIVOXY_PID_FILE" ] && kill -0 "$(cat "$PRIVOXY_PID_FILE")" 2>/dev/null; then
            echo "Privoxy is running (PID: $(cat "$PRIVOXY_PID_FILE"))"
        else
            echo "Privoxy is not running."
        fi
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
