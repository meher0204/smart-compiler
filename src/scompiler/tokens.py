
from dataclasses import dataclass
from enum import Enum


class TokenType(str, Enum):
    # Keywords
    INT = "INT"
    FLOAT = "FLOAT"
    IF = "IF"
    ELSE = "ELSE"
    WHILE = "WHILE"
    RETURN = "RETURN"
    PRINTF = "PRINTF"

    # Identifiers and literals
    ID = "ID"
    INT_LITERAL = "INT_LITERAL"
    FLOAT_LITERAL = "FLOAT_LITERAL"

    # Arithmetic operators
    PLUS = "PLUS"
    MINUS = "MINUS"
    STAR = "STAR"
    SLASH = "SLASH"
    PERCENT = "PERCENT"

    # Comparison and assignment operators
    ASSIGN = "ASSIGN"
    LT = "LT"
    GT = "GT"
    LE = "LE"
    GE = "GE"
    EQ = "EQ"
    NE = "NE"

    # Parentheses and punctuation
    LPAREN = "LPAREN"
    RPAREN = "RPAREN"
    LBRACE = "LBRACE"
    RBRACE = "RBRACE"
    SEMICOLON = "SEMICOLON"
    COMMA = "COMMA"

    # End of input
    EOF = "EOF"


@dataclass(frozen=True)
class Token:
    type: TokenType
    lexeme: str
    line: int
    col: int
