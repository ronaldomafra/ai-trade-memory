import ast
import sqlite3
from pathlib import Path


def test_hexagonal_dependency_direction():
    for layer in ("domain", "application"):
        for path in Path(f"src/poc/{layer}").rglob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                module = node.module if isinstance(node, ast.ImportFrom) else None
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else []
                for name in ([module] if module else []) + names:
                    assert not name.startswith(("poc.adapters", "poc.presentation")), (path, name)
                    if layer == "domain":
                        assert not name.startswith(("sqlite3", "httpx", "poc.config", "textual"))


def test_financial_schema_never_uses_sqlite_real():
    schema = Path("src/poc/adapters/outbound/migrations/001_accounting.sql").read_text()
    connection = sqlite3.connect(":memory:", isolation_level=None)
    connection.executescript(schema)
    financial_columns = {
        "portfolios": ["cash_usdt", "base_qty", "base_cost_basis_usdt", "realized_pnl_usdt"],
        "paper_fills": ["qty_base", "fill_price", "gross_usdt", "fee_usdt", "net_cash_delta_usdt"],
        "ledger_entries": ["amount", "balance_after"],
        "price_quotes": ["bid", "ask"],
    }
    for table, columns in financial_columns.items():
        types = {r[1]: r[2] for r in connection.execute(f"PRAGMA table_info({table})")}
        assert all(types[name] == "TEXT" for name in columns)
    connection.close()
    assert "ledger_no_update" in schema
    assert "fills_no_delete" in schema


def test_remote_tui_has_no_local_storage_broker_or_runtime_dependencies():
    for name in ("inbound/tui.py", "inbound/tui_charts.py", "outbound/control_client.py"):
        tree = ast.parse((Path("src/poc/adapters") / name).read_text())
        for node in ast.walk(tree):
            modules = (
                [node.module]
                if isinstance(node, ast.ImportFrom)
                else ([alias.name for alias in node.names] if isinstance(node, ast.Import) else [])
            )
            for module in modules:
                assert not module.startswith(
                    (
                        "sqlite3",
                        "subprocess",
                        "poc.adapters.outbound.sqlite",
                        "poc.adapters.outbound.runtime",
                        "poc.adapters.outbound.market",
                        "poc.domain.broker",
                        "poc.adapters.outbound.openrouter",
                    )
                ), (name, module)
