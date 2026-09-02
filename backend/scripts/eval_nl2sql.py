"""NL2SQL 批量评估（Day 26）：用真实 orders 数据测"自然语言 → SQL → 答对"效果

对照 RAG 的 eval_retrieval：RAG 测的是"检索到答案chunk"，这里测的是
"模型把自然语言生成正确 SQL 并在真实库上查出正确答案"。

判分用"答案正确性"而不是"SQL 和你写的一不一样"——模型可能有等价写法，
只要查出的数值和真值对上就算对。真值由基准 SQL 在真实库上现算。

用法（容器内，需 MySQL + LLM key）：
    docker exec copilot-backend python /app/eval_nl2sql.py
输出：每题 ✓/✗ + 模型 SQL + 命中统计（SQL合法 / 执行成功 / 答案正确）。
"""

import json
import re
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import text

from app.agent.tools import build_tools, _query_data
from app.ai.llm import llm_service
from app.database.session import SessionLocal

# (问题, 基准SQL[在真实库上算真值])
CASES = [
    ("订单总数是多少？", "SELECT COUNT(*) AS v FROM orders"),
    ("SP 州有多少笔订单？", "SELECT COUNT(*) AS v FROM orders WHERE department='SP'"),
    ("SP 州的订单总金额是多少？", "SELECT SUM(amount) AS v FROM orders WHERE department='SP'"),
    ("哪个州卖出最多订单？", "SELECT department AS v FROM orders GROUP BY department ORDER BY COUNT(*) DESC LIMIT 1"),
    ("哪个州订单总金额最高？", "SELECT department AS v FROM orders GROUP BY department ORDER BY SUM(amount) DESC LIMIT 1"),
    ("RJ 州的订单总金额是多少？", "SELECT SUM(amount) AS v FROM orders WHERE department='RJ'"),
    ("平均每笔订单金额是多少？", "SELECT AVG(amount) AS v FROM orders"),
    ("金额超过 1000 元的订单有多少笔？", "SELECT COUNT(*) AS v FROM orders WHERE amount > 1000"),
    ("订单金额最大的部门是哪个（只看部门）？", "SELECT department AS v FROM orders ORDER BY amount DESC LIMIT 1"),
    ("2017 年的订单有多少笔？", "SELECT COUNT(*) AS v FROM orders WHERE YEAR(created_at)=2017"),
    ("2017 年 SP 州的订单总金额是多少？", "SELECT SUM(amount) AS v FROM orders WHERE YEAR(created_at)=2017 AND department='SP'"),
    ("MG 州有多少笔订单？", "SELECT COUNT(*) AS v FROM orders WHERE department='MG'"),
    ("金额在 100 到 500 之间的订单有多少笔？", "SELECT COUNT(*) AS v FROM orders WHERE amount BETWEEN 100 AND 500"),
    ("最早的一笔订单是哪个州的？", "SELECT department AS v FROM orders ORDER BY created_at LIMIT 1"),
    ("SP 州订单里最多的单笔金额是多少？", "SELECT MAX(amount) AS v FROM orders WHERE department='SP'"),
]


def _truth(db, sql):
    """跑基准 SQL 拿真值（标量或字符串），失败返回 None"""
    try:
        row = db.execute(text(sql)).fetchone()
        if row is None:
            return None
        return row[0]
    except Exception:
        return None


def _num(x):
    """把可能的值转成可比较的浮点（容差判定用）"""
    if isinstance(x, Decimal):
        return float(x)
    if isinstance(x, (int, float)):
        return float(x)
    return x


def _model_sql(question, desc):
    """让模型按 query_data 描述生成一条 SQL，返回 SQL 或 None"""
    system = desc + "\n\n只输出一条 SELECT 语句，不要任何解释、不要 Markdown、不要分号。"
    raw = (llm_service.chat(system, "", question) or "").strip()
    m = re.search(r"select\b.*", raw, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    return m.group(0).strip().rstrip(";").strip()


def _hit(truth, result_rows):
    """真值是否出现在模型结果里：数值容差 0.01，字符串直接比对"""
    if truth is None:
        return False
    t = _num(truth)
    if isinstance(t, str):
        return any(t in str(c) for row in result_rows for c in row.values())
    for row in result_rows:
        for c in row.values():
            n = _num(c)
            if isinstance(n, (int, float)) and abs(n - t) < 0.01:
                return True
    return False


def main() -> None:
    admin = SimpleNamespace(role="admin", department=None)
    desc = [t for t in build_tools() if t["function"]["name"] == "query_data"][0]["function"]["description"]
    db = SessionLocal()

    # 1. 算每题真值
    truths = {q: _truth(db, sql) for q, sql in CASES}

    legit = exec_ok = correct = 0
    print(f"{'问题':<28}{'合法':<4}{'执行':<4}{'正确':<4}  真值 / 模型SQL")
    print("-" * 110)
    for q, _ in CASES:
        t = truths[q]
        sql = _model_sql(q, desc)
        if not sql:
            print(f"{q:<28}{'✘':<4}{'-':<4}{'-':<4}  true={t} 模型没生成SQL/生成非select")
            continue
        ok_legit = True
        res = _query_data(db, sql, admin)
        if "error" in res:
            print(f"{q:<28}{'✘':<4}{'-':<4}{'-':<4}  true={t}  [白名单/执行拒] {sql[:60]} -> {res['error'][:30]}")
            continue
        legit += 1
        exec_ok += 1
        rows = res.get("rows", [])
        hit = _hit(t, rows)
        if hit:
            correct += 1
        mark = "✔" if hit else "✘"
        print(f"{q:<28}{'✔':<4}{'✔':<4}{mark:<4}  true={t}  SQL={sql[:70]}")

    n = len(CASES)
    print("-" * 110)
    print(f"共 {n} 题：SQL 合法/执行 {legit}，答案正确 {correct} = {correct / n:.1%}")
    db.close()


if __name__ == "__main__":
    main()
