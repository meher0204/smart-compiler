from dataclasses import dataclass

from scompiler.tokens import Token, TokenType


KEYWORDS = {
    "int": TokenType.INT,
    "float": TokenType.FLOAT,
    "if": TokenType.IF,
    "else": TokenType.ELSE,
    "while": TokenType.WHILE,
    "return": TokenType.RETURN,
    "printf": TokenType.PRINTF,
}

SINGLE_CHAR_TOKENS = {
    "+": TokenType.PLUS,
    "-": TokenType.MINUS,
    "*": TokenType.STAR,
    "/": TokenType.SLASH,
    "%": TokenType.PERCENT,
    "=": TokenType.ASSIGN,
    "<": TokenType.LT,
    ">": TokenType.GT,
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
    "{": TokenType.LBRACE,
    "}": TokenType.RBRACE,
    ";": TokenType.SEMICOLON,
    ",": TokenType.COMMA,
}

DOUBLE_CHAR_TOKENS = {
    "<=": TokenType.LE,
    ">=": TokenType.GE,
    "==": TokenType.EQ,
    "!=": TokenType.NE,
}


@dataclass(frozen=True)
class LexicalError:
    message: str
    line: int
    col: int
    lexeme: str


class Lexer:
    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.col = 1
        self.tokens: list[Token] = []
        self.errors: list[LexicalError] = []

    def current(self) -> str:
        if self.pos >= len(self.source):
            return "\0"
        return self.source[self.pos]

    def peek(self, offset: int = 1) -> str:
        index = self.pos + offset
        if index >= len(self.source):
            return "\0"
        return self.source[index]

    def advance(self) -> str:
        char = self.current()

        if char == "\0":
            return char

        self.pos += 1

        if char == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1

        return char

    def add_token(
        self,
        token_type: TokenType,
        lexeme: str,
        line: int,
        col: int,
    ) -> None:
        self.tokens.append(Token(token_type, lexeme, line, col))

    def add_error(
        self,
        message: str,
        line: int,
        col: int,
        lexeme: str,
    ) -> None:
        self.errors.append(LexicalError(message, line, col, lexeme))

    def scan_identifier(self) -> None:
        line, col = self.line, self.col
        start = self.pos

        while self.current().isalnum() or self.current() == "_":
            self.advance()

        lexeme = self.source[start : self.pos]
        token_type = KEYWORDS.get(lexeme, TokenType.ID)
        self.add_token(token_type, lexeme, line, col)

    def scan_number(self) -> None:
        line, col = self.line, self.col
        start = self.pos

        while self.current().isdigit():
            self.advance()

        is_float = False

        if self.current() == ".":
            if self.peek().isdigit():
                is_float = True
                self.advance()

                while self.current().isdigit():
                    self.advance()
            else:
                # A decimal point must be followed by digits.
                self.advance()
                lexeme = self.source[start : self.pos]
                self.add_error(
                    "Malformed number: expected digits after decimal point.",
                    line,
                    col,
                    lexeme,
                )
                return

        if self.current().isalpha() or self.current() == "_":
            while self.current().isalnum() or self.current() == "_":
                self.advance()

            lexeme = self.source[start : self.pos]
            self.add_error(
                "Malformed number: unexpected letters after number.",
                line,
                col,
                lexeme,
            )
            return

        lexeme = self.source[start : self.pos]
        token_type = TokenType.FLOAT_LITERAL if is_float else TokenType.INT_LITERAL
        self.add_token(token_type, lexeme, line, col)

    def scan_string(self) -> None:
        line, col = self.line, self.col
        start = self.pos
        self.advance()  # Opening quote

        while self.current() not in ('"', "\n", "\0"):
            if self.current() == "\\" and self.peek() not in ("\0", "\n"):
                self.advance()
            self.advance()

        if self.current() != '"':
            lexeme = self.source[start : self.pos]
            self.add_error(
                "Unterminated string literal.",
                line,
                col,
                lexeme,
            )
            return

        self.advance()  # Closing quote
        lexeme = self.source[start : self.pos]

        # Strings are supported as lexical tokens for diagnostics.
        # The agreed grammar does not yet allow strings in expressions.
        self.add_error(
            "String literals are not supported by the current grammar.",
            line,
            col,
            lexeme,
        )

    def tokenize(self) -> tuple[list[Token], list[LexicalError]]:
        while self.current() != "\0":
            char = self.current()

            if char.isspace():
                self.advance()
                continue

            if char.isalpha() or char == "_":
                self.scan_identifier()
                continue

            if char.isdigit():
                self.scan_number()
                continue

            if char == '"':
                self.scan_string()
                continue

            if char == "/" and self.peek() == "/":
                while self.current() not in ("\n", "\0"):
                    self.advance()
                continue

            if char == "/" and self.peek() == "*":
                line, col = self.line, self.col
                self.advance()
                self.advance()

                while not (self.current() == "*" and self.peek() == "/") and self.current() != "\0":
                    self.advance()

                if self.current() == "\0":
                    self.add_error(
                        "Unterminated block comment.",
                        line,
                        col,
                        "/*",
                    )
                else:
                    self.advance()
                    self.advance()

                continue

            line, col = self.line, self.col
            pair = char + self.peek()

            if pair in DOUBLE_CHAR_TOKENS:
                self.advance()
                self.advance()
                self.add_token(DOUBLE_CHAR_TOKENS[pair], pair, line, col)
                continue

            if char in SINGLE_CHAR_TOKENS:
                self.advance()
                self.add_token(SINGLE_CHAR_TOKENS[char], char, line, col)
                continue

            self.advance()
            self.add_error(
                f"Illegal character: {char!r}.",
                line,
                col,
                char,
            )

        self.tokens.append(Token(TokenType.EOF, "", self.line, self.col))

        return self.tokens, self.errors


def tokenize(source: str) -> tuple[list[Token], list[LexicalError]]:
    return Lexer(source).tokenize()
