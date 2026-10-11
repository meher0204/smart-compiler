from scompiler.diagnostics import Diagnostic, DiagnosticCollector
from scompiler.parser import parse_source
from scompiler.report import ErrorReport
from scompiler.suggest import suggest


def test_valid_source_zero_errors():
    source = """
    int main() {
        int x = 10;
        int y = 20;
        if (x < y) {
            return x + y;
        }
        return 0;
    }
    """
    result = parse_source(source)
    assert result.success is True
    assert len(result.errors) == 0
    assert "Compilation succeeded with no errors." in result.report


def test_single_missing_semicolon():
    source = """
    int main() {
        int x = 10
        int y = 20;
        return x + y;
    }
    """
    result = parse_source(source)
    assert result.success is False
    assert len(result.diagnostics) == 1
    diag = result.diagnostics[0]
    assert diag.expected == ";"
    assert "Insert ';'" in diag.suggestion
    assert "Continued parsing from the next statement" in diag.recovery_info


def test_missing_closing_parenthesis():
    source = """
    int main() {
        int x = 5;
        if (x > 0 {
            return x;
        }
        return 0;
    }
    """
    result = parse_source(source)
    assert result.success is False
    assert len(result.diagnostics) == 1
    diag = result.diagnostics[0]
    assert diag.expected == ")"
    assert "Insert ')'" in diag.suggestion


def test_missing_closing_brace():
    source = """
    int main() {
        int x = 5;
        return x;
    """
    result = parse_source(source)
    assert result.success is False
    assert any(d.expected == "}" for d in result.diagnostics)
    assert any("Insert '}'" in d.suggestion for d in result.diagnostics if d.suggestion)


def test_multiple_independent_syntax_errors():
    source = """
    int main() {
        int a = 10
        int b = ;
        int c = 30
        return a + c;
    }
    """
    result = parse_source(source)
    assert result.success is False
    assert len(result.diagnostics) >= 3
    # Check that later statement 'int c = 30' was also reached and checked
    assert any("30" in d.suggestion or d.line >= 4 for d in result.diagnostics)


def test_error_inside_nested_block():
    source = """
    int main() {
        int x = 10;
        if (x > 0) {
            while (x > 5) {
                int z = ;
                x = x - 1;
            }
            int after = 100;
        }
        return 0;
    }
    """
    result = parse_source(source)
    assert result.success is False
    # Error should be found on 'int z = ;'
    assert any("expression" in d.message.lower() for d in result.diagnostics)
    # Recovery should allow continuing out of while and parsing 'int after = 100;' and 'return 0;'


def test_error_followed_by_valid_statements_parsed():
    source = """
    int foo() {
        int bad = ;
        int valid1 = 42;
        int valid2 = 84;
        return valid1 + valid2;
    }
    """
    result = parse_source(source)
    assert result.success is False
    # Only 1 error for the bad line
    assert len(result.diagnostics) == 1
    assert "expression" in result.diagnostics[0].message.lower()


def test_unexpected_token_panic_mode_recovery():
    source = """
    int main() {
        int @@@ invalid tokens %%% ;
        int recovered = 50;
        return recovered;
    }
    """
    result = parse_source(source)
    assert result.success is False
    # Lexical and/or syntax errors detected, but parsing recovers to valid declaration
    assert len(result.diagnostics) >= 1
    assert "SMART COMPILER — ERROR REPORT" in result.report


def test_error_near_eof():
    source = "int main() { return"
    result = parse_source(source)
    assert result.success is False
    assert len(result.diagnostics) >= 1


def test_cascading_duplicate_suppression():
    collector = DiagnosticCollector(max_errors=20)
    # Adding exact duplicate
    diag1 = Diagnostic(
        code="E001", message="Missing semicolon", line=5, column=10, category="syntax"
    )
    diag2 = Diagnostic(
        code="E001", message="Missing semicolon", line=5, column=10, category="syntax"
    )
    assert collector.add(diag1) is True
    assert collector.add(diag2) is False
    assert collector.suppressed == 1
    assert collector.error_count == 1


def test_lexical_error_followed_by_syntax_error():
    source = """
    int a = 5 @;
    int b = ;
    """
    result = parse_source(source)
    assert result.success is False
    categories = [d.category for d in result.diagnostics]
    assert "lexical" in categories
    assert "syntax" in categories


def test_rule_based_suggestions():
    d1 = Diagnostic(
        code="MISSING_SEMICOLON", message="Missing semicolon", line=1, column=5, lexeme="x"
    )
    assert "Insert ';'" in suggest(d1)

    d2 = Diagnostic(
        code="MISSING_RPAREN", message="Expected ')' to close condition", line=2, column=10
    )
    assert "Insert ')'" in suggest(d2)

    d3 = Diagnostic(code="MISSING_RBRACE", message="Unclosed block", line=3, column=1)
    assert "Insert '}'" in suggest(d3)

    d4 = Diagnostic(
        code="SYNTAX_ERROR", message="Unexpected token", line=4, column=5, lexeme="whiel"
    )
    assert "while" in suggest(d4)


def test_report_formatting():
    collector = DiagnosticCollector()
    collector.add_syntax_error(
        message="Expected ';' after variable declaration.",
        line=4,
        column=15,
        lexeme="int",
        expected=";",
        suggestion="Insert ';' after the previous statement.",
        recovery_info="Continued parsing from the next statement.",
    )
    report = ErrorReport(collector).render()
    assert "SMART COMPILER — ERROR REPORT" in report
    assert "Total errors: 1" in report
    assert "[Syntax Error] Line 4, Column 15" in report
    assert "Message: Expected ';' after variable declaration." in report
    assert "Expected: ';'" in report
    assert "Found: 'int'" in report
    assert "Suggestion: Insert ';' after the previous statement." in report
    assert "Recovery: Continued parsing from the next statement." in report
    assert "Compilation completed with errors. Recovery was attempted." in report
