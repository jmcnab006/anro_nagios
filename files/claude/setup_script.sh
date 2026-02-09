#!/bin/bash
# Nagios Manager Setup Script
# Version: 3.0

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default paths for Ubuntu nagios4 package
INSTALL_DIR="/usr/local/bin"
CONFIG_DIR="/etc/nagios-manager"
LOG_DIR="/var/log"
NAGIOS_DIR="/etc/nagios4"
BACKUP_DIR="/var/backups/nagios4"

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root for system-wide installation"
        log_info "Run with: sudo $0"
        exit 1
    fi
}

check_python() {
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is required but not installed"
        exit 1
    fi

    PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    log_info "Found Python $PYTHON_VERSION"

    if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 7) else 1)"; then
        log_error "Python 3.7 or higher is required"
        exit 1
    fi
}

check_nagios() {
    local nagios_paths=(
        "/etc/nagios4"
        "/etc/nagios3"
        "/etc/nagios"
        "/usr/local/nagios"
        "/opt/nagios"
    )

    for path in "${nagios_paths[@]}"; do
        if [[ -d "$path" ]]; then
            NAGIOS_DIR="$path"
            log_info "Found Nagios installation at: $NAGIOS_DIR"

            # Update backup dir based on nagios dir
            if [[ "$path" == "/etc/nagios4" ]]; then
                BACKUP_DIR="/var/backups/nagios4"
            elif [[ "$path" == "/etc/nagios3" ]]; then
                BACKUP_DIR="/var/backups/nagios3"
            else
                BACKUP_DIR="$path/backups"
            fi

            return 0
        fi
    done

    log_warning "Nagios installation not found in standard locations"
    log_info "You can specify the path during configuration"
    return 1
}

create_directories() {
    log_info "Creating directories..."

    mkdir -p "$CONFIG_DIR"
    mkdir -p "$BACKUP_DIR"

    # Create templates directory if it doesn't exist
    if [[ -d "$NAGIOS_DIR" ]]; then
        mkdir -p "$NAGIOS_DIR/templates"
        mkdir -p "$NAGIOS_DIR/conf.d/hosts"
        mkdir -p "$NAGIOS_DIR/conf.d/services"
        mkdir -p "$NAGIOS_DIR/conf.d/commands"
        mkdir -p "$NAGIOS_DIR/conf.d/contacts"
    fi

    # Set appropriate permissions
    chmod 755 "$CONFIG_DIR"
    chmod 755 "$BACKUP_DIR"

    # Set nagios ownership for Ubuntu package paths
    if [[ -d "$NAGIOS_DIR" ]]; then
        chown -R nagios:nagios "$BACKUP_DIR" 2>/dev/null || true
        chown -R nagios:nagios "$NAGIOS_DIR/templates" 2>/dev/null || true
        chown -R nagios:nagios "$NAGIOS_DIR/conf.d" 2>/dev/null || true
    fi

    log_success "Directories created"
}

install_files() {
    log_info "Installing Nagios Manager files..."

    # Install Python modules
    if [[ -f "$SCRIPT_DIR/nagios_manager.py" ]]; then
        cp "$SCRIPT_DIR/nagios_manager.py" "$INSTALL_DIR/"
        chmod 755 "$INSTALL_DIR/nagios_manager.py"
        log_success "Installed nagios_manager.py"
    else
        log_error "nagios_manager.py not found in $SCRIPT_DIR"
        exit 1
    fi

    # Install CLI script
    if [[ -f "$SCRIPT_DIR/nagios-cli" ]]; then
        cp "$SCRIPT_DIR/nagios-cli" "$INSTALL_DIR/nagios-cli"
        chmod 755 "$INSTALL_DIR/nagios-cli"
        log_success "Installed nagios-cli"
    else
        log_error "nagios-cli not found in $SCRIPT_DIR"
        exit 1
    fi

    # Install configuration template
    if [[ -f "$SCRIPT_DIR/config.yaml" ]]; then
        cp "$SCRIPT_DIR/config.yaml" "$CONFIG_DIR/config.yaml.template"
        if [[ ! -f "$CONFIG_DIR/config.yaml" ]]; then
            cp "$SCRIPT_DIR/config.yaml" "$CONFIG_DIR/config.yaml"
            log_success "Installed configuration files"
        else
            log_info "Configuration file already exists, created template only"
        fi
    fi
}

configure_logging() {
    log_info "Setting up logging..."

    # Create log rotation configuration
    cat > /etc/logrotate.d/nagios-manager << 'EOF'
/var/log/nagios-manager.log {
    weekly
    missingok
    rotate 4
    compress
    notifempty
    create 644 nagios nagios
    postrotate
        # Signal the application if needed
    endscript
}
EOF

    # Create initial log file
    touch /var/log/nagios-manager.log
    chown nagios:nagios /var/log/nagios-manager.log 2>/dev/null || true
    chmod 644 /var/log/nagios-manager.log

    log_success "Logging configured"
}

create_systemd_service() {
    log_info "Creating systemd service file..."

    cat > /etc/systemd/system/nagios-manager.service << EOF
[Unit]
Description=Nagios Configuration Manager Daemon
After=network.target nagios4.service
Requires=nagios4.service

[Service]
Type=notify
User=nagios
Group=nagios
ExecStart=$INSTALL_DIR/nagios-cli daemon
ExecReload=/bin/kill -HUP \$MAINPID
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=nagios-manager

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    log_success "Systemd service created"
}

setup_bash_completion() {
    log_info "Setting up bash completion..."

    cat > /etc/bash_completion.d/nagios-cli << 'EOF'
# Nagios CLI bash completion

_nagios_cli() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    # Main commands
    opts="host service command backup validate reload"

    case "${prev}" in
        nagios-cli)
            COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
            return 0
            ;;
        host)
            COMPREPLY=( $(compgen -W "create delete show list" -- ${cur}) )
            return 0
            ;;
        service)
            COMPREPLY=( $(compgen -W "create delete show list" -- ${cur}) )
            return 0
            ;;
        command)
            COMPREPLY=( $(compgen -W "create delete show list" -- ${cur}) )
            return 0
            ;;
        backup)
            COMPREPLY=( $(compgen -W "create list restore" -- ${cur}) )
            return 0
            ;;
    esac
}

complete -F _nagios_cli nagios-cli
EOF

    log_success "Bash completion configured"
}

install_python_dependencies() {
    log_info "Installing Python dependencies..."

    # Check if pip is available
    if command -v pip3 &> /dev/null; then
        pip3 install PyYAML pathlib2 2>/dev/null || log_warning "Failed to install some Python packages"
        log_success "Python dependencies installed"
    else
        log_warning "pip3 not found, you may need to install PyYAML manually"
    fi
}

verify_installation() {
    log_info "Verifying installation..."

    # Check if files exist
    local files=(
        "$INSTALL_DIR/nagios_manager.py"
        "$INSTALL_DIR/nagios-cli"
        "$CONFIG_DIR/config.yaml"
    )

    for file in "${files[@]}"; do
        if [[ ! -f "$file" ]]; then
            log_error "Missing file: $file"
            return 1
        fi
    done

    # Test CLI
    if "$INSTALL_DIR/nagios-cli" --help &>/dev/null; then
        log_success "CLI is working"
    else
        log_error "CLI test failed"
        return 1
    fi

    log_success "Installation verified"
}

configure_nagios_integration() {
    log_info "Configuring Nagios integration..."

    # Check if nagios user exists (should exist with Ubuntu package)
    if ! id "nagios" &>/dev/null; then
        log_warning "Nagios user not found. Please install nagios4 package first:"
        log_info "  sudo apt update"
        log_info "  sudo apt install nagios4"
        return 1
    fi

    # Add current user to nagios group
    if [[ -n "$SUDO_USER" ]]; then
        usermod -a -G nagios "$SUDO_USER" 2>/dev/null || log_warning "Failed to add user to nagios group"
        log_info "Added $SUDO_USER to nagios group (logout/login required)"
    fi

    # Set up sudo rules for nagios reload (Ubuntu uses nagios4 service name)
    cat > /etc/sudoers.d/nagios-manager << 'EOF'
# Allow nagios user to reload nagios service
nagios ALL=(ALL) NOPASSWD: /bin/systemctl reload nagios4
nagios ALL=(ALL) NOPASSWD: /bin/systemctl restart nagios4
nagios ALL=(ALL) NOPASSWD: /bin/systemctl status nagios4

# Support for older nagios service name
nagios ALL=(ALL) NOPASSWD: /bin/systemctl reload nagios
nagios ALL=(ALL) NOPASSWD: /bin/systemctl restart nagios
nagios ALL=(ALL) NOPASSWD: /bin/systemctl status nagios

# Allow nagios group members to use nagios-cli
%nagios ALL=(nagios) NOPASSWD: /usr/local/bin/nagios-cli
EOF

    log_success "Nagios integration configured"
}

show_post_install_info() {
    log_success "Nagios Manager installation completed!"
    echo
    echo "Installation Summary:"
    echo "- CLI tool: $INSTALL_DIR/nagios-cli"
    echo "- Configuration: $CONFIG_DIR/config.yaml"
    echo "- Logs: /var/log/nagios-manager.log"
    echo "- Backups: $BACKUP_DIR"
    echo
    echo "Prerequisites:"
    echo "1. Install nagios4 if not already installed:"
    echo "   sudo apt update"
    echo "   sudo apt install nagios4"
    echo
    echo "Next steps:"
    echo "1. Edit $CONFIG_DIR/config.yaml to match your Nagios setup"
    echo "2. Test the installation: nagios-cli validate"
    echo "3. Create your first host: nagios-cli host create test-host 192.168.1.100"
    echo "4. View help: nagios-cli --help"
    echo
    echo "Ubuntu nagios4 package structure:"
    echo "- Config: /etc/nagios4/nagios.cfg"
    echo "- Objects: /etc/nagios4/conf.d/"
    echo "- Plugins: /usr/lib/nagios/plugins/"
    echo "- Web interface: http://localhost/nagios4/"
    echo
    echo "For bash completion, logout and login again, or run:"
    echo "source /etc/bash_completion.d/nagios-cli"
    echo
}

main() {
    echo "Nagios Manager Setup Script v3.0"
    echo "=================================="
    echo

    # Parse command line arguments
    SKIP_ROOT_CHECK=false
    USER_INSTALL=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --user)
                USER_INSTALL=true
                SKIP_ROOT_CHECK=true
                INSTALL_DIR="$HOME/.local/bin"
                CONFIG_DIR="$HOME/.config/nagios-manager"
                shift
                ;;
            --nagios-dir)
                NAGIOS_DIR="$2"
                shift 2
                ;;
            --skip-root-check)
                SKIP_ROOT_CHECK=true
                shift
                ;;
            -h|--help)
                echo "Usage: $0 [OPTIONS]"
                echo "Options:"
                echo "  --user              Install for current user only"
                echo "  --nagios-dir DIR    Specify Nagios installation directory"
                echo "  --skip-root-check   Skip root user check"
                echo "  -h, --help          Show this help message"
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done

    # Checks
    if [[ "$SKIP_ROOT_CHECK" != "true" ]]; then
        check_root
    fi

    check_python
    check_nagios

    # Installation steps
    if [[ "$USER_INSTALL" == "true" ]]; then
        log_info "Installing for current user only..."
        mkdir -p "$INSTALL_DIR" "$CONFIG_DIR"
    else
        create_directories
        configure_nagios_integration
        create_systemd_service
        setup_bash_completion
        configure_logging
    fi

    install_python_dependencies
    install_files
    verify_installation
    show_post_install_info

    echo "Setup completed successfully!"
}

# Run main function
main "$@"