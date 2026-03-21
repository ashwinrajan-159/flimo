import time
import logging
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from collections import defaultdict

logger = logging.getLogger(__name__)

# Simple in-memory metrics
METRICS = {
    "total_requests": 0,
    "total_errors": 0,
    "latency_sum": 0.0,
    "endpoints": defaultdict(int)
}

class MonitoringMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        try:
            response = await call_next(request)
            
            # Update metrics
            process_time = time.time() - start_time
            METRICS["total_requests"] += 1
            METRICS["latency_sum"] += process_time
            METRICS["endpoints"][request.url.path] += 1
            
            # Log slow requests (> 1s)
            if process_time > 1.0:
                logger.warning(f"Slow request: {request.method} {request.url.path} took {process_time:.4f}s")
                
            return response
            
        except Exception as e:
            METRICS["total_errors"] += 1
            logger.error(f"Request failed: {request.method} {request.url.path} - {e}")
            raise e

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Simple Token Bucket / Fixed Window Rate Limiter.
    Soft limit: 60 req/min per IP.
    """
    def __init__(self, app, limit=60, window=60):
        super().__init__(app)
        self.limit = limit
        self.window = window
        self.clients = defaultdict(list) # IP -> [timestamps]

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host
        now = time.time()
        
        # Clean up old timestamps
        self.clients[client_ip] = [t for t in self.clients[client_ip] if now - t < self.window]
        
        if len(self.clients[client_ip]) >= self.limit:
             logger.warning(f"Rate limit exceeded for {client_ip}")
             return Response("Too Many Requests", status_code=429)
             
        self.clients[client_ip].append(now)
        return await call_next(request)
