#!/usr/bin/env bash

set -e

CMD="${1:-start}"
PRIVOXY_CACHE_DIR="$(pwd)/.privoxy-cache"
PRIVOXY_CONFIG_FILE="$(pwd)/.privoxy-config"
PRIVOXY_PID_FILE="$(pwd)/.privoxy.pid"
PRIVOXY_CA_CERT_FILE="$PRIVOXY_CACHE_DIR/ca-cert.pem"
PRIVOXY_CA_KEY_FILE="$PRIVOXY_CACHE_DIR/ca-key.pem"

mkdir -p "$PRIVOXY_CACHE_DIR"

generate_ca() {
    if [ ! -f "$PRIVOXY_CA_CERT_FILE" ] || [ ! -f "$PRIVOXY_CA_KEY_FILE" ]; then
        echo "Generating CA certificate for HTTPS inspection..."
        openssl req -x509 -newkey rsa:2048 -days 365 -nodes \
            -keyout "$PRIVOXY_CA_KEY_FILE" \
            -out "$PRIVOXY_CA_CERT_FILE" \
            -subj "/CN=Privoxy CA"
        echo "CA certificate generated at: $PRIVOXY_CA_CERT_FILE"
    else
        echo "CA certificate already exists at: $PRIVOXY_CA_CERT_FILE"
    fi
}

show_help() {
    echo "Usage: $0 {start|stop|restart|status|generate-ca|help}"
    echo ""
    echo "Commands:"
    echo "  start        Start privoxy with HTTPS support"
    echo "  stop         Stop privoxy"
    echo "  restart      Restart privoxy"
    echo "  status       Show privoxy status"
    echo "  generate-ca  Generate a new CA certificate for HTTPS interception"
    echo "  help         Show this help message"
    echo ""
    echo "The CA certificate is required for HTTPS interception. After running 'generate-ca',"
    echo "import $PRIVOXY_CA_CERT_FILE into your browser/system to avoid HTTPS warnings."
}

case "$CMD" in
    start)
        generate_ca
        if [ ! -f "$PRIVOXY_CONFIG_FILE" ]; then
            cat >"$PRIVOXY_CONFIG_FILE" <<EOF
listen-address  127.0.0.1:8123
logdir $PRIVOXY_CACHE_DIR
confdir $PRIVOXY_CACHE_DIR
enable-ssl-intercept 1
ca-key-file $PRIVOXY_CA_KEY_FILE
ca-cert-file $PRIVOXY_CA_CERT_FILE
EOF
        fi
        if [ ! -f "$PRIVOXY_PID_FILE" ] || ! kill -0 "$(cat "$PRIVOXY_PID_FILE")" 2>/dev/null; then
            privoxy --pidfile "$PRIVOXY_PID_FILE" "$PRIVOXY_CONFIG_FILE" &
            echo $! >"$PRIVOXY_PID_FILE"
            echo "Started privoxy proxy with HTTPS support on 127.0.0.1:8123 (logdir: $PRIVOXY_CACHE_DIR)"
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
    generate-ca)
        generate_ca
        ;;
    help | --help | -h)
        show_help
        ;;
    *)
        show_help
        exit 1
        ;;
esac
