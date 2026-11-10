"""The catalogue migration can be undone and applied again."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_initial_migration_is_reversible() -> None:
    executor = MigrationExecutor(connection)
    executor.migrate([("catalog", None)])
    assert "catalog_track" not in connection.introspection.table_names()
    executor = MigrationExecutor(connection)
    # Reverting catalog also reverts the apps that depend on it (watches, among others), so
    # every app has to be reapplied, or they stay half-migrated for the rest of the suite.
    executor.migrate(executor.loader.graph.leaf_nodes())
    assert "catalog_track" in connection.introspection.table_names()
