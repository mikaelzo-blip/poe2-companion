import http.client
import threading

import pytest

from companion.dashboard_server import DashboardRequestHandler, ThreadingDashboardServer


@pytest.fixture()
def port():
    httpd = ThreadingDashboardServer(("127.0.0.1", 0), DashboardRequestHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def _req(port, method, path, headers=None, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request(method, path, body=body, headers=headers or {})
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, data


def test_index_served(port):
    status, body = _req(port, "GET", "/")
    assert status == 200 and b"<html" in body.lower()


def test_project_files_not_served(port):
    assert _req(port, "GET", "/pyproject.toml")[0] == 404
    assert _req(port, "GET", "/.git/config")[0] == 404


def test_foreign_origin_post_rejected(port):
    status, _ = _req(port, "POST", "/api/equip-item", {"Origin": "http://evil.example", "Content-Length": "2"}, "{}")
    assert status == 403


def test_foreign_host_rejected(port):
    assert _req(port, "GET", "/api/guides", {"Host": "evil.example"})[0] == 403


def test_unknown_api_routes_404(port):
    assert _req(port, "GET", "/api/nope")[0] == 404
    assert _req(port, "POST", "/api/nope", {"Content-Length": "2"}, "{}")[0] == 404


def test_guides_route_dispatches(port):
    status, body = _req(port, "GET", "/api/guides?x=1")
    assert status == 200 and body.startswith((b"{", b"["))
