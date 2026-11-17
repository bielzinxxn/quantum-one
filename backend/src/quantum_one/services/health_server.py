"""Servidor HTTP mínimo de saúde para os workers (aiohttp).

GET /health/live  → 200 se o loop está batendo (usado pelo HEALTHCHECK do Docker)
GET /health/ready → 200 se todas as dependências estão OK, senão 503
"""

from __future__ import annotations

from aiohttp import web

from quantum_one.core.health import HealthState


def build_app(state: HealthState, live_timeout_s: float) -> web.Application:
    async def live(_: web.Request) -> web.Response:
        stale = state.seconds_since_tick() > live_timeout_s
        body = {"service": state.service, "alive": not stale}
        return web.json_response(body, status=503 if stale else 200)

    async def ready(_: web.Request) -> web.Response:
        snap = state.snapshot()
        return web.json_response(snap, status=200 if state.ready else 503)

    app = web.Application()
    app.router.add_get("/health/live", live)
    app.router.add_get("/health/ready", ready)
    return app


async def start(app: web.Application, host: str, port: int) -> web.AppRunner:
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, host, port).start()
    return runner
