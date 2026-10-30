"""
Minimal in-memory stand-in for the Firestore calls used by app.py.

Tests built on this never connect to, read from or write to a real
Firestore project. Installing it replaces firebase_admin, flask_cors and
google.cloud.firestore_v1 with stubs *only if* those packages are
missing or when force=True, so the same tests can also be pointed at the
real libraries.
"""

import sys
import types


class FieldFilter:
    def __init__(self, field_path, op_string, value):
        self.field_path, self.op_string, self.value = (
            field_path, op_string, value
        )


class Snapshot:
    def __init__(self, ref, data):
        self.reference = ref
        self.id = ref.id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return None if self._data is None else dict(self._data)


class DocRef:
    def __init__(self, store, path):
        self._store, self.path = store, tuple(path)
        self.id = self.path[-1]

    def get(self, transaction=None):
        return Snapshot(self, self._store.docs.get(self.path))

    def set(self, data):
        self._store.docs[self.path] = dict(data)

    def collection(self, name):
        return CollRef(self._store, self.path + (name,))


class Query:
    def __init__(self, store, path, filters=()):
        self._store, self._path, self._filters = store, path, tuple(filters)

    def where(self, field=None, op=None, value=None, filter=None):
        if filter is not None:
            field, op, value = (
                filter.field_path, filter.op_string, filter.value
            )
        assert op == "==", "fake supports equality filters only"
        self._store.queries.append((self._path, field, value))
        return Query(
            self._store, self._path, self._filters + ((field, value),)
        )

    def stream(self):
        n = len(self._path)
        for path, data in list(self._store.docs.items()):
            if len(path) == n + 1 and path[:n] == self._path:
                if all(data.get(f) == v for f, v in self._filters):
                    yield Snapshot(DocRef(self._store, path), data)


class CollRef(Query):
    def __init__(self, store, path):
        super().__init__(store, path)

    def document(self, doc_id=None):
        return DocRef(self._store, self._path + (doc_id,))


class Transaction:
    def update(self, ref, updates):
        doc = ref._store.docs[ref.path]
        for key, value in updates.items():
            parts = key.split(".")
            target = doc
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = value

    def set(self, ref, data):
        ref.set(data)


class FakeDb:
    def __init__(self):
        self.docs = {}
        self.queries = []

    def collection(self, name):
        return CollRef(self, (name,))

    def transaction(self):
        return Transaction()

    def put(self, path, data):
        self.docs[tuple(path)] = dict(data)


def install_stubs(db):
    """Make `import app` work without Firebase and bind it to `db`."""

    def module(name, **attrs):
        mod = types.ModuleType(name)
        mod.__dict__.update(attrs)
        sys.modules[name] = mod
        return mod

    firestore = module(
        "firebase_admin.firestore",
        client=lambda: db,
        transactional=lambda fn: fn,
    )
    credentials = module(
        "firebase_admin.credentials", Certificate=lambda path: None
    )
    firebase_admin = module(
        "firebase_admin",
        _apps={"stub": True},  # skip initialize_app()
        firestore=firestore,
        credentials=credentials,
        initialize_app=lambda *a, **k: None,
    )
    module("flask_cors", CORS=lambda app, *a, **k: app)
    module("google")
    module("google.cloud")
    module("google.cloud.firestore_v1")
    module(
        "google.cloud.firestore_v1.base_query", FieldFilter=FieldFilter
    )
    return firebase_admin
