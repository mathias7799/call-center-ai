#!/bin/bash
# PJSIP Installation Script for Python 3
# This script builds PJSIP from source and installs Python bindings

set -e  # Exit on error

echo "🚀 PJSIP Installation Script"
echo "============================"
echo ""

# Configuration
PJSIP_VERSION="2.14"
PJSIP_DIR="/tmp/pjproject"
INSTALL_PREFIX="/usr/local"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    warn "Running as root. This is okay but not required."
fi

# 1. Install system dependencies
info "Installing system dependencies..."
if command -v apt-get &> /dev/null; then
    sudo apt-get update
    sudo apt-get install -y \
        build-essential \
        git \
        python3-dev \
        libasound2-dev \
        libssl-dev \
        portaudio19-dev
elif command -v yum &> /dev/null; then
    sudo yum install -y \
        gcc \
        gcc-c++ \
        make \
        git \
        python3-devel \
        alsa-lib-devel \
        openssl-devel \
        portaudio-devel
else
    error "Unsupported package manager. Please install dependencies manually."
fi

info "System dependencies installed ✓"

# 2. Download PJSIP source
info "Downloading PJSIP ${PJSIP_VERSION}..."
if [ -d "$PJSIP_DIR" ]; then
    warn "PJSIP directory exists. Removing..."
    rm -rf "$PJSIP_DIR"
fi

git clone --depth 1 --branch ${PJSIP_VERSION} https://github.com/pjsip/pjproject.git "$PJSIP_DIR"
cd "$PJSIP_DIR"

info "PJSIP source downloaded ✓"

# 3. Configure PJSIP
info "Configuring PJSIP..."
./configure \
    --enable-shared \
    --disable-sound \
    --disable-video \
    --disable-opencore-amr \
    CFLAGS="-O2"

info "PJSIP configured ✓"

# 4. Build PJSIP
info "Building PJSIP (this may take several minutes)..."
make dep
make -j$(nproc)

info "PJSIP built ✓"

# 5. Install PJSIP libraries
info "Installing PJSIP libraries to ${INSTALL_PREFIX}..."
sudo make install
sudo ldconfig

info "PJSIP libraries installed ✓"

# 6. Fix Python bindings for Python 3
info "Fixing Python bindings for Python 3..."
cd pjsip-apps/src/python

# Fix setup.py for Python 3
if [ -f "setup.py" ]; then
    # Convert tabs to spaces
    sed -i 's/\t/    /g' setup.py

    # Fix Python 2 print statements
    sed -i "s/print '/print('/g" setup.py
    sed -i "s/print \"/print(\"/g" setup.py
    sed -i "s/'$/')'/g" setup.py
    sed -i 's/"$/")'/g' setup.py

    info "setup.py fixed for Python 3"
else
    warn "setup.py not found, skipping Python 3 fixes"
fi

# 7. Install Python bindings
info "Installing PJSIP Python bindings..."
if python3 setup.py install 2>&1; then
    info "PJSIP Python bindings installed ✓"
else
    error "Failed to install Python bindings. You may need to fix setup.py manually."
fi

# 8. Test installation
info "Testing PJSIP Python bindings..."
if python3 -c "import pjsua2; print('PJSIP version:', pjsua2.Endpoint.version())" 2>&1; then
    info "✅ PJSIP Python bindings working correctly!"
else
    error "❌ PJSIP Python bindings test failed"
fi

# 9. Cleanup
info "Cleaning up..."
cd /
if [ "$PJSIP_DIR" != "/" ] && [ -d "$PJSIP_DIR" ]; then
    rm -rf "$PJSIP_DIR"
fi

info "Cleanup complete ✓"

echo ""
echo "================================================================"
echo "✅ PJSIP Installation Complete!"
echo "================================================================"
echo ""
echo "You can now use PJSIP in your Python application:"
echo ""
echo "  import pjsua2 as pj"
echo "  endpoint = pj.Endpoint()"
echo "  print(endpoint.version())"
echo ""
echo "Next steps:"
echo "  1. Restart your application"
echo "  2. SIP telephony should now be available"
echo "  3. Check logs for 'PJSIP loaded successfully'"
echo ""
