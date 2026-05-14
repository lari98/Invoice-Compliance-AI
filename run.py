"""
Convenience launcher.

Usage:
    python run.py              # start API server
    python run.py --seed       # seed sample data + start server
    python run.py --seed-only  # seed only, no server
"""

import sys
import subprocess


def seed():
    print("Seeding database with sample invoices...")
    result = subprocess.run([sys.executable, "sample_data/seed_db.py"])
    if result.returncode != 0:
        print("Seed failed. Check logs above.")
        sys.exit(1)
    print("Seed complete.\n")


def start_server():
    print("Starting Swiss Invoice Compliance AI API...")
    print("Docs: http://localhost:8000/docs\n")
    subprocess.run([
        sys.executable, "-m", "uvicorn",
        "app.main:app",
        "--reload",
        "--port", "8000",
        "--host", "0.0.0.0",
    ])


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--seed-only" in args:
        seed()
    elif "--seed" in args:
        seed()
        start_server()
    else:
        start_server()
