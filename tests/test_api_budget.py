import asyncio
import json
import socket

import pytest
import requests

API_URL = "http://127.0.0.1:8765"


def _server_reachable() -> bool:
    try:
        s = socket.create_connection(("127.0.0.1", 8765), timeout=1)
        s.close()
        return True
    except OSError:
        return False


requires_server = pytest.mark.skipif(
    not _server_reachable(), reason="DRIFT API server not running on port 8765"
)


@requires_server
def test_normal_chat():
    print("Testing standard chat endpoint (/api/chat)...")
    resp = requests.post(
        f"{API_URL}/api/chat",
        json={"message": "Hello, Drift. Perform a quick verification cycle."},
    )
    print(f"Status code: {resp.status_code}")
    print(f"Response: {resp.json()}")
    assert resp.status_code == 200
    assert "reply" in resp.json()
    print("Standard chat test passed!\n")


@requires_server
def test_streaming_chat():
    print("Testing streaming chat endpoint (/api/chat/stream)...")
    resp = requests.post(
        f"{API_URL}/api/chat/stream",
        json={"message": "Tell me a short 1-sentence joke."},
        stream=True,
    )
    print(f"Status code: {resp.status_code}")
    assert resp.status_code == 200
    for line in resp.iter_lines():
        if line:
            decoded = line.decode("utf-8")
            print(f"Stream line: {decoded}")
            if "[DONE]" in decoded:
                break
    print("Streaming chat test passed!\n")


@requires_server
@pytest.mark.asyncio
async def test_client_disconnect_stream():
    print("Testing client disconnect on stream (expecting internal cancellation)...")
    reader, writer = await asyncio.open_connection("127.0.0.1", 8765)

    payload = json.dumps({"message": "Write a long story about space exploration."})
    req = (
        "POST /api/chat/stream HTTP/1.1\r\n"
        "Host: 127.0.0.1:8765\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "Connection: close\r\n\r\n"
        f"{payload}"
    )
    writer.write(req.encode("utf-8"))
    await writer.drain()

    while True:
        line = await reader.readline()
        if not line or line == b"\r\n":
            break
        print(f"Header: {line.decode('utf-8').strip()}")

    chunk = await reader.read(100)
    print(f"First chunk snippet: {chunk.decode('utf-8')}")

    print("Closing client connection to simulate disconnect...")
    writer.close()
    await writer.wait_closed()
    print(
        "Connection closed. Waiting a moment to let the server process the disconnect."
    )
    await asyncio.sleep(2)
    print("Client disconnect test run completed.\n")


if __name__ == "__main__":
    test_normal_chat()
    test_streaming_chat()
    asyncio.run(test_client_disconnect_stream())
