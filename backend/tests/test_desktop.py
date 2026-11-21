"""Desktop (Windows installer) mode: SQLite allowed in production, web app served by the API server."""
from fastapi.testclient import TestClient

from app import store
from app.config import Settings
from app.db import Base
from app.main import create_app


def test_desktop_serves_web_app_and_api(tmp_path):
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<title>Dispensary Desk</title>")
    (web / "assets" / "app.js").write_text("console.log(1)")
    settings = Settings(environment="production", desktop=True, standalone=True, app_role="hospital",
                        jwt_secret="x" * 40, sync_shared_secret="y" * 40, static_dir=str(web),
                        database_url=f"sqlite:///{tmp_path / 'd.db'}")
    app = create_app(settings, start_worker=False)
    Base.metadata.create_all(app.state.engine)
    try:
        c = TestClient(app)
        assert c.get("/api/health").json() == {"status": "ok"}
        assert "Dispensary Desk" in c.get("/").text
        assert "Dispensary Desk" in c.get("/users").text  # client-side route -> index.html
        r = c.get("/assets/app.js")
        assert r.status_code == 200 and "immutable" in r.headers["cache-control"]
        assert c.get("/api/does-not-exist").status_code == 404
        assert "Dispensary Desk" in c.get("/../../etc/passwd").text  # never escapes the web folder
    finally:
        store.set_standalone(False)


def test_sqlite_still_refused_in_production_outside_desktop():
    import pytest
    with pytest.raises(ValueError):
        Settings(environment="production", jwt_secret="x" * 40, sync_shared_secret="y" * 40,
                 database_url="sqlite:///x.db")
