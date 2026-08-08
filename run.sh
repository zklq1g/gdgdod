#!/bin/bash
echo " Setting up Incident RCA Agent..."

# Check if python3 is available
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
else
    echo " Python is not installed. Please install Python 3.10+ and try again."
    exit 1
fi

if [ ! -d "venv" ]; then
    echo " Creating virtual environment..."
    $PYTHON_CMD -m venv venv
fi

echo " Activating virtual environment..."
source venv/bin/activate

echo " Installing dependencies..."
pip install -r requirements.txt

if [ ! -f ".env" ]; then
    echo " WARNING: .env file not found. Please create one with your GOOGLE_API_KEY."
    echo "Example: GOOGLE_API_KEY=your_actual_api_key_here"
    exit 1
fi

echo " Starting the application..."
streamlit run ui.py
