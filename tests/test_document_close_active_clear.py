import sys
import types
from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException
from types import SimpleNamespace

@pytest.fixture
def doc_routes_mod(monkeypatch):
    class _DBStub(types.ModuleType):
        def __getattr__(self, name):
            return MagicMock()

    db_stub = _DBStub("core.database")
    monkeypatch.setitem(sys.modules, "core.database", db_stub)

    monkeypatch.delitem(sys.modules, "routes.document_routes", raising=False)
    import routes.document_routes as mod
    return mod

class _FakeDocument:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

class _FakeDb:
    def __init__(self, doc):
        self.doc = doc

    def query(self, model):
        self.model = model
        return self

    def filter(self, *clauses):
        self.clauses = clauses
        return self

    def first(self):
        return self.doc

    def close(self):
        pass

def test_deactivate_route_clears_active_document_id(monkeypatch, doc_routes_mod):
    mod = doc_routes_mod
    doc = _FakeDocument(id="doc-123", session_id="session-456", title="Test Doc", language="python", is_active=True, owner="alice")

    fake_db = _FakeDb(doc)
    monkeypatch.setattr(mod, "SessionLocal", lambda: fake_db)
    monkeypatch.setattr(mod, "get_current_user", lambda req: "alice")
    monkeypatch.setattr(mod, "_verify_doc_owner", lambda db, d, user: None)

    # Set document active first
    from src.tool_implementations import set_active_document, get_active_document
    set_active_document("doc-123")
    assert get_active_document() == "doc-123"

    # Verify that the next chat loop fallback logic WOULD inject it
    # Fallback simulation:
    _mem_id = get_active_document()
    assert _mem_id == "doc-123"

    # Setup routes and get the deactivate endpoint
    router = mod.setup_document_routes(MagicMock())
    deactivate_handler = None
    for route in router.routes:
        if route.path == "/api/document/{doc_id}/deactivate" and "POST" in route.methods:
            deactivate_handler = route.endpoint
            break

    assert deactivate_handler is not None

    # Call deactivate
    req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(auth_manager=None)))
    import asyncio
    resp = asyncio.run(deactivate_handler(request=req, doc_id="doc-123"))

    assert resp == {"ok": True, "id": "doc-123"}

    # Assert get_active_document() is now None, proving it is no longer injected into next chat fallback
    assert get_active_document() is None
    
    # Fallback simulation:
    _mem_id_after = get_active_document()
    assert _mem_id_after is None
