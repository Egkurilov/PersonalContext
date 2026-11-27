from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.exec_driver_sql("PRAGMA busy_timeout=5000")
        connection.exec_driver_sql("PRAGMA synchronous=FULL")
        connection.commit()
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            context.configure(connection=connection, render_as_batch=True, transactional_ddl=True)
            with context.begin_transaction():
                context.run_migrations()
            connection.commit()
        except BaseException:
            connection.rollback()
            raise


run_migrations_online()
