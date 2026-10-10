
from scompiler.parser import parse_source


def test_valid_declaration():
    result = parse_source("int x = 10;")
    assert result["success"] is True


def test_valid_function():
    source = "int main() { return 0; }"
    result = parse_source(source)
    assert result["success"] is True


def test_valid_expression():
    result = parse_source("int x = (2 + 3) * 4;")
    assert result["success"] is True


def test_valid_if_else():
    source = "int main() { int x = 5; if (x > 0) return x; else return 0; }"
    result = parse_source(source)
    assert result["success"] is True


def test_valid_while():
    source = "int main() { int x = 0; while (x < 5) x = x + 1; return x; }"
    result = parse_source(source)
    assert result["success"] is True


def test_valid_function_call():
    source = "int add(int a, int b) { return a + b; }"
    result = parse_source(source)
    assert result["success"] is True


def test_missing_expression():
    result = parse_source("int x = ;")
    assert result["success"] is False
    assert result["errors"]


def test_missing_semicolon():
    result = parse_source("int x = 10")
    assert result["success"] is False
    assert result["errors"]


def test_unclosed_parenthesis():
    result = parse_source("int x = (2 + 3;")
    assert result["success"] is False
    assert result["errors"]


def test_invalid_character():
    result = parse_source("int x = @;")
    assert result["success"] is False
    assert result["errors"]
def test_return_outside_function():
    result = parse_source("return 5;")
    assert result["success"] is False
    assert result["errors"]