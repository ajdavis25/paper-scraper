"""
astro-ph digest package initializer.
ensures dotenv is loaded early for all modules.
"""
from dotenv import load_dotenv
import os

# always load from project root, even if flask runs from /webapp
root_dir = os.path.abspath(os.path.dirname(__file__))
env_path = os.path.join(root_dir, ".env")

if os.path.exists(env_path):
    load_dotenv(dotenv_path=env_path)
    print(f"[dotenv] loaded from {env_path}")
else:
    print(f"[dotenv] no .env found at {env_path}")
