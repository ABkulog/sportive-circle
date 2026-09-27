"""Run Sportive Circle locally:  python main.py  ->  http://localhost:5050"""
from sportive import create_app

app = create_app({"DEBUG": True})  # local development only

if __name__ == "__main__":
    # Port 5000 is taken by AirPlay on macOS, so use 5050.
    app.run(debug=True, port=5050)
