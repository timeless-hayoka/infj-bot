import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from interfaces.web_app import app


def test_routes():
    print("Testing Flask routes rendering...")
    client = app.test_client()

    print("\n1. Requesting /observatory...")
    try:
        res = client.get("/observatory")
        print(f"Status: {res.status_code}")
        if res.status_code != 200:
            print("Response:", res.data.decode("utf-8")[:500])
    except Exception as e:
        print("Crash in /observatory:", e)

    print("\n2. Requesting /glyph...")
    try:
        res = client.get("/glyph")
        print(f"Status: {res.status_code}")
        if res.status_code != 200:
            print("Response:", res.data.decode("utf-8")[:500])
    except Exception as e:
        print("Crash in /glyph:", e)


if __name__ == "__main__":
    test_routes()
