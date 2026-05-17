import io, pytest
from fastapi.testclient import TestClient


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_root(client):
    r = client.get("/")
    assert r.status_code == 200
    # Root now serves dashboard.html (HTML) or JSON fallback — accept either
    ct = r.headers.get("content-type", "")
    if "text/html" in ct:
        assert len(r.content) > 0   # non-empty HTML response
    else:
        assert "docs" in r.json()   # JSON fallback


def test_api_info(client):
    r = client.get("/api")
    assert r.status_code == 200
    assert "docs" in r.json()


class TestUpload:
    def test_upload_201(self, client):
        r = client.post("/invoices/upload", files={"file": ("inv.pdf", io.BytesIO(b"RECHNUNG"), "application/pdf")})
        assert r.status_code == 201

    def test_upload_returns_id(self, client):
        r = client.post("/invoices/upload", files={"file": ("inv.pdf", io.BytesIO(b"data"), "application/pdf")})
        assert "invoice_id" in r.json()

    def test_bad_extension(self, client):
        r = client.post("/invoices/upload", files={"file": ("inv.docx", io.BytesIO(b"data"), "application/msword")})
        assert r.status_code == 400

    def test_png_accepted(self, client):
        r = client.post("/invoices/upload", files={"file": ("inv.png", io.BytesIO(b"data"), "image/png")})
        assert r.status_code == 201


@pytest.fixture
def inv_id(client):
    r = client.post("/invoices/upload", files={"file": ("t.pdf", io.BytesIO(b"RECHNUNG INV-001"), "application/pdf")})
    return r.json()["invoice_id"]


class TestInvoiceEndpoints:
    def test_list_empty(self, client):
        assert client.get("/invoices/").status_code == 200

    def test_list_has_invoice(self, client, inv_id):
        ids = [i["id"] for i in client.get("/invoices/").json()]
        assert inv_id in ids

    def test_get_detail(self, client, inv_id):
        r = client.get(f"/invoices/{inv_id}")
        assert r.status_code == 200
        d = r.json()
        assert "compliance_results" in d
        assert "line_items" in d

    def test_404(self, client):
        assert client.get("/invoices/99999").status_code == 404

    def test_raw_text(self, client, inv_id):
        r = client.get(f"/invoices/{inv_id}/raw")
        assert r.status_code == 200
        assert "raw_text" in r.json()

    def test_delete(self, client, inv_id):
        assert client.delete(f"/invoices/{inv_id}").status_code == 204
        assert client.get(f"/invoices/{inv_id}").status_code == 404

    def test_pagination(self, client):
        assert client.get("/invoices/?skip=0&limit=10").status_code == 200

    def test_limit_too_high(self, client):
        assert client.get("/invoices/?limit=500").status_code == 422


class TestComplianceEndpoints:
    def test_summary(self, client, inv_id):
        r = client.get(f"/compliance/{inv_id}")
        assert r.status_code == 200
        d = r.json()
        assert all(k in d for k in ["overall_status","total_checks","passed","warnings","failed","results"])

    def test_overview(self, client, inv_id):
        r = client.get("/compliance/stats/overview")
        assert r.status_code == 200
        assert "compliance_breakdown" in r.json()

    def test_404(self, client):
        assert client.get("/compliance/99999").status_code == 404


class TestDashboard:
    def test_stats(self, client):
        r = client.get("/dashboard/stats")
        assert r.status_code == 200
        assert "total_invoices" in r.json()

    def test_vendors(self, client):
        assert client.get("/dashboard/vendors").status_code == 200
