"""Hardened Gateway Middleware for PHI // DRIFT.

Enforces API authentication, rate limiting, request validation, 
concurrency caps, queue timeouts, and structured logging at the ingress layer.
"""

import time
import hmac
import hashlib
import logging
import asyncio
import sqlite3
import json
from pathlib import Path
from typing import Dict, Tuple, Optional
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp

logger = logging.getLogger("drift_gateway")
logger.setLevel(logging.INFO)

# Config Constants
DEFAULT_KEYS_DB = "gateway_keys.db"
MAX_PAYLOAD_BYTES = 512 * 1024  # 512 KB limit to prevent RAM exhaustion
QUEUE_TIMEOUT_SECONDS = 5.0    # Wait at most 5s in the queue before rejecting
GLOBAL_CONCURRENCY_CAP = 3     # Concurrency limit for execution slots

# Tier Definitions
TIERS = {
    "free": {
        "rate": 5 / 60.0,       # 5 requests per minute
        "capacity": 10.0,       # Burst capacity
        "daily_cap": 100
    },
    "pro": {
        "rate": 30 / 60.0,      # 30 requests per minute
        "capacity": 50.0,
        "daily_cap": 1000
    },
    "admin": {
        "rate": 9999.0,         # Effectively unlimited
        "capacity": 9999.0,
        "daily_cap": 999999
    }
}

class TokenBucket:
    def __init__(self, capacity: float, refill_rate: float):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill = time.time()
        self.lock = asyncio.Lock()

    async def acquire(self) -> bool:
        async with self.lock:
            now = time.time()
            elapsed = now - self.last_refill
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            self.last_refill = now
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return True
            return False

class GatewayState:
    """Manages active in-memory buckets, concurrency semaphores, and usage tracking."""
    def __init__(self):
        self.buckets: Dict[str, TokenBucket] = {}
        self.semaphores: Dict[str, asyncio.Semaphore] = {}
        self.daily_usage: Dict[str, Tuple[int, float]] = {}  # key_hash -> (count, day_start_time)
        self.global_sem = asyncio.Semaphore(GLOBAL_CONCURRENCY_CAP)
        self.nonces: Dict[str, float] = {}  # nonce -> expiry_timestamp
        self.nonces_lock = asyncio.Lock()

    async def validate_nonce(self, nonce: str, timestamp: float) -> bool:
        """Checks if a nonce is unique and registers it.
        
        Purges expired nonces. Returns True if valid, False if reused.
        """
        async with self.nonces_lock:
            now = time.time()
            # Clean up expired nonces
            expired = [k for k, v in self.nonces.items() if now > v]
            for k in expired:
                del self.nonces[k]
            
            # Check for reuse
            if nonce in self.nonces:
                return False
                
            # Nonce is valid for 10 seconds past the request timestamp
            self.nonces[nonce] = timestamp + 10.0
            return True

    def get_bucket(self, key_hash: str, tier: str) -> TokenBucket:
        if key_hash not in self.buckets:
            conf = TIERS.get(tier, TIERS["free"])
            self.buckets[key_hash] = TokenBucket(conf["capacity"], conf["rate"])
        return self.buckets[key_hash]

    def increment_daily_usage(self, key_hash: str, daily_cap: int) -> bool:
        now = time.time()
        day_seconds = 24 * 3600
        if key_hash not in self.daily_usage:
            self.daily_usage[key_hash] = (1, now)
            return True
        
        count, day_start = self.daily_usage[key_hash]
        if now - day_start > day_seconds:
            # Reset daily cap
            self.daily_usage[key_hash] = (1, now)
            return True
        
        if count >= daily_cap:
            return False
            
        self.daily_usage[key_hash] = (count + 1, day_start)
        return True

state_manager = GatewayState()

class HardenedGatewayMiddleware:
    def __init__(self, app: ASGIApp, data_dir: Optional[str] = None):
        self.app = app
        
        # Resolve DB path using environment/data dir
        if not data_dir:
            from drift.core.config import DATA_DIR
            data_dir = DATA_DIR if DATA_DIR else "."
        
        self.db_path = Path(data_dir) / DEFAULT_KEYS_DB
        self._init_db()

    def _init_db(self):
        """Creates the SQLite database for API keys."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS keys (
                key_prefix TEXT NOT NULL,
                key_hash TEXT PRIMARY KEY,
                tier TEXT NOT NULL,
                created_at REAL NOT NULL,
                active INTEGER DEFAULT 1
            )
        """)
        conn.commit()
        conn.close()

    def _verify_key(self, raw_key: str) -> Optional[str]:
        """Checks if key is valid and returns its assigned tier."""
        if not raw_key.startswith("drift_live_"):
            return None
            
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT tier FROM keys WHERE key_hash = ? AND active = 1", (key_hash,))
        row = cursor.fetchone()
        conn.close()
        
        return row[0] if row else None

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        path = request.url.path
        method = request.method
        client_ip = request.client.host if request.client else "unknown"

        # 1. Bypass Gateway constraints for Web UI, static files, health check, and module identity check
        if not path.startswith("/api/") or path in ("/api/health", "/api/identity"):
            await self.app(scope, receive, send)
            return

        # Pre-validate payload size via Content-Length header
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_PAYLOAD_BYTES:
                    logger.warning(f"Payload too large from {client_ip} on {path} ({content_length} bytes)")
                    response = JSONResponse(
                        {"error": "Payload Too Large", "message": f"Maximum payload size is {MAX_PAYLOAD_BYTES} bytes."},
                        status_code=413
                    )
                    await response(scope, receive, send)
                    return
            except ValueError:
                response = JSONResponse({"error": "Bad Request", "message": "Invalid Content-Length header."}, status_code=400)
                await response(scope, receive, send)
                return

        # Read and cache body bytes
        try:
            body_bytes = b""
            more_body = True
            while more_body:
                message = await receive()
                if message["type"] == "http.request":
                    body_bytes += message.get("body", b"")
                    more_body = message.get("more_body", False)
                    if len(body_bytes) > MAX_PAYLOAD_BYTES:
                        logger.warning(f"Payload too large from {client_ip} on {path} during stream")
                        response = JSONResponse(
                            {"error": "Payload Too Large", "message": f"Maximum payload size is {MAX_PAYLOAD_BYTES} bytes."},
                            status_code=413
                        )
                        await response(scope, receive, send)
                        return
                elif message["type"] == "http.disconnect":
                    return
        except Exception as e:
            logger.error(f"Failed to read request body: {e}")
            response = JSONResponse({"error": "Bad Request", "message": "Failed to read request body."}, status_code=400)
            await response(scope, receive, send)
            return

        # Setup stateful receive override
        body_read = False
        async def custom_receive():
            nonlocal body_read
            if not body_read:
                body_read = True
                return {"type": "http.request", "body": body_bytes, "more_body": False}
            return await receive()

        # Re-create Request with custom_receive
        request = Request(scope, custom_receive)

        # 1.5. Bidirectional cryptographic verification
        import os
        is_prod = os.environ.get("DRIFT_ENV") == "production"
        has_keys_configured = any(k.startswith("DRIFT_SHARED_KEY") for k in os.environ)
        
        if is_prod or has_keys_configured:
            sig_header = request.headers.get("x-drift-signature")
            ts_header = request.headers.get("x-drift-timestamp")
            key_id_header = request.headers.get("x-drift-key-id", "v1")
            nonce_header = request.headers.get("x-drift-nonce")

            if not sig_header or not ts_header:
                logger.warning(f"Missing signature headers from {client_ip} on {path}")
                response = JSONResponse(
                    {"error": "Unauthorized", "message": "Missing X-Drift-Signature or X-Drift-Timestamp header."},
                    status_code=401
                )
                await response(scope, custom_receive, send)
                return

            # Verify timestamp freshness
            try:
                req_ts = float(ts_header)
            except ValueError:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(ts_header.replace("Z", "+00:00"))
                    req_ts = dt.timestamp()
                except Exception:
                    response = JSONResponse(
                        {"error": "Unauthorized", "message": "Invalid X-Drift-Timestamp format."},
                        status_code=401
                    )
                    await response(scope, custom_receive, send)
                    return

            now = time.time()
            if abs(now - req_ts) > 10.0:
                logger.warning(f"Out of window timestamp from {client_ip} on {path} (diff: {now - req_ts:.2f}s)")
                response = JSONResponse(
                    {"error": "Unauthorized", "message": "Request timestamp is out of the valid window (±10s)."},
                    status_code=401
                )
                await response(scope, custom_receive, send)
                return

            # Validate nonce
            if nonce_header:
                if not await state_manager.validate_nonce(nonce_header, req_ts):
                    logger.warning(f"Replay attack detected (used nonce: {nonce_header}) from {client_ip}")
                    response = JSONResponse(
                        {"error": "Unauthorized", "message": "Replay attack detected: Nonce already used."},
                        status_code=401
                    )
                    await response(scope, custom_receive, send)
                    return

            # Resolve secret key
            env_var_name = f"DRIFT_SHARED_KEY_{key_id_header.upper()}"
            secret_str = os.environ.get(env_var_name)

            if not secret_str and not is_prod:
                secret_str = os.environ.get("DRIFT_SHARED_KEY")

            if not secret_str:
                err_msg = f"CRITICAL: Shared key '{env_var_name}' is missing from environment!"
                if is_prod:
                    raise RuntimeError(err_msg)
                else:
                    logger.error(err_msg)
                    response = JSONResponse(
                        {"error": "Internal Server Error", "message": "Cryptographic key configuration error."},
                        status_code=500
                    )
                    await response(scope, custom_receive, send)
                    return

            secret = secret_str.encode()

            # Compute SHA256 body hash
            body_hash = hashlib.sha256(body_bytes).hexdigest()

            # Build canonical message: METHOD + "\n" + PATH + "\n" + TIMESTAMP + "\n" + BODY_HASH + ("\n" + NONCE if NONCE else "")
            if nonce_header:
                canonical_string = f"{method}\n{path}\n{ts_header}\n{body_hash}\n{nonce_header}"
            else:
                canonical_string = f"{method}\n{path}\n{ts_header}\n{body_hash}"

            # Verify HMAC signature
            expected_sig = hmac.new(secret, canonical_string.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig_header, expected_sig):
                logger.warning(f"Signature mismatch for request {method} {path} from {client_ip}")
                response = JSONResponse(
                    {"error": "Unauthorized", "message": "Invalid cryptographic signature."},
                    status_code=401
                )
                await response(scope, custom_receive, send)
                return

        start_time = time.time()

        # 3. API Key Extraction & Verification
        auth_header = request.headers.get("authorization")
        is_local = client_ip in ("127.0.0.1", "::1", "localhost", "testclient")

        if is_local and (not auth_header or not auth_header.startswith("Bearer ")):
            tier = "admin"
            key_prefix = "local_bypass"
            key_hash = "local_bypass"
        else:
            if not auth_header or not auth_header.startswith("Bearer "):
                logger.info(f"Unauthorized access attempt to {path} from {client_ip}")
                response = JSONResponse({"error": "Unauthorized", "message": "Missing or malformed Authorization header."}, status_code=401)
                await response(scope, custom_receive, send)
                return
            
            raw_key = auth_header.split(" ")[1]
            tier = self._verify_key(raw_key)
            if not tier:
                logger.warning(f"Invalid API key signature from {client_ip} on {path}")
                response = JSONResponse({"error": "Unauthorized", "message": "Invalid or deactivated API key."}, status_code=401)
                await response(scope, custom_receive, send)
                return

            key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
            key_prefix = raw_key[:15]

        # 4. Enforce Token Bucket limits & Daily Caps
        tier_config = TIERS.get(tier, TIERS["free"])
        bucket = state_manager.get_bucket(key_hash, tier)
        
        if not await bucket.acquire():
            logger.warning(f"Rate limit hit on key {key_prefix} ({tier}) from {client_ip} on {path}")
            response = JSONResponse(
                {"error": "Too Many Requests", "message": f"Rate limit exceeded for tier '{tier}'."},
                status_code=429
            )
            await response(scope, custom_receive, send)
            return
            
        if not state_manager.increment_daily_usage(key_hash, tier_config["daily_cap"]):
            logger.warning(f"Daily quota hit on key {key_prefix} ({tier}) from {client_ip}")
            response = JSONResponse(
                {"error": "Too Many Requests", "message": "Daily request quota exceeded."},
                status_code=429
            )
            await response(scope, custom_receive, send)
            return

        # 5. Concurrency Queue & Timeout
        try:
            # Wait up to QUEUE_TIMEOUT_SECONDS to enter the execution slot
            await asyncio.wait_for(
                state_manager.global_sem.acquire(),
                timeout=QUEUE_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            logger.error(f"Concurrency queue timeout reached for key {key_prefix} on {path}")
            response = JSONResponse(
                {"error": "Too Many Requests", "message": "Server concurrency queue full. Please try again later."},
                status_code=429
            )
            await response(scope, custom_receive, send)
            return

        # 6. Execute request and record latency
        response_status = 500
        try:
            captured_status = [500]
            async def wrapped_send(message):
                if message["type"] == "http.response.start":
                    captured_status[0] = message["status"]
                await send(message)

            await self.app(scope, custom_receive, wrapped_send)
            response_status = captured_status[0]
        except Exception as exc:
            logger.error(f"Internal processing failure: {exc}", exc_info=True)
            response = JSONResponse(
                {"error": "Internal Server Error", "message": f"Request processing failed: {type(exc).__name__}"},
                status_code=500
            )
            await response(scope, custom_receive, send)
        finally:
            # Release concurrency slot
            state_manager.global_sem.release()
            
            # Log structured audit line
            duration = time.time() - start_time
            log_data = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "method": method,
                "path": path,
                "client_ip": client_ip,
                "key_prefix": key_prefix,
                "tier": tier,
                "status": response_status,
                "latency_ms": round(duration * 1000.0, 2)
            }
            logger.info(json.dumps(log_data))
