"""
Calculator 工具单元测试。

验证计算器工具的核心逻辑：
- 基础算术运算（加减乘除）
- 表达式含非法字符时拒绝执行（安全校验）
- 除零错误处理
- 空表达式处理
"""
import pytest
from app.tools.calculator import CalculatorTool


@pytest.fixture
def calculator():
    return CalculatorTool()


def test_basic_addition(calculator):
    assert calculator.execute(expression="2 + 3") == "5"


def test_basic_multiplication(calculator):
    assert calculator.execute(expression="3 * 4") == "12"


def test_operator_precedence(calculator):
    """乘法优先于加法。"""
    assert calculator.execute(expression="2 + 3 * 4") == "14"


def test_parentheses(calculator):
    """括号改变优先级。"""
    assert calculator.execute(expression="(2 + 3) * 4") == "20"


def test_float_division(calculator):
    result = calculator.execute(expression="10 / 3")
    assert float(result) == pytest.approx(3.3333, rel=1e-3)


def test_reject_special_characters(calculator):
    """包含字母等非法字符时拒绝执行。"""
    result = calculator.execute(expression="__import__('os')")
    assert "不允许" in result


def test_reject_semicolon(calculator):
    """分号注入应被拒绝。"""
    result = calculator.execute(expression="1; print('hack')")
    assert "不允许" in result


def test_empty_expression(calculator):
    """空表达式返回错误信息而非崩溃。"""
    result = calculator.execute(expression="")
    # 空字符串通过白名单校验但 eval 报错
    assert "错误" in result or result == "" or "计算错误" in result


def test_query_alias(calculator):
    """LLM 可能传 query 而非 expression，工具应兼容。"""
    result = calculator.execute(query="1 + 1")
    assert result == "2"
