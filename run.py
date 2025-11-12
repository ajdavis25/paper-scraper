"""
run.py - unified app entrypoint for flask --app run run
"""
import os, sys

# ensure project root is importable
sys.path.append(os.path.dirname(__file__))

from webapp import create_app  # the fully initialized flask app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
