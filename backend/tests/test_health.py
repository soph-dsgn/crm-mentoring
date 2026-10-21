from app.api.routes.health import HealthResponse, health
from app.core.config import Settings
from app.main import create_app


def test_health() -> None:
    settings = Settings(
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        _env_file=None,
    )

    app = create_app(settings)
    health_route = next(route for route in app.routes if route.path == "/health")
    response = health()

    assert "GET" in health_route.methods
    assert health_route.response_model is HealthResponse
    assert response.model_dump() == {"status": "ok"}
