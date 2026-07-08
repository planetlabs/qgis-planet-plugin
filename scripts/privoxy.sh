#!/usr/bin/env bash

set -e

CMD="${1:-start}"
PRIVOXY_CACHE_DIR="$(pwd)/.privoxy-cache"
PRIVOXY_CONFIG_FILE="$(pwd)/.privoxy-config"
PRIVOXY_PID_FILE="$(pwd)/.privoxy.pid"
PRIVOXY_CA_CERT_FILE="$PRIVOXY_CACHE_DIR/ca-cert.pem"
PRIVOXY_CA_KEY_FILE="$PRIVOXY_CACHE_DIR/ca-key.pem"
PAC_SERVER_PID_FILE="$(pwd)/.pac-server.pid"
PAC_SERVER_PORT="8080"

mkdir -p "$PRIVOXY_CACHE_DIR"

# Detect virsh/libvirt bridge IPs for VM testing
get_virsh_ips() {
  # Look for virbr* interfaces that are UP and extract their IPv4 addresses
  ip -4 addr show 2>/dev/null | awk '/virbr[0-9]/ && /inet / {print $2}' | cut -d/ -f1
}

open_firewall() {
  echo "🔥"
  echo "🔥  SECURITY WARNING: OPENING FIREWALL"
  echo "🔥  PORT 8123 ACCESSIBLE FROM NETWORK"
  echo "🔥   PRIVOXY PROXY EXPOSED TO WORLD"
  echo "🔥    USE WITH EXTREME CAUTION!!!"
  echo "🔥"
  sudo iptables -I INPUT -p tcp --dport 8123 -j ACCEPT
  echo "🔓 Firewall port 8123 opened"
}

close_firewall() {
  sudo iptables -D INPUT -p tcp --dport 8123 -j ACCEPT 2>/dev/null || true
  echo "🔒 Firewall port 8123 closed"
}

start_pac_server() {
  local proxy_ip
  proxy_ip=$(ip route get 1.1.1.1 | awk '{print $7}' | head -1)

  local pac_file
  pac_file="$(pwd)/proxy.pac"

  if [ -f "$PAC_SERVER_PID_FILE" ] && kill -0 "$(cat "$PAC_SERVER_PID_FILE")" 2>/dev/null; then
    echo "🌐 PAC server already running (PID: $(cat "$PAC_SERVER_PID_FILE"))"
    return 0
  fi

  # Open firewall for PAC server
  sudo iptables -I INPUT -p tcp --dport "$PAC_SERVER_PORT" -j ACCEPT
  echo "🔓 Firewall port $PAC_SERVER_PORT opened for PAC server"

  # Start simple HTTP server for PAC file
  if command -v python3 >/dev/null 2>&1; then
    cd "$(dirname "$pac_file")"
    python3 -m http.server "$PAC_SERVER_PORT" >/dev/null 2>&1 &
    echo $! >"$PAC_SERVER_PID_FILE"
    cd - >/dev/null
    echo "🌐 PAC server started on port $PAC_SERVER_PORT (PID: $(cat "$PAC_SERVER_PID_FILE"))"
    echo "   PAC URL: http://$proxy_ip:$PAC_SERVER_PORT/proxy.pac"
    for virsh_ip in $(get_virsh_ips); do
      echo "   PAC URL (virsh VM): http://$virsh_ip:$PAC_SERVER_PORT/proxy.pac"
    done
  elif command -v python >/dev/null 2>&1; then
    cd "$(dirname "$pac_file")"
    python -m SimpleHTTPServer "$PAC_SERVER_PORT" >/dev/null 2>&1 &
    echo $! >"$PAC_SERVER_PID_FILE"
    cd - >/dev/null
    echo "🌐 PAC server started on port $PAC_SERVER_PORT (PID: $(cat "$PAC_SERVER_PID_FILE"))"
    echo "   PAC URL: http://$proxy_ip:$PAC_SERVER_PORT/proxy.pac"
    for virsh_ip in $(get_virsh_ips); do
      echo "   PAC URL (virsh VM): http://$virsh_ip:$PAC_SERVER_PORT/proxy.pac"
    done
  else
    echo "⚠️  Warning: Neither python3 nor python found - cannot start PAC server"
    echo "   You'll need to serve the PAC file manually or use file:// URLs"
  fi
}

stop_pac_server() {
  if [ -f "$PAC_SERVER_PID_FILE" ]; then
    if kill "$(cat "$PAC_SERVER_PID_FILE")" 2>/dev/null; then
      echo "🌐 PAC server stopped"
    fi
    rm -f "$PAC_SERVER_PID_FILE"
  fi
  # Close firewall for PAC server
  sudo iptables -D INPUT -p tcp --dport "$PAC_SERVER_PORT" -j ACCEPT 2>/dev/null || true
  echo "🔒 Firewall port $PAC_SERVER_PORT closed"
}

generate_pac() {
  local proxy_ip
  proxy_ip=$(ip route get 1.1.1.1 | awk '{print $7}' | head -1)

  local pac_file
  pac_file="$(pwd)/proxy.pac"

  cat >"$pac_file" <<EOF
function FindProxyForURL(url, host) {
    // Remove port number from host if present
    var hostNoPort = host.split(':')[0];

    // Direct connection for localhost on the proxy server itself
    if (hostNoPort == "localhost" || hostNoPort == "127.0.0.1") {
        return "DIRECT";
    }

    // Use Privoxy for all traffic
    return "PROXY ${proxy_ip}:8123; DIRECT";
}
EOF

  echo "📄 PAC file generated: $pac_file"
  echo "🌐 Proxy server IP: $proxy_ip:8123"
  echo ""
  echo "🔧 MANUAL PROXY CONFIGURATION:"
  echo "   HTTP Proxy:  $proxy_ip:8123"
  echo "   HTTPS Proxy: $proxy_ip:8123"
  echo "   FTP Proxy:   $proxy_ip:8123"
  echo "   No proxy for: localhost,127.0.0.1"
  echo ""
  echo "💡 AUTOMATIC CONFIGURATION OPTIONS:"
  echo "   Local file:  file://$pac_file"
  echo "   HTTP server: http://$proxy_ip:$PAC_SERVER_PORT/proxy.pac"
  echo ""
  local virsh_ips
  virsh_ips=$(get_virsh_ips)
  if [ -n "$virsh_ips" ]; then
    echo "🖥️  VIRSH/LIBVIRT VM CONFIGURATION:"
    echo "   Use these addresses when configuring proxy inside a VM:"
    for virsh_ip in $virsh_ips; do
      echo "   HTTP Proxy:  $virsh_ip:8123"
      echo "   PAC URL:     http://$virsh_ip:$PAC_SERVER_PORT/proxy.pac"
    done
  fi
}

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

check_privoxy() {
  if ! command -v privoxy >/dev/null 2>&1; then
    echo "❌ Error: privoxy not found in PATH"
    echo ""
    echo "🔧 INSTALLATION REQUIRED:"
    echo ""
    if [ -f "flake.nix" ] || [ -f "flake.lock" ]; then
      echo "📦 Nix users: Run 'nix develop' to enter development environment"
      echo "   Then retry this script"
    else
      echo "🐧 Ubuntu/Debian: sudo apt install privoxy"
      echo "🍎 macOS: brew install privoxy"
      echo "🔴 RHEL/Fedora: sudo dnf install privoxy"
      echo "🐧 Arch: sudo pacman -S privoxy"
    fi
    echo ""
    echo "After installation, retry this script"
    return 1
  fi
  return 0
}

show_logs() {
  local log_file="$PRIVOXY_CACHE_DIR/privoxy.log"

  if [ ! -f "$log_file" ]; then
    echo "❌ Log file not found: $log_file"
    echo "Make sure privoxy is running or has been started at least once."
    return 1
  fi

  echo "📋 Following privoxy logs: $log_file"
  echo "Press Ctrl+C to stop following logs"
  echo ""

  if command -v tspin >/dev/null 2>&1; then
    echo "🌀 Using tailspin to follow logs..."
    tspin "$log_file" --follow
  elif command -v bat >/dev/null 2>&1; then
    echo "🦇 Using bat to follow logs..."
    bat --follow --style=numbers,changes --color=always "$log_file"
  else
    echo "📄 Using tail to follow logs (install 'tailspin' or 'bat' for better formatting)..."
    tail -f "$log_file"
  fi
}

test_pac_local() {
  local url="http://127.0.0.1:$PAC_SERVER_PORT/proxy.pac"
  echo "🧪 Fetching PAC file from localhost: $url"
  echo ""
  if command -v curl >/dev/null 2>&1; then
    curl -sf "$url" && echo "" || echo "❌ Failed to fetch PAC file. Is the PAC server running?"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- "$url" && echo "" || echo "❌ Failed to fetch PAC file. Is the PAC server running?"
  else
    echo "❌ Neither curl nor wget found"
  fi
}

test_pac_vlan() {
  local virsh_ips
  virsh_ips=$(get_virsh_ips)
  if [ -z "$virsh_ips" ]; then
    echo "❌ No virbr* interfaces found. Is libvirt running?"
    return 1
  fi
  for virsh_ip in $virsh_ips; do
    local url="http://$virsh_ip:$PAC_SERVER_PORT/proxy.pac"
    echo "🧪 Fetching PAC file from virsh network ($virsh_ip): $url"
    echo ""
    if command -v curl >/dev/null 2>&1; then
      curl -sf "$url" && echo "" || echo "❌ Failed to fetch PAC file. Is the PAC server running?"
    elif command -v wget >/dev/null 2>&1; then
      wget -qO- "$url" && echo "" || echo "❌ Failed to fetch PAC file. Is the PAC server running?"
    else
      echo "❌ Neither curl nor wget found"
    fi
    echo ""
  done
}

show_help() {
  echo "Usage: $0 {start|stop|restart|status|generate-ca|logs|testpac-local|testpac-vlan|help}"
  echo ""
  echo "Commands:"
  echo "  start          Start privoxy with HTTPS support"
  echo "  stop           Stop privoxy"
  echo "  restart        Restart privoxy"
  echo "  status         Show privoxy status"
  echo "  generate-ca    Generate a new CA certificate for HTTPS interception"
  echo "  logs           Follow privoxy logs (uses bat if available, otherwise tail)"
  echo "  testpac-local  Fetch and display PAC file via localhost"
  echo "  testpac-vlan   Fetch and display PAC file via virsh/libvirt bridge network"
  echo "  help           Show this help message"
  echo ""
  echo "The CA certificate is required for HTTPS interception. After running 'generate-ca',"
  echo "import $PRIVOXY_CA_CERT_FILE into your browser/system to avoid HTTPS warnings."
}

case "$CMD" in
start)
  check_privoxy || exit 1
  generate_ca
  if [ ! -f "$PRIVOXY_CONFIG_FILE" ]; then
    cat >"$PRIVOXY_CONFIG_FILE" <<EOF
listen-address  0.0.0.0:8123
logdir $PRIVOXY_CACHE_DIR
confdir $PRIVOXY_CACHE_DIR
ca-key-file $PRIVOXY_CA_KEY_FILE
ca-cert-file $PRIVOXY_CA_CERT_FILE
logfile privoxy.log
debug   1
debug   1024
EOF
  fi
  open_firewall
  if [ ! -f "$PRIVOXY_PID_FILE" ] || ! kill -0 "$(cat "$PRIVOXY_PID_FILE")" 2>/dev/null; then
    privoxy --pidfile "$PRIVOXY_PID_FILE" "$PRIVOXY_CONFIG_FILE" &
    echo $! >"$PRIVOXY_PID_FILE"
    echo "Started privoxy proxy with HTTPS support on 0.0.0.0:8123 (logdir: $PRIVOXY_CACHE_DIR)"
  else
    echo "Privoxy already running (PID: $(cat "$PRIVOXY_PID_FILE"))"
  fi
  generate_pac
  start_pac_server
  echo ""
  echo "📋 To follow logs: $0 logs"
  ;;
stop)
  if [ -f "$PRIVOXY_PID_FILE" ]; then
    kill "$(cat "$PRIVOXY_PID_FILE")" && rm -f "$PRIVOXY_PID_FILE"
    echo "Stopped privoxy."
  else
    echo "Privoxy is not running."
  fi
  stop_pac_server
  close_firewall
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
logs)
  show_logs
  ;;
testpac-local)
  test_pac_local
  ;;
testpac-vlan)
  test_pac_vlan
  ;;
help | --help | -h)
  show_help
  ;;
*)
  show_help
  exit 1
  ;;
esac
