"""
Unit tests for Click & Rich CLI suite.
"""

from click.testing import CliRunner
from qb_invoicing.cli import cli


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "qb-invoicing v" in result.output


def test_cli_init_db(tmp_path, monkeypatch):
    test_db = tmp_path / "cli_test.db"
    monkeypatch.setenv("DATABASE_PATH", str(test_db))

    runner = CliRunner()
    result = runner.invoke(cli, ["init-db"])
    assert result.exit_code == 0
    assert "Database initialized" in result.output
    assert test_db.exists()


def test_cli_preview():
    runner = CliRunner()
    result = runner.invoke(cli, ["preview", "--order", "samples/sample_order_ecommerce.json"])
    assert result.exit_code == 0
    assert "Order Ingestion Preview" in result.output
    assert "EC-8921" in result.output
    assert "QuickBooks Online API v3 JSON Payload" in result.output


def test_cli_generate_and_status(tmp_path, monkeypatch):
    test_db = tmp_path / "cli_flow.db"
    test_exports = tmp_path / "exports"
    monkeypatch.setenv("DATABASE_PATH", str(test_db))
    monkeypatch.setenv("EXPORTS_DIR", str(test_exports))

    runner = CliRunner()

    # 1. Initialize
    res_init = runner.invoke(cli, ["init-db"])
    assert res_init.exit_code == 0

    # 2. Generate invoice
    res_gen = runner.invoke(cli, ["generate", "--order", "samples/sample_order_ecommerce.json", "--export-html"])
    assert res_gen.exit_code == 0
    assert "Invoice Generated:" in res_gen.output
    assert "INV-2026-001" in res_gen.output

    # 3. Check status
    res_stat = runner.invoke(cli, ["status", "INV-2026-001"])
    assert res_stat.exit_code == 0
    assert "QuickBooks Invoice Status" in res_stat.output
    assert "INV-2026-001" in res_stat.output
    assert "Sarah Jenkins" in res_stat.output

    # 4. Record payment
    res_pay = runner.invoke(cli, ["record-payment", "--invoice", "INV-2026-001", "--amount", "100.00", "--method", "CreditCard"])
    assert res_pay.exit_code == 0
    assert "Payment of $100.00 recorded successfully" in res_pay.output

    # 5. List invoices
    res_list = runner.invoke(cli, ["list-invoices"])
    assert res_list.exit_code == 0
    assert "1001" in res_list.output
    assert "Sarah" in res_list.output

    # 6. Check metrics
    res_met = runner.invoke(cli, ["metrics"])
    assert res_met.exit_code == 0
    assert "Total Invoices Tracked" in res_met.output

    # 7. Sync payments
    res_sync = runner.invoke(cli, ["sync-payments"])
    assert res_sync.exit_code == 0
    assert "Reconciliation Complete" in res_sync.output


def test_cli_batch_generate(tmp_path, monkeypatch):
    test_db = tmp_path / "cli_batch.db"
    monkeypatch.setenv("DATABASE_PATH", str(test_db))

    runner = CliRunner()
    runner.invoke(cli, ["init-db"])

    res_batch = runner.invoke(cli, ["batch-generate", "--file", "samples/sample_orders_batch.json"])
    assert res_batch.exit_code == 0
    assert "Batch Invoicing Results" in res_batch.output
    assert "BATCH-001" in res_batch.output
    assert "BATCH-002" in res_batch.output
    assert "BATCH-003" in res_batch.output
    assert "Successfully generated 3/3 invoices" in res_batch.output
