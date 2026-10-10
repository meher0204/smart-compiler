
from scompiler.lexer import tokenize
from scompiler.tokens import Token, TokenType


class ParseError(Exception):
    def __init__(self, message, token):
        self.message = message
        self.token = token
        super().__init__(message)


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        self.errors = []

    def current(self):
        return self.tokens[self.pos]

    def check(self, *types):
        return self.current().type in types

    def advance(self):
        token = self.current()
        if token.type != TokenType.EOF:
            self.pos += 1
        return token

    def match(self, *types):
        if self.check(*types):
            return self.advance()
        return None

    def expect(self, token_type):
        if self.check(token_type):
            return self.advance()

        token = self.current()
        expected = token_type.value
        found = token.lexeme if token.type != TokenType.EOF else "EOF"
        raise ParseError(
            f"Line {token.line}, column {token.col}: "
            f"expected {expected}, found {found}",
            token,
        )

    def parse(self):
        self.program()
        self.expect(TokenType.EOF)
        return True

    # Program -> DeclarationList
    def program(self):
        while not self.check(TokenType.EOF):
            old_pos = self.pos
            try:
                self.declaration()
            except ParseError as error:
                self.errors.append(error.message)
                self.synchronize()
            if self.pos == old_pos:
                self.advance()

    def declaration(self):
        if self.check(TokenType.INT, TokenType.FLOAT):
            self.advance()
            self.expect(TokenType.ID)

            if self.match(TokenType.LPAREN):
                self.param_list()
                self.expect(TokenType.RPAREN)
                self.block()
            else:
                if self.match(TokenType.ASSIGN):
                    self.expr()
                self.expect(TokenType.SEMICOLON)
        else:
            token = self.current()
            found = token.lexeme if token.type != TokenType.EOF else "EOF"
            raise ParseError(
                f"Line {token.line}, column {token.col}: "
                f"expected declaration or function, found {found}",
                token,
            )

    def param_list(self):
        if self.check(TokenType.INT, TokenType.FLOAT):
            self.param()
            while self.match(TokenType.COMMA):
                self.param()

    def param(self):
        self.expect_any(TokenType.INT, TokenType.FLOAT)
        self.expect(TokenType.ID)

    def statement(self):
        if self.check(TokenType.INT, TokenType.FLOAT):
            self.declaration()
        elif self.check(TokenType.ID):
            if self.pos + 1 < len(self.tokens) and (
                self.tokens[self.pos + 1].type == TokenType.ASSIGN
            ):
                self.assignment()
            else:
                self.expr()
                self.expect(TokenType.SEMICOLON)
        elif self.match(TokenType.IF):
            self.expect(TokenType.LPAREN)
            self.expr()
            self.expect(TokenType.RPAREN)
            self.statement()
            if self.match(TokenType.ELSE):
                self.statement()
        elif self.match(TokenType.WHILE):
            self.expect(TokenType.LPAREN)
            self.expr()
            self.expect(TokenType.RPAREN)
            self.statement()
        elif self.match(TokenType.RETURN):
            if not self.check(TokenType.SEMICOLON):
                self.expr()
            self.expect(TokenType.SEMICOLON)
        elif self.match(TokenType.PRINTF):
            self.expect(TokenType.LPAREN)
            self.expr()
            self.expect(TokenType.RPAREN)
            self.expect(TokenType.SEMICOLON)
        elif self.match(TokenType.LBRACE):
            while not self.check(TokenType.RBRACE, TokenType.EOF):
                old_pos = self.pos
                self.statement()
                if self.pos == old_pos:
                    self.advance()
            self.expect(TokenType.RBRACE)
        else:
            self.expr()
            self.expect(TokenType.SEMICOLON)

    def assignment(self):
        self.expect(TokenType.ID)
        self.expect(TokenType.ASSIGN)
        self.expr()
        self.expect(TokenType.SEMICOLON)

    def block(self):
        self.expect(TokenType.LBRACE)
        while not self.check(TokenType.RBRACE, TokenType.EOF):
            old_pos = self.pos
            try:
                self.statement()
            except ParseError as error:
                self.errors.append(error.message)
                self.synchronize()
            if self.pos == old_pos:
                self.advance()
        self.expect(TokenType.RBRACE)

    def expr(self):
        self.add_expr()
        if self.match(
            TokenType.LT, TokenType.GT,
            TokenType.LE, TokenType.GE,
            TokenType.EQ, TokenType.NE
        ):
            self.add_expr()

    def add_expr(self):
        self.mul_expr()
        while self.match(TokenType.PLUS, TokenType.MINUS):
            self.mul_expr()

    def mul_expr(self):
        self.unary_expr()
        while self.match(
            TokenType.STAR, TokenType.SLASH, TokenType.PERCENT
        ):
            self.unary_expr()

    def unary_expr(self):
        if self.match(TokenType.PLUS, TokenType.MINUS):
            self.unary_expr()
        else:
            self.primary()

    def primary(self):
        if self.match(TokenType.ID):
            if self.match(TokenType.LPAREN):
                self.arg_list()
                self.expect(TokenType.RPAREN)
        elif self.match(TokenType.INT_LITERAL, TokenType.FLOAT_LITERAL):
            pass
        elif self.match(TokenType.LPAREN):
            self.expr()
            self.expect(TokenType.RPAREN)
        else:
            token = self.current()
            found = token.lexeme if token.type != TokenType.EOF else "EOF"
            raise ParseError(
                f"Line {token.line}, column {token.col}: "
                f"expected expression, found {found}",
                token,
            )

    def arg_list(self):
        if not self.check(TokenType.RPAREN):
            self.expr()
            while self.match(TokenType.COMMA):
                self.expr()

    def expect_any(self, *types):
        if self.check(*types):
            return self.advance()
        token = self.current()
        expected = " or ".join(t.value for t in types)
        found = token.lexeme if token.type != TokenType.EOF else "EOF"
        raise ParseError(
            f"Line {token.line}, column {token.col}: "
            f"expected {expected}, found {found}",
            token,
        )

    
    def synchronize(self):
        while not self.check(TokenType.EOF):
            if self.check(TokenType.RBRACE):
                return

            if self.match(TokenType.SEMICOLON):
                return

            if self.check(
                TokenType.INT,
                TokenType.FLOAT,
                TokenType.IF,
                TokenType.WHILE,
                TokenType.RETURN,
                TokenType.PRINTF,
            ):
                return

            self.advance()



def parse_source(source):
    tokens, lexical_errors = tokenize(source)
    parser = Parser(tokens)

    try:
        parser.parse()
    except ParseError as error:
        parser.errors.append(error.message)

    return {
        "success": not lexical_errors and not parser.errors,
        "errors": [error.message for error in lexical_errors]
        + parser.errors,
    }
