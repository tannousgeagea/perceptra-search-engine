import os
import time
import importlib
from typing import Callable
from fastapi import Request, Response, APIRouter
from fastapi.routing import APIRoute


QUERIES_DIR = os.path.dirname(__file__) + "/queries"
QUERIES = [
    f"api.routers.auth.queries.{f[:-3]}"
    for f in os.listdir(QUERIES_DIR)
    if f.endswith('.py') and not f.endswith('__.py')
]


class TimedRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            before = time.time()
            response: Response = await original(request)
            response.headers["X-Response-Time"] = str(time.time() - before)
            return response

        return handler


router = APIRouter(
    prefix="/api/v1",
    route_class=TimedRoute,
    tags=["Auth"],
    responses={404: {"description": "Not found"}},
)

for Q in QUERIES:
    module = importlib.import_module(Q)
    router.include_router(module.router)
