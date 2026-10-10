
from scompiler.lexer import tokenize
from scompiler.tokens import TokenType


def test_keywords_and_identifiers():
    tokens, errors = tokenize("int count = 10;")

    assert not errors
    assert [token.type for token in tokens] == [
        TokenType.INT,
        TokenType.ID,
        TokenType.ASSIGN,
        TokenType.INT_LITERAL,
        TokenType.SEMICOLON,
        TokenType.EOF,
    ]


def test_float_and_operators():
    tokens, errors = tokenize("float x = 2.5 + 3 * 4;")

    assert not errors
    assert tokens[3].type == TokenType.FLOAT_LITERAL
    assert tokens[4].type == TokenType.PLUS
    assert tokens[5].type == TokenType.INT_LITERAL
    assert tokens[-1].type == TokenType.EOF


def test_comparison_operators():
    tokens, errors = tokenize("a <= 10; b != 5")

    assert not errors
    assert tokens[1].type == TokenType.LE
    assert tokens[5].type == TokenType.NE


def test_illegal_character_does_not_stop_scanning():
    tokens, errors = tokenize("int a = 5 @;")

    assert len(errors) == 1
    assert errors[0].lexeme == "@"
    assert tokens[-2].type == TokenType.SEMICOLON
    assert tokens[-1].type == TokenType.EOF


def test_malformed_number():
    tokens, errors = tokenize("int a = 12abc;")

    assert len(errors) == 1
    assert "Malformed number" in errors[0].message
    assert tokens[-2].type == TokenType.SEMICOLON


def test_unterminated_string():
    tokens, errors = tokenize('printf("hello)')

    assert len(errors) == 1
    assert "Unterminated string" in errors[0].message
    assert tokens[-1].type == TokenType.EOF


def test_line_and_column():
    tokens, errors = tokenize("int a;\nfloat b;")

    assert not errors
    assert tokens[0].line == 1
    assert tokens[3].line == 2
    assert tokens[3].col == 1


def test_multiple_lexical_errors():
    tokens, errors = tokenize("int a = @; float b = #;")

    assert len(errors) == 2
    assert errors[0].lexeme == "@"
    assert errors[1].lexeme == "#"
    assert tokens[-1].type == TokenType.EOF


def test_comments_are_ignored():
    tokens, errors = tokenize(
        "int a = 10; // this is a comment\n"
        "/* block comment */ float b = 2.5;"
    )

    assert not errors
    assert [token.type for token in tokens] == [
        TokenType.INT,
        TokenType.ID,
        TokenType.ASSIGN,
        TokenType.INT_LITERAL,
        TokenType.SEMICOLON,
        TokenType.FLOAT,
        TokenType.ID,
        TokenType.ASSIGN,
        TokenType.FLOAT_LITERAL,
        TokenType.SEMICOLON,
        TokenType.EOF,
    ]


def test_unterminated_block_comment():
    tokens, errors = tokenize("int a; /* unfinished comment")

    assert len(errors) == 1
    assert "Unterminated block comment" in errors[0].message
    assert tokens[-1].type == TokenType.EOF


def test_error_positions():
    tokens, errors = tokenize("int a;\n@")

    assert len(errors) == 1
    assert errors[0].line == 2
    assert errors[0].col == 1
