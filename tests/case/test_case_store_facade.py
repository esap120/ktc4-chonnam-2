"""`CaseStore` facade — repository · conn · adapter registry를 묶는다(`decisions/case-store-mysql.md` §5)."""

from __future__ import annotations

from daesingo.case.domain import CaseAggregate
from daesingo.case.store import AdapterRegistry, CaseStore, InMemoryCaseRepository


class _BindingAdapter:
    def __init__(self) -> None:
        self.bound = None

    def bind_case(self, case):
        self.bound = case


def test_get_case_returns_copy_and_save_persists():
    store = CaseStore()
    store.register(CaseAggregate.empty("case_f001"))
    case = store.load_for_update("case_f001")
    case.start_search()
    assert store.get_case("case_f001").stage == "INTAKE"
    store.save(case)
    assert store.get_case("case_f001").stage == "SEARCHING"


def test_get_adapter_binds_the_loaded_case():
    store = CaseStore()
    adapter = _BindingAdapter()
    store.register(CaseAggregate.empty("case_f002"), adapter)
    case = store.get_case("case_f002")
    assert store.get_adapter("case_f002", case) is adapter
    assert adapter.bound is case


def test_unregistered_adapter_is_none():
    store = CaseStore()
    store.register(CaseAggregate.empty("case_f003"))
    assert store.get_adapter("case_f003") is None
    assert store.get_adapter("case_never") is None


def test_store_wraps_given_repository_and_registry():
    repo, registry = InMemoryCaseRepository(), AdapterRegistry()
    store = CaseStore(repository=repo, adapters=registry, conn=None)
    store.register(CaseAggregate.empty("case_f004"))
    assert repo.load(None, "case_f004").case_id == "case_f004"
