from __future__ import annotations

import typing as t
from functools import reduce
from string import Template

import sqlglot
from sqlglot import Generator, exp
from sqlglot.executor.env import ENV
from sqlglot.executor.python import Python
from sqlglot.helper import csv, ensure_collection

from sqlmesh.core.dialect import (
    MacroDef,
    MacroFunc,
    MacroSQL,
    MacroStrReplace,
    MacroVar,
)
from sqlmesh.utils import registry_decorator
from sqlmesh.utils.errors import MacroEvalError, SQLMeshError


class MacroStrTemplate(Template):
    delimiter = "@"


EXPRESSIONS_NAME_MAP = {}

for klass in sqlglot.Parser.EXPRESSION_PARSERS:
    name = klass if isinstance(klass, str) else klass.__name__  # type: ignore
    EXPRESSIONS_NAME_MAP[name.lower()] = name


def _macro_sql(sql: str, into: t.Optional[str] = None) -> str:
    args = [_macro_str_replace(sql)]
    if into in EXPRESSIONS_NAME_MAP:
        args.append(f"into=exp.{EXPRESSIONS_NAME_MAP[into]}")
    return f"self.parse_one({', '.join(args)})"


def _macro_func_sql(self: Generator, e: exp.Expression) -> str:
    func = e.this

    if isinstance(func, exp.Anonymous):
        return f"""self.send({csv("'" + func.name + "'", self.expressions(func))})"""
    return self.sql(func)


def _macro_str_replace(text: str) -> str:
    """Stringifies python code for variable replacement
    Args:
        text: text string
    Returns:
        Stringified python code to execute variable replacement
    """
    return f"self.template({text}, locals())"


class MacroDialect(Python):
    class Generator(Python.Generator):
        TRANSFORMS = {
            **Python.Generator.TRANSFORMS,  # type: ignore
            exp.Column: lambda self, e: e.name,
            exp.Lambda: lambda self, e: f"lambda {self.expressions(e)}: {self.sql(e, 'this')}",
            MacroFunc: _macro_func_sql,
            MacroSQL: lambda self, e: _macro_sql(
                self.sql(e, "this"), e.args.get("into")
            ),
            MacroStrReplace: lambda self, e: _macro_str_replace(self.sql(e, "this")),
        }


class MacroEvaluator:
    """The class responsible for evaluating SQLMesh Macros/SQL.

    SQLMesh supports special preprocessed SQL prefixed with `@`. Although it provides similar power to
    traditional methods like string templating, there is semantic understanding of SQL which prevents
    common errors like leading/trailing commas, syntax errors etc.

    SQLMesh SQL allows for macro variables and macro functions.

    Macro variables take the form of @variable. These are used for variable substitution.

    SELECT * FROM foo WHERE ds BETWEEN @start_date AND @end_date

    Macro variables can be defined with a special macro function.

    @DEF(start_date, '2021-01-01')

    Args:
        dialect: Dialect of the SQL to evaluate.
        env: Python execution environment including global variables
    """

    def __init__(self, dialect: str = "", env: t.Optional[t.Dict[str, t.Any]] = None):
        from sqlmesh.core.model import prepare_env

        self.dialect = dialect
        self.generator = MacroDialect().generator()
        self.locals: t.Dict[str, t.Any] = {}
        self.env = {**ENV, "self": self}
        self.macros = {
            normalize_macro_name(k): v.func for k, v in macro.get_registry().items()
        }
        prepare_env(self.env, env, self.macros)

    def send(
        self, name: str, *args
    ) -> t.Union[None, exp.Expression, t.List[exp.Expression]]:
        func = self.macros.get(normalize_macro_name(name))

        if not callable(func):
            raise SQLMeshError(f"Macro '{name}' does not exist.")

        return func(self, *args)

    def transform(
        self, query: exp.Expression
    ) -> exp.Expression | t.List[exp.Expression] | None:
        query = query.transform(
            lambda node: exp.convert(self.locals[node.name])
            if isinstance(node, MacroVar)
            else node
        )

        def evaluate_macros(
            node: exp.Expression,
        ) -> exp.Expression | t.List[exp.Expression] | None:
            exp.replace_children(
                node, lambda n: n if isinstance(n, exp.Lambda) else evaluate_macros(n)
            )
            if isinstance(node, MacroFunc):
                return self.evaluate(node)
            return node

        transformed = evaluate_macros(query)

        if transformed:
            for expression in ensure_collection(transformed):
                expression.transform(  # type: ignore
                    lambda node: node.this
                    if isinstance(node, exp.Column) and node.arg_key == "alias"
                    else node,
                    copy=False,
                )

        return transformed

    def template(self, text: t.Any, local_variables: t.Dict[str, t.Any]) -> str:
        """Substitute @vars with locals.

        Args:
            text: The string to do substitition on.
            local_variables: Local variables in the context so that lambdas can be used.

        Returns:
           The rendered string.
        """
        return MacroStrTemplate(str(text)).safe_substitute(
            self.locals, **local_variables
        )

    def evaluate(
        self, node: MacroFunc
    ) -> exp.Expression | t.List[exp.Expression] | None:
        if isinstance(node, MacroDef):
            self.locals[node.name] = node.expression
            return node

        if isinstance(node, MacroSQL) or not node.find(exp.Column, exp.Table):
            result = self.eval_expression(node)
        else:
            func = node.this
            result = self.send(func.name, *func.expressions)

        if result is None:
            return None

        if isinstance(result, list):
            return [exp.convert(item) for item in result if item is not None]
        return exp.convert(result)

    def eval_expression(self, node: exp.Expression) -> t.Any:
        """Converts a SQLGlot expression into executable Python code and evals it.

        Args:
            node: expression
        Returns:
            The return value of the evaled Python Code.
        """
        code = node.sql()
        try:
            code = self.generator.generate(node)
            return eval(code, self.env, self.locals)
        except Exception as e:
            raise MacroEvalError(
                f"Error trying to eval macro.\n\nGenerated code: {code}\n\nOriginal sql: {node}"
            ) from e

    def parse_one(
        self, sql: str, into: t.Optional[exp.Expression] = None, **opts
    ) -> t.Optional[exp.Expression]:
        """Parses the given SQL string and returns a syntax tree for the first
        parsed SQL statement.

        Args:
            sql (str): the SQL code string to parse.
            into (Expression): the Expression to parse into
            **opts: other options

        Returns:
            Expression: the syntax tree for the first parsed statement
        """
        return sqlglot.maybe_parse(sql, dialect=self.dialect, into=into, **opts)


class macro(registry_decorator):
    """Specifies a function is a macro and registers it the global MACROS registry.

    Registered macros can be referenced in SQL statements to make queries more dynamic or cleaner.

    Example:
        from typing import t
        from sqlglot import exp
        from sqlmesh.core.macros import MacroEvaluator, macro

        @macro()
        def add_one(evaluator: MacroEvaluator, column: str) -> exp.Add:
            return evaluator.parse_one(f"{column} + 1")

    Args:
        name: A custom name for the macro, the default is the name of the function.
        serialize: Whether or not to serialize this macro when used in a model, defaults to True.
    """

    registry_name = "macros"

    def __init__(
        self,
        name: str = "",
        serialize: bool = True,
    ):
        super().__init__(name)
        self.serialize = serialize


MacroRegistry = t.Dict[str, macro]


def norm_var_arg_lambda(
    evaluator: MacroEvaluator, func: exp.Lambda, *items
) -> t.Tuple[t.Iterable, t.Callable]:
    """
    Converts sql literal array and lambda into actual python iterable + callable.

    In order to support expressions like @EACH([a, b, c], x -> @SQL('@x')), the lambda var x
    needs be passed to the local state.

    Args:
        evaluator: MacroEvaluator that invoked the macro
        func: Lambda SQLGlot expression.
        items: Array or items of SQLGlot expressions.
    """

    def substitute(
        node: exp.Expression, arg_index: t.Dict[str, int], *items: exp.Expression
    ):
        if (
            isinstance(node, exp.Identifier)
            and node.name in arg_index
            and not isinstance(node.parent, exp.Column)
        ):
            return items[arg_index[node.name]].copy()
        if isinstance(node, MacroFunc):
            local_copy = evaluator.locals.copy()
            for k, v in arg_index.items():
                evaluator.locals[k] = items[v]
            result = evaluator.transform(node)
            evaluator.locals = local_copy
            return result
        return node

    if len(items) == 1:
        item = items[0]
        expressions = item.expressions if isinstance(item, exp.Array) else item
    else:
        expressions = items

    if not callable(func):
        arg_index = {
            expression.name: i for i, expression in enumerate(func.expressions)
        }
        body = func.this
        return expressions, lambda *x: body.transform(substitute, arg_index, *x)

    return expressions, func


@macro(serialize=False)
def each(
    evaluator: MacroEvaluator,
    *args: t.Any,
) -> t.List[t.Any]:
    """Iterates through items calling func on each.

    If a func call on item returns None, it will be excluded from the list.

    Args:
        evaluator: MacroEvaluator that invoked the macro
        args: The last argument should be a lambda of the form x -> x +1. The first argument can be
            an Array or var args can be used.

    Returns:
        A list of items that is the result of func
    """
    *items, func = args
    items, func = norm_var_arg_lambda(evaluator, func, *items)  # type: ignore
    return [item for item in map(func, items) if item is not None]


@macro("REDUCE", serialize=False)
def reduce_(evaluator: MacroEvaluator, *args: t.Any) -> t.Any:
    """Iterates through items applying provided function that takes two arguments
    cumulatively to the items of iterable items, from left to right, so as to reduce
    the iterable to a single item.

    Example:
        >>> from sqlglot import parse_one
        >>> from sqlmesh.core.macros import MacroEvaluator, reduce_
        >>> sql = "@SQL(@REDUCE([100, 200, 300, 400], (x, y) -> x + y))"
        >>> MacroEvaluator().transform(parse_one(sql)).sql()
        '1000'

    Args:
        evaluator: MacroEvaluator that invoked the macro
        args: The last argument should be a lambda of the form (x, y) -> x + y. The first argument can be
            an Array or var args can be used.
    Returns:
        A single item that is the result of applying func cumulatively to items
    """
    *items, func = args
    items, func = norm_var_arg_lambda(evaluator, func, *items)  # type: ignore
    return reduce(func, items)


@macro("FILTER", serialize=False)
def filter_(evaluator: MacroEvaluator, *args: t.Any) -> t.List[t.Any]:
    """Iterates through items, applying provided function to each item and removing
    all items where the function returns False

    Example:
        >>> from sqlglot import parse_one
        >>> from sqlmesh.core.macros import MacroEvaluator, filter_
        >>> sql = "@REDUCE(@FILTER([1, 2, 3], x -> x > 1), (x, y) -> x + y)"
        >>> MacroEvaluator().transform(parse_one(sql)).sql()
        '5'

    Args:
        evaluator: MacroEvaluator that invoked the macro
        args: The last argument should be a lambda of the form x -> x > 1. The first argument can be
            an Array or var args can be used.
    Returns:
        The items for which the func returned True
    """
    *items, func = args
    items, func = norm_var_arg_lambda(evaluator, func, *items)  # type: ignore
    return list(filter(func, items))


@macro("WITH", serialize=False)
def with_(
    evaluator: MacroEvaluator,
    condition: exp.Condition,
    expression: exp.With,
) -> t.Optional[exp.With]:
    """Inserts WITH expression when the condition is True

    Example:
        >>> from sqlglot import parse_one
        >>> from sqlmesh.core.macros import MacroEvaluator, with_
        >>> sql = "@WITH(True) all_cities as (select * from city) select all_cities"
        >>> MacroEvaluator().transform(parse_one(sql)).sql()
        'WITH all_cities AS (SELECT * FROM city) SELECT all_cities'

    Args:
        evaluator: MacroEvaluator that invoked the macro
        condition: Condition expression
        expression: With expression
    Returns:
        With expression if the conditional is True; otherwise None
    """
    return expression if evaluator.eval_expression(condition) else None


@macro(serialize=False)
def join(
    evaluator: MacroEvaluator,
    condition: exp.Condition,
    expression: exp.Join,
) -> t.Optional[exp.Join]:
    """Inserts JOIN expression when the condition is True

    Example:
        >>> from sqlglot import parse_one
        >>> from sqlmesh.core.macros import MacroEvaluator, join
        >>> sql = "select * from city @JOIN(True) country on city.country = country.name"
        >>> MacroEvaluator().transform(parse_one(sql)).sql()
        'SELECT * FROM city JOIN country ON city.country = country.name'

        >>> sql = "select * from city left outer @JOIN(True) country on city.country = country.name"
        >>> MacroEvaluator().transform(parse_one(sql)).sql()
        'SELECT * FROM city LEFT OUTER JOIN country ON city.country = country.name'

    Args:
        evaluator: MacroEvaluator that invoked the macro
        condition: Condition expression
        expression: Join expression
    Returns:
        Join expression if the conditional is True; otherwise None
    """
    return expression if evaluator.eval_expression(condition) else None


@macro(serialize=False)
def where(
    evaluator: MacroEvaluator,
    condition: exp.Condition,
    expression: exp.Where,
) -> t.Optional[exp.Where]:
    """Inserts WHERE expression when the condition is True

    Example:
        >>> from sqlglot import parse_one
        >>> from sqlmesh.core.macros import MacroEvaluator, where
        >>> sql = "select * from city @WHERE(True) population > 100 and country = 'Mexico'"
        >>> MacroEvaluator().transform(parse_one(sql)).sql()
        "SELECT * FROM city WHERE population > 100 AND country = 'Mexico'"

    Args:
        evaluator: MacroEvaluator that invoked the macro
        condition: Condition expression
        expression: Where expression
    Returns:
        Where expression if condition is True; otherwise None
    """
    return expression if evaluator.eval_expression(condition) else None


@macro(serialize=False)
def group_by(
    evaluator: MacroEvaluator,
    condition: exp.Condition,
    expression: exp.Group,
) -> t.Optional[exp.Group]:
    """Inserts GROUP BY expression when the condition is True

    Example:
        >>> from sqlglot import parse_one
        >>> from sqlmesh.core.macros import MacroEvaluator, group_by
        >>> sql = "select * from city @GROUP_BY(True) country, population"
        >>> MacroEvaluator().transform(parse_one(sql)).sql()
        'SELECT * FROM city GROUP BY country, population'

    Args:
        evaluator: MacroEvaluator that invoked the macro
        condition: Condition expression
        expression: Group expression
    Returns:
        Group expression if the condition is True; otherwise None
    """
    return expression if evaluator.eval_expression(condition) else None


@macro(serialize=False)
def having(
    evaluator: MacroEvaluator,
    condition: exp.Condition,
    expression: exp.Having,
) -> t.Optional[exp.Having]:
    """Inserts HAVING expression when the condition is True

    Example:
        >>> from sqlglot import parse_one
        >>> from sqlmesh.core.macros import MacroEvaluator, having
        >>> sql = "select * from city group by country @HAVING(True) population > 100 and country = 'Mexico'"
        >>> MacroEvaluator().transform(parse_one(sql)).sql()
        "SELECT * FROM city GROUP BY country HAVING population > 100 AND country = 'Mexico'"

    Args:
        evaluator: MacroEvaluator that invoked the macro
        condition: Condition expression
        expression: Having expression
    Returns:
        Having expression if the condition is True; otherwise None
    """
    return expression if evaluator.eval_expression(condition) else None


@macro(serialize=False)
def order_by(
    evaluator: MacroEvaluator,
    condition: exp.Condition,
    expression: exp.Order,
) -> t.Optional[exp.Order]:
    """Inserts ORDER BY expression when the condition is True

    Example:
        >>> from sqlglot import parse_one
        >>> from sqlmesh.core.macros import MacroEvaluator, order_by
        >>> sql = "select * from city @ORDER_BY(True) population, name DESC"
        >>> MacroEvaluator().transform(parse_one(sql)).sql()
        'SELECT * FROM city ORDER BY population, name DESC'

    Args:
        evaluator: MacroEvaluator that invoked the macro
        condition: Condition expression
        expression: Order expression
    Returns:
        Order expression if the condition is True; otherwise None
    """
    return expression if evaluator.eval_expression(condition) else None


def normalize_macro_name(name: str) -> str:
    """Prefix macro name with @ and upcase"""
    return f"@{name.upper()}"