import typing as t
from difflib import unified_diff

from sqlglot import Dialect, Generator, Parser, TokenType, exp
from sqlglot.tokens import Token


class Model(exp.Expression):
    arg_types = {"expressions": True}


class Audit(exp.Expression):
    arg_types = {"expressions": True}


class MacroVar(exp.Var):
    pass


class MacroFunc(exp.Func):
    pass


class MacroDef(MacroFunc):
    arg_types = {"this": True, "expression": True}


class MacroSQL(MacroFunc):
    arg_types = {"this": True, "into": False}


class MacroStrReplace(MacroFunc):
    pass


class DColonCast(exp.Cast):
    pass


@t.no_type_check
def _parse_statement(self: Parser) -> t.Optional[exp.Expression]:
    if self._curr is None:
        return None

    parser = PARSERS.get(self._curr.text.upper())

    if parser:
        # Capture any available description in the form of a comment
        comments = self._curr.comments

        self._advance()
        meta = self._parse_wrapped(lambda: parser(self))

        meta.comments = comments
        return meta
    return self.__parse_statement()


@t.no_type_check
def _parse_lambda(self: Parser) -> t.Optional[exp.Expression]:
    node = self.__parse_lambda()
    if isinstance(node, exp.Lambda):
        node.set("this", self._parse_alias(node.this))
    return node


@t.no_type_check
def _parse_placeholder(self: Parser) -> t.Optional[exp.Expression]:
    return self.__parse_placeholder() or (
        self._match(TokenType.PARAMETER) and _parse_macro(self, None)
    )


def _parse_macro(
    self: Parser, _token: Token, keyword_macro: str = ""
) -> t.Optional[exp.Expression]:
    index = self._index - 1
    field = self._parse_primary() or self._parse_function({}) or self._parse_id_var()

    if isinstance(field, exp.Func):
        macro_name = field.name.upper()
        if macro_name != keyword_macro and macro_name in KEYWORD_MACROS:
            self._retreat(index)
            return None
        if isinstance(field, exp.Anonymous):
            name = field.name.upper()
            if name == "DEF":
                return self.expression(
                    MacroDef, this=field.expressions[0], expression=field.expressions[1]
                )
            if name == "SQL":
                into = (
                    field.expressions[1].this.lower()
                    if len(field.expressions) > 1
                    else None
                )
                return self.expression(MacroSQL, this=field.expressions[0], into=into)
        return self.expression(MacroFunc, this=field)
    if field.is_string or (isinstance(field, exp.Identifier) and field.quoted):
        return self.expression(MacroStrReplace, this=exp.Literal.string(field.this))
    return self.expression(MacroVar, this=field.this)


KEYWORD_MACROS = {"WITH", "JOIN", "WHERE", "GROUP_BY", "HAVING", "ORDER_BY"}


def _parse_matching_macro(self: Parser, name: str) -> t.Optional[exp.Expression]:
    if (
        not self._match_pair(TokenType.PARAMETER, TokenType.VAR, advance=False)
        or self._next.text.upper() != name.upper()
    ):
        return None

    self._advance(1)
    return _parse_macro(self, self._curr, name)


@t.no_type_check
def _parse_with(self: Parser) -> t.Optional[exp.Expression]:
    macro = _parse_matching_macro(self, "WITH")
    if not macro:
        return self.__parse_with()

    macro.this.append("expressions", self.__parse_with(True))
    return macro


@t.no_type_check
def _parse_join(self: Parser) -> t.Optional[exp.Expression]:
    index = self._index
    natural, side, kind = self._parse_join_side_and_kind()
    macro = _parse_matching_macro(self, "JOIN")
    if not macro:
        self._retreat(index)
        return self.__parse_join()

    join = self.__parse_join(True)
    if natural:
        join.set("natural", True)
    if side:
        join.set("side", side.text)
    if kind:
        join.set("kind", kind.text)

    macro.this.append("expressions", join)
    return macro


@t.no_type_check
def _parse_where(self: Parser) -> t.Optional[exp.Expression]:
    macro = _parse_matching_macro(self, "WHERE")
    if not macro:
        return self.__parse_where()

    macro.this.append("expressions", self.__parse_where(True))
    return macro


@t.no_type_check
def _parse_group(self: Parser) -> t.Optional[exp.Expression]:
    macro = _parse_matching_macro(self, "GROUP_BY")
    if not macro:
        return self.__parse_group()

    macro.this.append("expressions", self.__parse_group(True))
    return macro


@t.no_type_check
def _parse_having(self: Parser) -> t.Optional[exp.Expression]:
    macro = _parse_matching_macro(self, "HAVING")
    if not macro:
        return self.__parse_having()

    macro.this.append("expressions", self.__parse_having(True))
    return macro


@t.no_type_check
def _parse_order(
    self: Parser, this: exp.Expression = None
) -> t.Optional[exp.Expression]:
    macro = _parse_matching_macro(self, "ORDER_BY")
    if not macro:
        return self.__parse_order(this)

    macro.this.append("expressions", self.__parse_order(this, True))
    return macro


def _create_parser(
    parser_type: t.Type[exp.Expression], table_keys: t.List[str]
) -> t.Callable:
    def parse(self: Parser) -> t.Optional[exp.Expression]:
        expressions = []

        while True:
            key = self._parse_id_var(True)

            if not key:
                break

            key = key.name.lower()

            if key in table_keys:
                value = exp.table_name(self._parse_table())
            elif key == "columns":
                value = self._parse_schema()
            else:
                value = self._parse_bracket(self._parse_field(any_token=True))

            expressions.append(self.expression(exp.Property, this=key, value=value))

            if not self._match(TokenType.COMMA):
                break

        return self.expression(parser_type, expressions=expressions)

    return parse


_parse_model = _create_parser(Model, ["name"])
_parse_audit = _create_parser(Audit, ["model"])
PARSERS = {"MODEL": _parse_model, "AUDIT": _parse_audit}


def _model_sql(self, expression: exp.Expression) -> str:
    props = ",\n".join(
        [
            self.indent(f"{prop.name} {self.sql(prop, 'value')}")
            for prop in expression.expressions
        ]
    )
    return "\n".join(["MODEL (", props, ")"])


def _macro_keyword_func_sql(self, expression: exp.Expression) -> str:
    name = expression.name
    keyword = name.replace("_", " ")
    *args, clause = expression.expressions
    macro = f"@{name}({self.format_args(*args)})"
    return self.sql(clause).replace(keyword, macro, 1)


def _macro_func_sql(self, expression: exp.Expression) -> str:
    expression = expression.this
    name = expression.name
    if name in KEYWORD_MACROS:
        return _macro_keyword_func_sql(self, expression)
    return f"@{name}({self.format_args(*expression.expressions)})"


def _override(klass: t.Type[Parser], func: t.Callable) -> None:
    name = func.__name__
    setattr(klass, f"_{name}", getattr(klass, name))
    setattr(klass, name, func)


def format_model_expressions(
    expressions: t.List[exp.Expression], dialect: t.Optional[str] = None
) -> str:
    """Format a model's expressions into a standardized format.

    Args:
        expressions: The model's expressions, must be at least model def + query.
        dialect: The dialect to render the expressions as.
    Returns:
        A string with the formatted model.
    """
    *statements, query = expressions
    query = query.copy()
    selects = []

    for expression in query.expressions:
        column = None
        comments = expression.comments
        expression.comments = None

        if not isinstance(expression, exp.Alias):
            if expression.name:
                expression = expression.replace(
                    exp.alias_(expression.copy(), expression.name)
                )

        column = column or expression
        expression = expression.this

        if isinstance(expression, exp.Cast):
            this = expression.this
            if not isinstance(this, (exp.Binary, exp.Unary)) or isinstance(
                this, exp.Paren
            ):
                expression.replace(DColonCast(this=this, to=expression.to))
        column.comments = comments
        selects.append(column)

    query.set("expressions", selects)

    return ";\n\n".join(
        [
            *(statement.sql(pretty=True, dialect=dialect) for statement in statements),
            query.sql(pretty=True, dialect=dialect),
        ]
    ).strip()


def text_diff(
    a: t.Optional[exp.Expression],
    b: t.Optional[exp.Expression],
    dialect: t.Optional[str] = None,
) -> str:
    """Find the unified text diff between two expressions."""
    return "\n".join(
        unified_diff(
            a.sql(pretty=True, comments=False, dialect=dialect).split("\n")
            if a
            else "",
            b.sql(pretty=True, comments=False, dialect=dialect).split("\n")
            if b
            else "",
        )
    )


@t.no_type_check
def extend_sqlglot() -> None:
    """Extend SQLGlot with SQLMesh's custom macro aware dialect."""
    parsers = {Parser}
    generators = {Generator}

    for dialect in Dialect.classes.values():
        if hasattr(dialect, "Parser"):
            parsers.add(dialect.Parser)
        if hasattr(dialect, "Generator"):
            generators.add(dialect.Generator)

    for generator in generators:
        if MacroFunc not in generator.TRANSFORMS:
            generator.TRANSFORMS.update(
                {
                    DColonCast: lambda self, e: f"{self.sql(e, 'this')}::{self.sql(e, 'to')}",
                    MacroDef: lambda self, e: f"@DEF({self.sql(e.this)}, {self.sql(e.expression)})",
                    MacroFunc: _macro_func_sql,
                    MacroStrReplace: lambda self, e: f"@{self.sql(e.this)}",
                    MacroSQL: lambda self, e: f"@SQL({self.sql(e.this)})",
                    MacroVar: lambda self, e: f"@{e.name}",
                    Model: _model_sql,
                }
            )
            generator.WITH_SEPARATED_COMMENTS = (
                *generator.WITH_SEPARATED_COMMENTS,
                Model,
            )

    for parser in parsers:
        parser.PRIMARY_PARSERS.update(
            {
                TokenType.PARAMETER: _parse_macro,
            }
        )

    _override(Parser, _parse_statement)
    _override(Parser, _parse_join)
    _override(Parser, _parse_order)
    _override(Parser, _parse_where)
    _override(Parser, _parse_group)
    _override(Parser, _parse_with)
    _override(Parser, _parse_having)
    _override(Parser, _parse_lambda)
    _override(Parser, _parse_placeholder)