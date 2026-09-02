"""检索准确率评估脚本（多文档基准）

评价方式：对每个问题跑真实检索（embedding + Chroma），看：
- 内容命中 hit@k / recall@k：答案原文（子串）有没有出现在 top-k 里
- 来源命中 src@k：应命中的来源文件有没有出现在 top-k 里（多文档才有意义）

为什么加"来源命中"：多文档下，内容命中可能"碰运气"（答案词多处出现），
来源命中才证明"真的从那份对的文档里捞出来的"。

「硬/软」标记：hard=True = 答案/来源唯一、确实考验检索；
hard=False = 全文到处都是，撞上也不算数（会虚高）。--hard 只跑硬题。

用法：docker exec -i -w /app copilot-backend python - < backend/scripts/eval_retrieval.py --hard --k 8
"""

import sys

from app.services.retrieval_service import retrieval_service

# (问题, 答案原文子串, 是否硬题, 应命中来源文件)
BENCHMARK = [
    # ===== 半年报 1225485674.pdf（原有 14 硬题，看是否被新文档干扰）=====
    ("北矿科技的公司代码是多少？", "600980", True, "1225485674.pdf"),
    ("北矿科技公司外文名称是什么？", "BGRIMM", True, "1225485674.pdf"),
    ("公司上半年营业总收入是多少万元？", "65,739.50", True, "1225485674.pdf"),
    ("上半年归属于上市公司股东的净利润是多少万元？", "6,825.99", True, "1225485674.pdf"),
    ("基本每股收益是多少元？", "0.3594", True, "1225485674.pdf"),
    ("公司的控股股东是谁？", "矿冶科技集团", False, "1225485674.pdf"),
    ("公司注册地址位于什么路多少号？", "南四环西路188号", False, "1225485674.pdf"),
    ("公司董事长兼总经理是谁？", "卢世杰", False, "1225485674.pdf"),
    ("上半年公司增值税税率是多少？", "13%", True, "1225485674.pdf"),
    ("子公司北矿机电的企业所得税税率是多少？", "15.00", True, "1225485674.pdf"),
    ("公司总股本是多少万股？", "19,326.3526", True, "1225485674.pdf"),
    ("截至报告期末普通股股东总数是多少户？", "26,783", True, "1225485674.pdf"),
    ("公司两大核心主业之一是什么？", "磁性材料", False, "1225485674.pdf"),
    ("2025年限制性股票激励计划激励对象有多少人？", "113", True, "1225485674.pdf"),
    ("收到控股股东实施限制性股票激励计划批复的日期？", "2026年4月13日", True, "1225485674.pdf"),
    ("财务报表经公司董事会批准报出的日期？", "2026年8月20日", True, "1225485674.pdf"),
    ("哪位董事、副总经理因达到法定退休年龄辞职？", "李炳山", True, "1225485674.pdf"),
    ("每10股派息多少元（含税）？", "0.55", True, "1225485674.pdf"),
    ("公司生产销售浮选设备属于哪块业务？", "矿冶装备", False, "1225485674.pdf"),
    ("公司股票上市交易所是哪里？", "上海证券交易所", False, "1225485674.pdf"),
    # ===== T0016 QSG_V1.pdf（FreeBuds SE2 快速指南）=====
    ("HUAWEI FreeBuds SE 2 的耳机型号是什么？", "T0016", True, "T0016 QSG_V1.pdf"),
    ("FreeBuds SE 2 耳机的电池容量是多少？", "41mAh", True, "T0016 QSG_V1.pdf"),
    ("充电盒的充电接口是什么类型？", "USB-C", True, "T0016 QSG_V1.pdf"),
    ("这款耳机支持什么防护等级？", "IP54", True, "T0016 QSG_V1.pdf"),
    ("产品制造商是哪家公司？", "華為終端", True, "T0016 QSG_V1.pdf"),
    ("客户服务电话是多少？", "412-8848", True, "T0016 QSG_V1.pdf"),
    # ===== 真实用户长问（Day 26：工整短问测不出，真实长问才露馅）=====
    # 带产品全名/前后缀长，会把问题引向标题chunk(idx0/idx1)，答案却在规格chunk(idx5)，
    # 两者竞争正是"工整短问"测不出的点——Day 26 的"充电接口"就是栽在这。
    ("HUAWEI FreeBuds SE 2的充电盒充电接口到底是什么类型？", "USB-C", True, "T0016 QSG_V1.pdf"),
    ("我上传的这份 FreeBuds SE 2 快速指南里,耳机电池容量有多大？", "41mAh", True, "T0016 QSG_V1.pdf"),
    ("北矿科技这个半年报里,公司总股本一共有多少万股？", "19,326.3526", True, "1225485674.pdf"),
    ("文物建筑防火设计规范里,文物保护单位范围内严禁设置什么？", "易燃易爆场所", True, "DB11!~1706-2019.pdf"),
    # ===== DB11!~1706-2019.pdf（文物建筑防火设计规范）=====
    ("《文物建筑防火设计规范》适用于什么结构的建筑？", "木结构、砖木结构", True, "DB11!~1706-2019.pdf"),
    ("本规范的实施日期是哪天？", "2020-04-01", True, "DB11!~1706-2019.pdf"),
    ("文物保护单位范围内严禁设置什么？", "易燃易爆场所", True, "DB11!~1706-2019.pdf"),
    ("本规范的主编单位包括哪一家？", "北京市消防救援总队", True, "DB11!~1706-2019.pdf"),
    ("文物建筑消防设计应遵循什么原则？", "预防为主、防消结合", True, "DB11!~1706-2019.pdf"),
]

DEFAULT_K = 5


def _strip(src: str) -> str:
    """去掉图检索加的 [图] 前缀，再去和应命中来源比对"""
    return src.lstrip("[").split("]")[-1]


def eval_single(question: str, answer: str, source: str, k: int) -> dict:
    """检索一次，返回内容命中的位置(1起) 和 应命中来源出现的位置(1起)，None=没找到"""
    chunks = retrieval_service.search(question, k=k)
    content_rank = src_rank = None
    for i, chunk in enumerate(chunks, start=1):
        text = chunk.get("text") or ""
        src = _strip(chunk.get("source") or "")
        if content_rank is None and answer in text:
            content_rank = i
        if src_rank is None and source and source in src:
            src_rank = i
    return {
        "content_rank": content_rank,
        "src_rank": src_rank,
        "first_text": (chunks[0].get("text") or "")[:22],
    }


def main() -> None:
    argv = sys.argv[1:]
    hard_only = "--hard" in argv
    k = int(argv[argv.index("--k") + 1]) if "--k" in argv else DEFAULT_K

    bench = BENCHMARK if not hard_only else [x for x in BENCHMARK if x[2]]
    n = len(bench)

    hit = {hk: 0 for hk in (1, 3, 5)}
    src = {hk: 0 for hk in (1, 3, 5)}
    content_found = src_found = 0
    mrrs = []

    print(f"基准：{n} 题（{'仅硬题' if hard_only else '全部'}），K={k}\n")
    print(f"{'问题':<36}{'内容':<6}{'来源':<5}{'首片预览'}")
    print("-" * 76)

    for question, answer, _, expect_src in bench:
        r = eval_single(question, answer, expect_src, k)
        cr, sr = r["content_rank"], r["src_rank"]
        for hk in hit:
            if cr is not None and cr <= hk:
                hit[hk] += 1
            if sr is not None and sr <= hk:
                src[hk] += 1
        if cr is not None:
            content_found += 1
            mrrs.append(1.0 / cr)
        if sr is not None:
            src_found += 1
        cmark = f"✔#{cr}" if cr is not None else "✘"
        smark = f"✔#{sr}" if sr is not None else "✘"
        print(f"{question:<36}{cmark:<6}{smark:<5}{r['first_text'].replace(chr(10), ' / ')}")

    print("-" * 76)
    for hk in (1, 3, 5):
        print(f"hit@   {hk} 内容命中 = {hit[hk]}/{n} = {hit[hk] / n:.1%}")
    for hk in (1, 3, 5):
        print(f"src@   {hk} 来源命中 = {src[hk]}/{n} = {src[hk] / n:.1%}")
    print(f"recall@{k} 内容进 top-{k} = {content_found}/{n} = {content_found / n:.1%}")
    print(f"src@{k}  应命中来源进 top-{k} = {src_found}/{n} = {src_found / n:.1%}")
    print(f"MRR   内容 = {sum(mrrs) / n:.3f}")


if __name__ == "__main__":
    main()
