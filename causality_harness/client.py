import requests

def call_drift(url, prompt, state):
    payload = {
        "message": prompt,
        "mode": "engineer",
        "state": state
    }

    r = requests.post(url, json=payload, timeout=60)
    r.raise_for_status()
    # Check if there is an error field
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"API Error: {data['error']}")
    return data.get("reply", "")
