"""计算器工具 — 安全地计算数学表达式。"""
from app.tools.base import BaseAgentTool


class CalculatorTool(BaseAgentTool):
    def __init__(self):
        super().__init__(
            tool_id="calculator",
            name="calculator",
            description="计算数学表达式。输入一个数学表达式字符串，返回计算结果。例如: '2 + 3 * 4'",
        )

    def execute(self, **kwargs) -> str:
        """执行数学计算。通过白名单字符过滤防止代码注入。"""
        expression = kwargs.get("expression", kwargs.get("query", ""))
        # 白名单过滤：只允许数字、运算符、括号和空格
        allowed = set("0123456789+-*/.() ")
        if not all(c in allowed for c in expression):
            return f"错误：表达式包含不允许的字符: {expression}"
        try:
            result = eval(expression, {"__builtins__": {}}, {})
            return str(result)
        except Exception as e:
            return f"计算错误: {e}"
