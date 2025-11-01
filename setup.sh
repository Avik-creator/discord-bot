#!/bin/bash
# Setup script for Football Card Discord Bot

echo "========================================"
echo "Football Card Discord Bot - Setup"
echo "========================================"
echo ""

# Check Python version
echo "Checking Python version..."
python3 --version

if [ $? -ne 0 ]; then
    echo "❌ Python 3 is not installed!"
    exit 1
fi

# Create virtual environment
echo ""
echo "Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Copy .env.example if .env doesn't exist
if [ ! -f .env ]; then
    echo ""
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "✅ .env file created. Please edit it with your credentials."
else
    echo ""
    echo "⚠️  .env file already exists. Skipping..."
fi

echo ""
echo "========================================"
echo "Setup Complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your credentials"
echo "2. Ensure PostgreSQL is running"
echo "3. Run: python populate_db.py"
echo "4. Run: python bot.py"
echo ""
echo "Or simply run: ./run.sh"
echo "========================================"

