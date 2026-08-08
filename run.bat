@echo off
echo  Setting up Incident RCA Agent...

if not exist "venv" (
    echo  Creating virtual environment...
    python -m venv venv
)

echo  Activating virtual environment...
call venv\Scripts\activate.bat

echo  Installing dependencies...
pip install -r requirements.txt

if not exist ".env" (
    echo  WARNING: .env file not found. Please create one with your GOOGLE_API_KEY.
    echo Example: GOOGLE_API_KEY=your_actual_api_key_here
    pause
    exit /b 1
)

echo  Starting the application...
streamlit run ui.py
pause
