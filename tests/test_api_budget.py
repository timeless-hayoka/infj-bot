"""Live API integration tests — require DRIFT web server on 127.0.0.1:8765."""

import asyncio
import json
import os

import pytest
import requests

pytestmark = pytest.mark.env

API_URL = os.environ.get("DRIFT_API_URL", "http://127.0.0.1:8765")
REQUEST_TIMEOUT = float(os.environ.get("DRIFT_API_TEST_TIMEOUT", "5"))


def _require_live_api() -> None:
    if os.environ.get("DRIFT_RUN_ENV_TESTS") != "1":
        pytest.skip("Set DRIFT_RUN_ENV_TESTS=1 and start the API to run live integration tests")


def test_normal_chat():
    _require_live_api()
    print("Testing standard chat endpoint (/api/chat)...")
    resp = requests.post(
        f"{API_URL}/api/chat",
        json={"message": "Hello, Drift. Perform a quick verification cycle."},
        timeout=REQUEST_TIMEOUT,
    )
    print(f"Status code: {resp.status_code}")
    print(f"Response: {resp.json()}")
    assert resp.status_code == 200
    assert "reply" in resp.json()
    print("Standard chat test passed!\n")

def test_streaming_chat():
    _require_live_api()
    print("Testing streaming chat endpoint (/api/chat/stream)...")
    resp = requests.post(
        f"{API_URL}/api/chat/stream",
        json={"message": "Tell me a short 1-sentence joke."},
        stream=True,
        timeout=REQUEST_TIMEOUT,
    )
    print(f"Status code: {resp.status_code}")
    assert resp.status_code == 200
    for line in resp.iter_lines():
        if line:
            decoded = line.decode('utf-8')
            print(f"Stream line: {decoded}")
            if "[DONE]" in decoded:
                break
    print("Streaming chat test passed!\n")

async def test_client_disconnect_stream():
    _require_live_api()
    print("Testing client disconnect on stream (expecting internal cancellation)...")
    host, _, port_str = API_URL.replace("http://", "").replace("https://", "").partition("/")[0].partition(":")
    port = int(port_str or ("443" if API_URL.startswith("https") else "80"))
    reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=REQUEST_TIMEOUT)
    
    payload = json.dumps({"message": "Write a long story about space exploration."})
    req = (
        "POST /api/chat/stream HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "Connection: close\r\n\r\n"
        f"{payload}"
    )
    writer.write(req.encode('utf-8'))
    await writer.drain()
    
    # Read headers
    while True:
        line = await reader.readline()
        if not line or line == b"\r\n":
            break
        print(f"Header: {line.decode('utf-8').strip()}")
        
    # Read a few bytes of chunk/body, then immediately close writer to simulate disconnect
    chunk = await reader.read(100)
    print(f"First chunk snippet: {chunk.decode('utf-8')}")
    
    print("Closing client connection to simulate disconnect...")
    writer.close()
    await writer.wait_closed()
    print("Connection closed. Waiting a moment to let the server process the disconnect.")
    await asyncio.sleep(2)
    print("Client disconnect test run completed.\n")

if __name__ == "__main__":
    test_normal_chat()
    test_streaming_chat()
    asyncio.run(test_client_disconnect_stream())
