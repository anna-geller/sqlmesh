"""
# EngineAdapter

Engine adapters are how SQLMesh connects and interacts with various data stores. They allow SQLMesh to
generalize its functionality to different engines that have Python Database API 2.0 compliant
connections. Rather than executing queries directly against your data stores, SQLMesh components like
the SnapshotEvaluator delegates them to engine adapters so these components can be engine agnostic.
"""
from __future__ import annotations

import contextlib
import logging
import typing as t

import duckdb
import pandas as pd
from sqlglot import exp

from sqlmesh.utils import optional_import
from sqlmesh.utils.df import pandas_to_sql
from sqlmesh.utils.errors import SQLMeshError

DF_TYPES: t.Tuple = (pd.DataFrame,)
pyspark = optional_import("pyspark")

if pyspark:
    DF_TYPES += (pyspark.sql.DataFrame,)

DF = t.Union[DF_TYPES]  # type: ignore
Query = t.Union[exp.Subqueryable, exp.DerivedTable]
QueryOrDF = t.Union[Query, DF]

logger = logging.getLogger(__name__)


class EngineAdapter:
    """Base class wrapping a Database API compliant connection.

    The EngineAdapter is an easily subclassable interface that interacts
    with the underlying engine and data store.

    Args:
        connection: Database API compliant connection. The connection will be
            lazily established if a callable that returns a connection is passed in.
        dialect: The dialect with which this adapter is associated.
    """

    def __init__(self, connection: t.Any, dialect: str):
        self.connection = connection
        self.dialect = dialect.lower()
        self.spark: t.Optional["pyspark.sql.SparkSession"] = getattr(  # type: ignore
            connection, "spark", None
        )
        self._transaction = False

    @property
    def cursor(self) -> t.Any:
        if not hasattr(self, "_cursor"):
            if callable(self.connection):
                self._cursor = self.connection().cursor()
            else:
                self._cursor = self.connection.cursor()
        return self._cursor

    def create_and_insert(
        self,
        table_name: str,
        columns: t.Dict[str, exp.DataType],
        query_or_df: QueryOrDF,
        **kwargs,
    ):
        """Inserts query into table and creates it if missing.

        Args:
            table_name: The name of the table (eg. prod.table)
            columns: A mapping between the column name and its data type
            query_or_df: The SQL query or dataframe to insert.
            kwargs: Additional kwargs for creating the table or updating the query
        """
        self.create_table(table_name, columns, **kwargs)
        self.insert_append(table_name, query_or_df, columns=columns)

    def replace_query(self, table_name: str, query_or_df: QueryOrDF):
        """Replaces an existing table with a query.

        For partiton based engines (hive, spark), insert override is used. For other systems, create or replace is used.

        Args:
            table_name: The name of the table (eg. prod.table)
            query_or_df: The SQL query to run or a dataframe.
        """
        if self.supports_partitions:
            self.insert_overwrite(table_name, query_or_df)
        else:
            self.execute(
                exp.Create(
                    kind="TABLE",
                    this=exp.to_table(table_name),
                    replace=True,
                    expression=query_or_df,
                )
            )

    def create_table(
        self,
        table_name: str,
        columns: t.Dict[str, exp.DataType],
        exists: bool = True,
        **kwargs,
    ) -> None:
        """Create a table using a DDL statement

        Args:
            table_name: The name of the table to create. Can be fully qualified or just table name
            columns: A mapping between the column name and its data type
            exists: Indicates if you to include an IF EXISTS check
            kwargs: Optional create table properties.
        """
        properties = self._create_table_properties(**kwargs)

        schema = exp.Schema(
            this=exp.to_table(table_name),
            expressions=[
                exp.ColumnDef(this=exp.to_identifier(column), kind=kind)
                for column, kind in columns.items()
            ],
        )
        create_expression = exp.Create(
            this=schema, kind="TABLE", exists=exists, properties=properties
        )
        self.execute(create_expression)

    def drop_table(self, table_name: str, exists: bool = True) -> None:
        """Drops a table.

        Args:
            table_name: The name of the table to drop.
            exists: If exists, defaults to True.
        """
        drop_expression = exp.Drop(this=table_name, kind="TABLE", exists=exists)
        self.execute(drop_expression)

    def create_view(
        self,
        view_name: str,
        query_or_df: QueryOrDF,
        columns: t.Iterable[str] = [],
        replace: bool = True,
    ) -> None:
        """Create a view with a query or dataframe.

        If a dataframe is passed in, it will be converted into a literal values statement.
        This should only be done if the dataframe is very small!

        Args:
            view_name: The view name.
            query_or_df: A query or dataframe.
            columns: Columns to use in the view statement.
            replace: Whether or not to replace an existing view defaults to True.
        """
        schema: t.Optional[exp.Table | exp.Schema] = exp.to_table(view_name)

        if isinstance(query_or_df, DF_TYPES):
            if pyspark and isinstance(query_or_df, pyspark.sql.DataFrame):
                query_or_df = query_or_df.toPandas()

            if not isinstance(query_or_df, pd.DataFrame):
                raise SQLMeshError("Can only create views with pandas dataframes.")

            if not columns:
                raise SQLMeshError(
                    "Creating a view with a dataframe requires passing in columns."
                )
            schema = exp.Schema(
                this=schema,
                expressions=[exp.column(column, quoted=True) for column in columns],
            )
            query_or_df = next(pandas_to_sql(query_or_df))

        self.execute(
            exp.Create(
                this=schema,
                kind="VIEW",
                replace=replace,
                expression=query_or_df,
            )
        )

    def create_schema(self, schema_name: str, ignore_if_exists: bool = True) -> None:
        """Create a schema from a name or qualified table name."""
        self.execute(
            exp.Create(
                this=exp.to_identifier(schema_name.split(".")[0]),
                kind="SCHEMA",
                exists=ignore_if_exists,
            )
        )

    def drop_view(self, view_name: str, ignore_if_not_exists: bool = True) -> None:
        """Drop a view."""
        if_exists = " IF EXISTS" if ignore_if_not_exists else ""
        self.execute(f"DROP VIEW{if_exists} {view_name}")

    def table_exists(self, table_name: str) -> bool:
        try:
            self.execute(f"DESCRIBE TABLE {table_name}")
            return True
        except Exception:
            return False

    def delete_from(self, table_name: str, where: t.Union[str, exp.Expression]) -> None:
        self.execute(exp.delete(table_name, where))

    def insert_append(
        self,
        table_name: str,
        query_or_df: QueryOrDF,
        columns: t.Optional[t.Iterable[str]] = None,
    ) -> None:
        self._insert(table_name, query_or_df, columns, overwrite=False)

    def insert_overwrite(
        self,
        table_name: str,
        query_or_df: QueryOrDF,
        columns: t.Optional[t.Iterable[str]] = None,
    ) -> None:
        self._insert(table_name, query_or_df, columns, overwrite=True)

    def delete_insert_query(
        self,
        table_name: str,
        query_or_df: QueryOrDF,
        where: exp.Condition,
        columns: t.Optional[t.Iterable[str]] = None,
    ) -> None:
        with self.transaction():
            self.delete_from(table_name, where=where)
            self.insert_append(table_name, query_or_df, columns=columns)

    def update_table(
        self,
        table_name: str,
        properties: t.Optional[t.Dict[str, t.Any]] = None,
        where: t.Optional[str | exp.Condition] = None,
    ) -> None:
        self.execute(exp.update(table_name, properties, where=where))

    def fetchone(self, query: t.Union[exp.Expression, str]) -> t.Tuple:
        self.execute(query)
        return self.cursor.fetchone()

    def fetchall(self, query: t.Union[exp.Expression, str]) -> t.List[t.Tuple]:
        self.execute(query)
        return self.cursor.fetchall()

    def fetchdf(self, query: t.Union[exp.Expression, str]) -> DF:
        self.execute(query)
        if hasattr(self.cursor, "fetchdf"):
            return self.cursor.fetchdf()
        if hasattr(self.cursor, "fetchall_arrow"):
            return self.cursor.fetchall_arrow().to_pandas()
        raise NotImplementedError(
            "The cursor does not have a way to return a Pandas DataFrame"
        )

    @contextlib.contextmanager
    def transaction(self) -> t.Generator[None, None, None]:
        """A transaction context manager."""
        if self._transaction:
            yield
            return
        self._transaction = True
        self.execute(exp.Transaction())
        try:
            yield
        except Exception as e:
            self.execute(exp.Rollback())
            raise e
        else:
            self.execute(exp.Commit())
        finally:
            self._transaction = False

    @property
    def supports_partitions(self) -> bool:
        """Whether or not the engine adapter supports partitions."""
        return self.dialect in ("hive", "spark")

    def execute(self, sql: t.Union[str, exp.Expression]) -> None:
        """Execute a sql query."""
        sql = self._to_sql(sql) if isinstance(sql, exp.Expression) else sql
        logger.debug(f"Executing SQL:\n{sql}")
        self.cursor.execute(sql)

    def _insert(
        self,
        table_name: str,
        query_or_df: QueryOrDF,
        columns: t.Optional[t.Iterable[str]],
        overwrite: bool,
        batch_size: int = 10000,
    ) -> None:
        if not columns:
            into: t.Optional[exp.Expression] = exp.to_table(table_name)
        else:
            into = exp.Schema(
                this=exp.to_table(table_name),
                expressions=[exp.column(c, quoted=True) for c in columns],
            )

        if (
            self.spark
            and pyspark
            and isinstance(query_or_df, (pyspark.sql.DataFrame, pd.DataFrame))
        ):
            if not isinstance(query_or_df, pyspark.sql.DataFrame):
                query_or_df = self.spark.createDataFrame(query_or_df)
            query_or_df.select(*self.spark.table(table_name).columns).write.insertInto(  # type: ignore
                table_name, overwrite=overwrite
            )
        elif isinstance(query_or_df, pd.DataFrame):
            sqlalchemy = optional_import("sqlalchemy")
            # pandas to_sql doesn't support insert overwrite, it only supports deleting the table or appending
            if (
                not overwrite
                and sqlalchemy
                and isinstance(self.connection, sqlalchemy.engine.Connectable)
            ):
                query_or_df.to_sql(
                    table_name,
                    self.connection,
                    if_exists="append",
                    index=False,
                    chunksize=batch_size,
                    method="multi",
                )
            elif isinstance(self.connection, duckdb.DuckDBPyConnection):
                self.execute(
                    exp.Insert(
                        this=into,
                        expression="SELECT * FROM query_or_df",
                        overwrite=overwrite,
                    )
                )
            else:
                with self.transaction():
                    for values in pandas_to_sql(query_or_df, batch_size):
                        self.execute(
                            exp.Insert(
                                this=into,
                                expression=values,
                                overwrite=overwrite,
                            )
                        )
        elif isinstance(query_or_df, exp.Expression):
            self.execute(
                exp.Insert(
                    this=into,
                    expression=query_or_df,
                    overwrite=overwrite,
                )
            )
        else:
            raise SQLMeshError(f"Unsupported dataframe {query_or_df}")

    def _create_table_properties(
        self,
        storage_format: t.Optional[str] = None,
        partitioned_by: t.Optional[t.List[str]] = None,
    ) -> t.Optional[exp.Properties]:
        if not self.supports_partitions:
            return None

        format_property = None
        partition_columns_property = None
        if storage_format:
            format_property = exp.TableFormatProperty(this=exp.Var(this=storage_format))
        if partitioned_by:
            partition_columns_property = exp.PartitionedByProperty(
                this=exp.Schema(
                    expressions=[exp.to_identifier(column) for column in partitioned_by]
                ),
            )
        return exp.Properties(
            expressions=[
                table_property
                for table_property in [format_property, partition_columns_property]
                if table_property
            ]
        )

    def _to_sql(self, e: exp.Expression, **kwargs) -> str:
        kwargs = {
            "dialect": self.dialect,
            "pretty": False,
            "comments": False,
            "identify": True,
            **kwargs,
        }
        return e.sql(**kwargs)