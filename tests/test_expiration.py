"""Tables are kept alive in the sandbox: extended when due, renewed by copy when refused."""

import datetime as dt
from types import SimpleNamespace

from google.api_core.exceptions import Forbidden

from pipeline import load_raw

NOW = dt.datetime(2026, 11, 27, 22, 0, tzinfo=dt.UTC)


class FakeJob:
    def result(self):
        return self


class FakeClient:
    def __init__(self, tables, refuse=False):
        self.tables = tables  # table_id -> SimpleNamespace
        self.refuse = refuse
        self.calls = []

    def list_tables(self, dataset):
        return [SimpleNamespace(table_id=t, table_type=v.kind, reference=f"p.{dataset}.{t}")
                for t, v in list(self.tables.items())]  # fmt: skip

    def get_table(self, ref):
        return self.tables[ref.split(".")[-1]]

    def update_table(self, table, fields):
        if self.refuse and fields == ["expires"]:
            raise Forbidden("Table expiration time must be less than 60 days while in sandbox mode.")
        self.calls.append(("update", table.table_id, tuple(fields)))

    def copy_table(self, src, dst, job_config=None):
        self.calls.append(("copy", src.split(".")[-1], dst.split(".")[-1]))
        old = self.tables[src.split(".")[-1]]
        self.tables[dst.split(".")[-1]] = SimpleNamespace(**{**vars(old), "table_id": dst.split(".")[-1]})
        return FakeJob()

    def delete_table(self, ref):
        self.calls.append(("delete", ref.split(".")[-1]))
        del self.tables[ref.split(".")[-1]]


def table(name, expires_in_days, kind="TABLE"):
    return SimpleNamespace(table_id=name, kind=kind, project="p", dataset_id="raw", description="d",
                           labels={"layer": "raw"}, expires=NOW + dt.timedelta(days=expires_in_days))  # fmt: skip


def test_far_expirations_are_left_alone_and_views_skipped():
    client = FakeClient({"customers": table("customers", 58), "v": table("v", 1, kind="VIEW")})
    assert load_raw.refresh_expiration(client, "raw", now=NOW) == 0
    assert client.calls == []


def test_a_near_expiration_is_extended():
    client = FakeClient({"customers": table("customers", 10)})
    assert load_raw.refresh_expiration(client, "raw", now=NOW) == 1
    assert client.calls == [("update", "customers", ("expires",))]


def test_a_refused_extension_renews_the_table_by_copy():
    client = FakeClient({"customers": table("customers", 10)}, refuse=True)
    assert load_raw.refresh_expiration(client, "raw", now=NOW) == 1
    assert client.calls == [
        ("copy", "customers", "customers__renew"),
        ("delete", "customers"),
        ("copy", "customers__renew", "customers"),
        ("delete", "customers__renew"),
        ("update", "customers", ("description", "labels", "expires")),
    ]
    assert set(client.tables) == {"customers"}
