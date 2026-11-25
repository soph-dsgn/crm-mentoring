from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_backend_image_is_rootless_pinned_and_does_not_migrate_on_startup() -> None:
    dockerfile = (REPOSITORY_ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    requirements = (REPOSITORY_ROOT / "backend" / "requirements.lock").read_text(encoding="utf-8")

    assert "python:3.13.17-slim-bookworm@sha256:" in dockerfile
    assert "USER 10001:10001" in dockerfile
    assert '"--workers", "1"' in dockerfile
    assert '"--no-proxy-headers"' in dockerfile
    assert "alembic upgrade" not in dockerfile
    assert all(
        "==" in line for line in requirements.splitlines() if line and not line.startswith("#")
    )


def test_frontend_image_is_reproducible_rootless_static_packaging() -> None:
    dockerfile = (REPOSITORY_ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")
    nginx = (REPOSITORY_ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")

    assert "node:24.12.0-alpine3.23" in dockerfile
    assert "npm ci" in dockerfile
    assert "USER 101:101" in dockerfile
    assert "worker_processes  1;" in dockerfile
    assert "try_files $uri $uri/ /index.html" in nginx
    assert "add_header_inherit merge;" in nginx


def test_handoff_routes_browser_and_api_through_one_https_origin() -> None:
    deploy = REPOSITORY_ROOT / "deploy"
    handoff = (REPOSITORY_ROOT / "docs" / "deployment" / "README.md").read_text(encoding="utf-8")
    env = (deploy / "backend.env.example").read_text(encoding="utf-8")
    proxy = (deploy / "nginx-crm.locations.conf.example").read_text(encoding="utf-8")

    assert "Единый HTTPS origin" in handoff
    assert 'KURATORSKAYA_FRONTEND_ORIGINS=["https://CRM_HOSTNAME"]' in env
    assert 'KURATORSKAYA_PERMITTED_HOSTS=["CRM_HOSTNAME","127.0.0.1"]' in env
    assert "location ^~ /api/" in proxy and "proxy_cache off" in proxy
    assert "location = /health/live" in proxy and "location = /health/ready" in proxy
    assert "location / { proxy_pass http://127.0.0.1:CRM_WEB_PORT;" in proxy
