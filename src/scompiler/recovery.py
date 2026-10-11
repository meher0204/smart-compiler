"""recovery.py - Panic-mode and phrase-level error recovery for Smart Compiler.

Implements fault-tolerant parsing recovery mechanisms:
1. Synchronization sets tailored to the language grammar.
2. Phrase-level recovery for common missing delimiters (; , ) , }).
3. Panic-mode token skipping to the nearest safe synchronization boundary.
4. Cascading error suppression and infinite loop prevention.
"""

from __future__ import annotations

from typing import Optional, Set

from scompiler.tokens import Token, TokenType


# Language-specific synchronization token sets
STATEMENT_STARTERS: Set[TokenType] = {
    TokenType.INT,
    TokenType.FLOAT,
    TokenType.IF,
    TokenType.WHILE,
    TokenType.RETURN,
    TokenType.PRINTF,
    TokenType.LBRACE,
}

STATEMENT_SYNC: Set[TokenType] = STATEMENT_STARTERS | {
    TokenType.SEMICOLON,
    TokenType.RBRACE,
    TokenType.EOF,
}

EXPR_SYNC: Set[TokenType] = {
    TokenType.SEMICOLON,
    TokenType.RPAREN,
    TokenType.RBRACE,
    TokenType.COMMA,
    TokenType.EOF,
}

BLOCK_SYNC: Set[TokenType] = {
    TokenType.RBRACE,
    TokenType.EOF,
}


class RecoveryManager:
    """Manages error recovery state and strategies for the recursive descent parser."""

    def __init__(self, parser) -> None:
        self.parser = parser
        self.in_panic_mode: bool = False
        self.last_error_pos: int = -1
        self.recovery_count: int = 0

    def begin_recovery(self) -> None:
        """Mark that an error occurred and panic recovery is active."""
        self.in_panic_mode = True
        self.last_error_pos = self.parser.pos

    def end_recovery(self) -> None:
        """Reset panic mode after successfully reaching a synchronization boundary."""
        self.in_panic_mode = False

    def should_report_error(self, token_pos: int) -> bool:
        """Check if an error at `token_pos` should be reported to avoid cascading duplicates."""
        if self.in_panic_mode and token_pos == self.last_error_pos:
            return False
        return True

    # ---- Phrase-level Virtual Insertion Recoveries ------------------------

    def try_recover_missing_semicolon(self, prev_token: Optional[Token]) -> bool:
        """Attempt phrase-level recovery for a missing semicolon.

        If the next token is a clear statement boundary (a new statement keyword,
        a closing brace, or EOF), virtually insert ';' and continue parsing.
        """
        curr = self.parser.current()

        if curr.type in STATEMENT_SYNC:
            line = prev_token.line if prev_token else curr.line
            col = (prev_token.col + len(prev_token.lexeme)) if prev_token else curr.col
            prev_lex = prev_token.lexeme if prev_token else "statement"

            self.parser.collector.add_syntax_error(
                code="MISSING_SEMICOLON",
                message="Expected ';' after statement or declaration.",
                line=line,
                column=col,
                lexeme=curr.lexeme if curr.type != TokenType.EOF else "EOF",
                expected=";",
                suggestion=f"Insert ';' after '{prev_lex}'.",
                recovery_info="Continued parsing from the next statement.",
            )
            self.recovery_count += 1
            self.end_recovery()
            return True

        return False

    def try_recover_missing_rparen(
        self,
        open_paren: Optional[Token] = None,
        context: str = "condition or expression",
    ) -> bool:
        """Attempt phrase-level recovery for a missing closing parenthesis ')'.

        If the next token clearly begins a block ('{'), statement, or semicolon,
        virtually insert ')' and continue without skipping tokens.
        """
        curr = self.parser.current()

        if curr.type in (
            TokenType.LBRACE,
            TokenType.SEMICOLON,
            TokenType.INT,
            TokenType.FLOAT,
            TokenType.IF,
            TokenType.WHILE,
            TokenType.RETURN,
            TokenType.PRINTF,
            TokenType.EOF,
        ):
            related = (open_paren.line, open_paren.col) if open_paren else None
            self.parser.collector.add_syntax_error(
                code="MISSING_RPAREN",
                message=f"Expected ')' to close {context}.",
                line=curr.line,
                column=curr.col,
                lexeme=curr.lexeme if curr.type != TokenType.EOF else "EOF",
                expected=")",
                suggestion="Insert ')' to close the condition."
                if "condition" in context
                else "Insert ')'.",
                recovery_info="Continued parsing after virtually closing parenthesis.",
                related=related,
            )
            self.recovery_count += 1
            self.end_recovery()
            return True

        return False

    def try_recover_missing_rbrace(
        self,
        open_brace: Optional[Token] = None,
    ) -> bool:
        """Attempt phrase-level recovery for an unclosed block brace '}'."""
        curr = self.parser.current()
        related = (open_brace.line, open_brace.col) if open_brace else None

        self.parser.collector.add_syntax_error(
            code="UNCLOSED_BLOCK",
            message="Unclosed block; expected '}'.",
            line=curr.line,
            column=curr.col,
            lexeme=curr.lexeme if curr.type != TokenType.EOF else "EOF",
            expected="}",
            suggestion="Insert '}' before the end of the file."
            if curr.type == TokenType.EOF
            else "Insert '}' to close the block.",
            recovery_info="Continued parsing after virtually closing block.",
            related=related,
        )
        self.recovery_count += 1
        self.end_recovery()
        return True

    # ---- Panic-Mode Synchronization --------------------------------------

    def synchronize_statement(self) -> None:
        """Advance the token stream until reaching a safe statement boundary."""
        self.begin_recovery()

        while not self.parser.check(TokenType.EOF):
            # If at a block end, do not consume it; let enclosing block handle it
            if self.parser.check(TokenType.RBRACE):
                self.end_recovery()
                return

            # If at a semicolon, consume it to complete the failed statement
            if self.parser.check(TokenType.SEMICOLON):
                self.parser.advance()
                self.end_recovery()
                return

            # If at the start of a new statement, stop so it can be parsed
            if self.parser.check(*STATEMENT_STARTERS):
                self.end_recovery()
                return

            self.parser.advance()

        self.end_recovery()

    def synchronize_to(self, sync_tokens: Set[TokenType], consume: bool = False) -> None:
        """Advance until the current token type matches one in `sync_tokens` or EOF."""
        self.begin_recovery()

        while not self.parser.check(TokenType.EOF):
            if self.parser.current().type in sync_tokens:
                if consume and not self.parser.check(TokenType.RBRACE, TokenType.EOF):
                    self.parser.advance()
                self.end_recovery()
                return
            self.parser.advance()

        self.end_recovery()
