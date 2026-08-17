import os
import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

app = FastAPI()

GITHUB_MCP_URL = "https://api.githubcopilot.com/mcp/x/all"
GITHUB_PAT = os.environ["GITHUB_PAT"]          # your fine-grained PAT
PROXY_SECRET = os.environ["PROXY_SECRET"]      # random string, acts as the "auth" for this proxy

# Headers that must not be blindly forwarded (either hop-by-hop, or would
# conflict with the ones we set ourselves).
STRIP_HEADERS = {
    "connection", "keep-alive", "transfer-encoding",
    "upgrade", "content-encoding", "content-length", "host",
}

client = httpx.AsyncClient(timeout=httpx.Timeout(300.0))


@app.api_route("/mcp/{secret}", methods=["GET", "POST", "DELETE", "OPTIONS"])
async def proxy(secret: str, request: Request):
    # This is the only "auth" gate — wrong or missing secret in the URL path
    # gets a plain 404 so the endpoint doesn't even reveal it exists.
    if secret != PROXY_SECRET:
        return Response(status_code=404)

    forward_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in STRIP_HEADERS
    }
    forward_headers["authorization"] = f"Bearer {GITHUB_PAT}"

    body = await request.body()

    upstream_request = client.build_request(
        request.method,
        GITHUB_MCP_URL,
        headers=forward_headers,
        content=body,
        params=request.query_params,
    )
    upstream_response = await client.send(upstream_request, stream=True)

    response_headers = {
        k: v for k, v in upstream_response.headers.items()
        if k.lower() not in STRIP_HEADERS
    }

    return StreamingResponse(
        upstream_response.aiter_raw(),
        status_code=upstream_response.status_code,
        headers=response_headers,
        background=BackgroundTask(upstream_response.aclose),
    )


@app.get("/")
async def health():
    # Lets you sanity-check the deploy is alive without exposing anything.
    return {"status": "ok"}
