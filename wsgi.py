"""Entry point for a production server:  gunicorn wsgi:app

Settings come from environment variables (see .env.example and docs/deployment.md).
"""
from sportive import create_app

app = create_app()
