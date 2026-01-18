#!/bin/bash
echo "Installing missing packages..."

# Java
echo "Installing Java 17..."
sudo apt install -y openjdk-17-jre

# AWS CLI
echo "Installing AWS CLI..."
if ! command -v aws &>/dev/null; then
    curl -s "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
    cd /tmp
    unzip -q awscliv2.zip
    sudo ./aws/install >/dev/null 2>&1
    rm -f awscliv2.zip
    cd -
fi

# Python packages
echo "Installing Python packages..."
cd /home/x/Code/sam-project
source venv/bin/activate
pip install beautifulsoup4 python-docx >/dev/null 2>&1

echo "Verifying..."
java -version 2>&1 | grep -q "17" && echo "✓ Java 17 installed" || echo "✗ Java not installed"
command -v aws && echo "✓ AWS CLI installed" || echo "✗ AWS CLI not installed"
python3 -c "import beautifulsoup4, docx" 2>/dev/null && echo "✓ Python packages installed" || echo "✗ Python packages not installed"
