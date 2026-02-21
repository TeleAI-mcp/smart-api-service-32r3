"""Main FastAPI class and utility functions for ASGI applications."""

from typing import (
    Any,
    AsyncContextManager,
    Callable,
    Coroutine,
    Dict,
    List,
    Optional,
    Sequence,
    Type,
    Union,
)
from contextlib import asynccontextmanager
from fastapi import routing
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
    websocket_request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.logger import logger
from fastapi.middleware.asyncexitstack import AsyncExitStackMiddleware
from fastapi.types import DecoratedCallable
from fastapi.utils import generate_unique_id
from starlette.applications import Starlette
from starlette.datastructures import State
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import BaseRoute
from starlette.types import ASGIApp, Receive, Scope, Send
from typing_extensions import Doc, deprecated
import fastapi.utils

class FastAPI(Starlette):
    """
    `FastAPI` class, the main entrypoint to use FastAPI.

    Read more in the
    [FastAPI docs for First Steps](https://fastapi.tiangolo.com/tutorial/first-steps/).
    """

    def __init__(
        self,
        *,
        debug: bool = False,
        routes: Optional[List[BaseRoute]] = None,
        title: str = "FastAPI",
        description: str = "",
        version: str = "0.1.0",
        openapi_url: Optional[str] = "/openapi.json",
        openapi_tags: Optional[List[Dict[str, Any]]] = None,
        servers: Optional[List[Dict[str, Union[str, Any]]]] = None,
        dependencies: Optional[Sequence[Any]] = None,
        default_response_class: Type[Response] = JSONResponse,
        docs_url: Optional[str] = "/docs",
        redoc_url: Optional[str] = "/redoc",
        swagger_ui_oauth2_redirect_url: str = "/docs/oauth2-redirect",
        swagger_ui_init_oauth: Optional[Dict[str, Any]] = None,
        middleware: Optional[Sequence[Middleware]] = None,
        exception_handlers: Optional[
            Dict[
                Union[int, Type[Exception]],
                Callable[[Request, Any], Coroutine[Any, Any, Response]],
            ]
        ] = None,
        on_startup: Optional[Sequence[Callable[[], Any]]] = None,
        on_shutdown: Optional[Sequence[Callable[[], Any]]] = None,
        lifespan: Optional[
            Callable[["FastAPI"], AsyncContextManager[Any]]
        ] = None,
        terms_of_service: Optional[str] = None,
        contact: Optional[Dict[str, Union[str, Any]]] = None,
        license_info: Optional[Dict[str, Union[str, Any]]] = None,
        openapi_prefix: str = "",
        root_path: str = "",
        root_path_in_servers: bool = True,
        responses: Optional[Dict[Union[int, str], Dict[str, Any]]] = None,
        callbacks: Optional[List[BaseRoute]] = None,
        webhooks: Optional[routing.APIRouter] = None,
        deprecated: Optional[bool] = None,
        include_in_schema: bool = True,
        swagger_ui_parameters: Optional[Dict[str, Any]] = None,
        generate_unique_id_function: Callable[[routing.APIRoute], str] = Default(
            generate_unique_id
        ),
        separate_input_output_schemas: bool = True,
        **extra: Any,
    ) -> None:
        self.debug = debug
        self.title = title
        self.description = description
        self.version = version
        self.terms_of_service = terms_of_service
        self.contact = contact
        self.license_info = license_info
        self.openapi_url = openapi_url
        self.openapi_tags = openapi_tags
        self.servers = servers
        self.separate_input_output_schemas = separate_input_output_schemas
        self.extra = extra
        self.openapi_version = "3.1.0"
        self.openapi_schema: Optional[Dict[str, Any]] = None
        if self.openapi_url:
            assert self.title, "A title must be provided for OpenAPI, e.g.: 'My API'"
            assert self.version, "A version must be provided for OpenAPI, e.g.: '2.1.0'"
        self.webhooks = webhooks or routing.APIRouter()
        self.webhooks_route_class = routing.APIRoute
        self.state: State = State()
        self.dependency_overrides: Dict[Callable[..., Any], Callable[..., Any]] = {}
        self.router: routing.APIRouter = routing.APIRouter(
            routes=routes,
            dependency_overrides_provider=self,
            on_startup=on_startup,
            on_shutdown=on_shutdown,
            lifespan=lifespan,
            default_response_class=default_response_class,
            dependencies=dependencies,
            callbacks=callbacks,
            deprecated=deprecated,
            include_in_schema=include_in_schema,
            responses=responses,
            generate_unique_id_function=generate_unique_id_function,
        )
        self.exception_handlers: Dict[
            Any, Callable[[Request, Any], Coroutine[Any, Any, Response]]
        ] = {} if exception_handlers is None else dict(exception_handlers)
        self.exception_handlers.setdefault(HTTPException, http_exception_handler)
        self.exception_handlers.setdefault(
            RequestValidationError, request_validation_exception_handler
        )
        self.exception_handlers.setdefault(
            routing.WebSocketRequestValidationError,
            websocket_request_validation_exception_handler,
        )

        self.user_middleware: List[Middleware] = (
            [] if middleware is None else list(middleware)
        )
        self.middleware_stack: Optional[ASGIApp] = None
        self.setup()

        self.docs_url = docs_url
        self.redoc_url = redoc_url
        self.swagger_ui_oauth2_redirect_url = swagger_ui_oauth2_redirect_url
        self.swagger_ui_init_oauth = swagger_ui_init_oauth
        self.swagger_ui_parameters = swagger_ui_parameters
        self.root_path = root_path
        self.root_path_in_servers = root_path_in_servers
        self.openapi_prefix = openapi_prefix.rstrip("/")
        if self.openapi_url:
            self.add_route(
                self.openapi_prefix + self.openapi_url,
                self.openapi,
                include_in_schema=False,
            )
        if self.openapi_url and self.docs_url:
            self.add_route(
                self.docs_url,
                self.docs,
                include_in_schema=False,
            )
            self.add_route(
                self.swagger_ui_oauth2_redirect_url,
                self.swagger_ui_redirect,
                include_in_schema=False,
            )
        if self.openapi_url and self.redoc_url:
            self.add_route(
                self.redoc_url,
                self.redoc,
                include_in_schema=False,
            )