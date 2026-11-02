import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from interfaces.web_app import app


def compare():
    client = app.test_client()
    res = client.get("/observatory")
    flask_html = res.data.decode("utf-8")

    path = project_root / "interfaces" / "templates" / "observatory.html"
    if not path.exists():
        path = Path("/home/crexs/templates/observatory.html")
    with open(path, "r", encoding="utf-8") as f:
        raw_html = f.read()

    print(f"Raw HTML length: {len(raw_html)}")
    print(f"Flask HTML length: {len(flask_html)}")
    if raw_html == flask_html:
        print("MATCH! No corruption detected.")
    else:
        print("MISMATCH! The output was modified by Jinja rendering.")
        # Print first diff or show where it differs
        for i, (c1, c2) in enumerate(zip(raw_html, flask_html)):
            if c1 != c2:
                print(f"First difference at index {i}:")
                print("Raw context:  ", repr(raw_html[max(0, i - 40) : i + 40]))
                print("Flask context:", repr(flask_html[max(0, i - 40) : i + 40]))
                break


if __name__ == "__main__":
    compare()
