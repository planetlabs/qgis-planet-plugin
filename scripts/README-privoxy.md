# Privoxy Proxy Setup

This directory contains a script to set up and manage a Privoxy proxy server with automatic PAC file generation.

## Requirements

### Ubuntu/Linux
- `privoxy` package
- `openssl` (usually pre-installed)
- `iptables` (for firewall management)

Install privoxy:
```bash
sudo apt update
sudo apt install privoxy
```

### Windows
- Download and install Privoxy from: https://www.privoxy.org/user-manual/installation.html
- Or use WSL with Ubuntu setup above

## Usage

### Starting the Proxy

```bash
# Start privoxy proxy server and generate PAC file
./privoxy.sh start
```

This will:
- Generate a CA certificate for HTTPS interception
- Create privoxy configuration
- Open firewall port 8123 (with security warning)
- Start the proxy server on `0.0.0.0:8123`
- Generate a PAC file at `proxy.pac`

### Other Commands

```bash
# Stop the proxy server
./privoxy.sh stop

# Restart the proxy server
./privoxy.sh restart

# Check proxy status
./privoxy.sh status

# Generate new CA certificate
./privoxy.sh generate-ca

# Show help
./privoxy.sh help
```

## Browser Configuration

### Ubuntu

#### Firefox
1. Open Firefox preferences
2. Go to "General" → "Network Settings" → "Settings..."
3. Select "Automatic proxy configuration URL"
4. Enter: `file:///path/to/your/project/proxy.pac`
5. Click "OK"

#### Chrome/Chromium
```bash
# Start Chrome with PAC file
google-chrome --proxy-pac-url=file:///path/to/your/project/proxy.pac

# Or configure in settings:
# Settings → Advanced → System → Open proxy settings
# Use automatic configuration script: file:///path/to/your/project/proxy.pac
```

#### System-wide (Ubuntu)
```bash
# Set system proxy via GUI
gnome-control-center network

# Or via command line
gsettings set org.gnome.system.proxy mode 'auto'
gsettings set org.gnome.system.proxy autoconfig-url 'file:///path/to/your/project/proxy.pac'
```

### Windows

#### Internet Explorer/Edge
1. Open Internet Options
2. Go to "Connections" → "LAN Settings"
3. Check "Use automatic configuration script"
4. Enter: `file:///C:/path/to/your/project/proxy.pac`
5. Click "OK"

#### Chrome
1. Open Chrome settings
2. Advanced → System → "Open your computer's proxy settings"
3. In "Automatic proxy setup":
   - Turn on "Use setup script"
   - Script address: `file:///C:/path/to/your/project/proxy.pac`

#### Firefox
1. Open Firefox preferences
2. General → Network Settings → Settings...
3. Select "Automatic proxy configuration URL"
4. Enter: `file:///C:/path/to/your/project/proxy.pac`

## Testing from a Virsh/Libvirt VM

When testing the proxy from a virtual machine managed by libvirt/virsh, the script
automatically detects `virbr*` bridge interfaces and displays the corresponding
PAC and proxy addresses alongside the primary network address.

When you run `./privoxy.sh start` on the host, the output will include a
**VIRSH/LIBVIRT VM CONFIGURATION** section if any `virbr*` interfaces are found.
Use those addresses when configuring the proxy inside your VM (typically
`192.168.122.1` for the default libvirt network).

### VM Proxy Configuration (QGIS)

Inside the VM, configure QGIS proxy settings:
1. Go to **Settings > Options > Network**
2. Set proxy type to **DefaultProxy** or **HttpProxy**
3. Enter the virsh bridge IP shown by the script (e.g. `192.168.122.1`) as the host
4. Set port to `8123`

Or use the PAC URL shown in the script output as the automatic configuration URL.

## HTTPS Certificate Setup

For HTTPS traffic inspection, you need to install the generated CA certificate:

### Ubuntu
```bash
# Copy the certificate
sudo cp .privoxy-cache/ca-cert.pem /usr/local/share/ca-certificates/privoxy-ca.crt

# Update certificate store
sudo update-ca-certificates

# For Firefox specifically
# 1. Open Firefox → Preferences → Privacy & Security
# 2. Certificates → View Certificates → Authorities → Import
# 3. Select .privoxy-cache/ca-cert.pem
# 4. Check "Trust this CA to identify websites"
```

### Windows
1. Double-click on `.privoxy-cache/ca-cert.pem`
2. Click "Install Certificate..."
3. Choose "Local Machine" → "Next"
4. Select "Place all certificates in the following store"
5. Click "Browse" → Select "Trusted Root Certification Authorities"
6. Click "Next" → "Finish"

## Security Notes

⚠️ **IMPORTANT SECURITY WARNINGS:**

1. **Firewall Access**: The script opens port 8123 to the network, making your proxy accessible to other devices. This is a security risk.

2. **CA Certificate**: Installing the CA certificate allows the proxy to intercept HTTPS traffic. Only install on machines you control.

3. **Network Exposure**: The proxy listens on `0.0.0.0:8123`, making it accessible from any network interface.

## Troubleshooting

### Common Issues

1. **Permission denied**: Run with `sudo` if needed for firewall operations
2. **Port already in use**: Check if privoxy is already running: `sudo netstat -tlnp | grep 8123`
3. **PAC file not working**: Ensure the file path is correct and accessible to your browser
4. **HTTPS warnings**: Install the CA certificate as described above

### Logs
Check privoxy logs in `.privoxy-cache/privoxy.log` for debugging.

### Manual Proxy Configuration
If PAC file doesn't work, manually configure your browser to use:
- HTTP Proxy: `[your-ip]:8123`
- HTTPS Proxy: `[your-ip]:8123`

Your IP address is shown when starting the proxy server.
