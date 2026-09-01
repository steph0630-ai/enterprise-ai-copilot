"""BM25 关键词检索（无第三方依赖，纯 stdlib）

给"向量检索候选池"做关键词重排用（Day 25 hybrid 重排）。

为什么需要它：向量只懂"语义形似"，对"正好含这个数字/型号/代码的 chunk"
跟别的相似 chunk 分不清（实测 IP54、412-8848、600980 常被排到 #4~#8）。
BM25 按字面精确命中，专门补这个。

两个约定：
- tokenize 重点照顾"短精确 token"（412-8848、0.3594、IP54、13%）+ 中文。
  中文按单字切（unigram）：中文没空格，单字 unigram 就能让"客户服务电话"这类
  查询命中，无需引 jieba 这类大依赖。
- 索引全量拉语料、惰性构建 + 脏标记（invalidate）。当前 ~700 chunk 足够；
  语料到几万级要改增量/持久化（见 eval_retrieval 的 ponytail 注释）。
"""

import math
import re
from collections import Counter

# 字母数字串，保留内部 ./ - ：拆出 "412-8848" "0.3594" "IP54" "600980"
_ALNUM_RE = re.compile(r"[A-Za-z0-9]+(?:[./\-][A-Za-z0-9]+)*")
# 汉字单字（去掉可选的 0x2F80 区，这里用 CJK 统一表意区）
_CJK_RE = re.compile(r"[一-鿿]")


def tokenize(text: str) -> list[str]:
    """把一段文本切成 token 列表：字母数字串（小写化）+ 汉字单字"""
    t = (text or "").lower()
    return _ALNUM_RE.findall(t) + _CJK_RE.findall(t)


class KeywordIndex:
    """BM25 索引：只管词频/文档频率那些统计，打分时现算。

    标准 BM25（k1=1.5, b=0.75）。索引只存 N / avgdl / 每个 token 的 df，
    具体某个 chunk 的 tf 在 score() 里算——因为我们只会对"候选池"里
    几十个 chunk 打分，不值得为它们预建完整倒排。
    """

    _K1 = 1.5
    _B = 0.75

    def __init__(self) -> None:
        self._dirty = True  # 语料变了就要重建
        self._N = 0
        self._avgdl = 0.0
        self._df: dict[str, int] = {}
        self._last_len = 0  # 最近一次构建的语料条数（防重复构建）

    def invalidate(self) -> None:
        """语料有增减（入库/删除）时调用，下次打分前会重建"""
        self._dirty = True

    def build(self, corpus_texts: list[str]) -> None:
        """惰性构建：只有"脏 + 条数变化"才算，否则直接跳过"""
        if not self._dirty and self._last_len == len(corpus_texts):
            return
        valid = [t for t in corpus_texts if t]
        n = len(valid)
        if n == 0:
            self._N, self._avgdl, self._df = 0, 0.0, {}
            self._dirty = False
            self._last_len = n
            return
        df: dict[str, int] = {}
        total = 0
        for text in valid:
            toks = tokenize(text)
            # df 用去重后的集合（BM25 的 df 是"含该词的文档数"）
            for t in set(toks):
                df[t] = df.get(t, 0) + 1
            total += len(toks)
        self._N = n
        self._avgdl = total / n
        self._df = df
        self._dirty = False
        self._last_len = n

    def score(self, query_terms: list[str], doc_text: str) -> float:
        """一个 chunk 相对查询的 BM25 分数。查询词不全在文档里就是 0 附近。

        分数是"量级"而非"名次"——强命中的 chunk 分数会明显高于只蹭到一两个词的。
        这样融合时才能让"精确命中"那类 chunk 真实上浮（纯排名融合做不到）。
        """
        if not self._N or not query_terms or not doc_text:
            return 0.0
        toks = tokenize(doc_text)
        doc_len = len(toks)
        if doc_len == 0:
            return 0.0
        tf = Counter(toks)
        total = 0.0
        for term in query_terms:
            df = self._df.get(term, 0)
            f = tf.get(term, 0)
            if f == 0:
                continue
            idf = math.log((self._N - df + 0.5) / (df + 0.5) + 1)
            denom = f + self._K1 * (1 - self._B + self._B * doc_len / self._avgdl)
            total += idf * (f * (self._K1 + 1)) / denom
        return total


# 模块级单例：整个应用共用一份（跟 retrieval_service / embedding_service 同风格）
keyword_index = KeywordIndex()
