"""稀疏文本页整页兜底测试（Day 26）

背景：图文混排 PDF（快速指南）的规格块，中文标签（充电接口…）进不了 pdfplumber
文本层（0 个 CJK 字符），又不算 page.images → 现有抠图全漏，导致"充电接口"答不出。
兜底：文本异常短的页整页渲染给 VL。

原则：全打桩，不碰真实 PDF / 渲染 / VL。
"""

import io

from app.services import document_service as ds


class _Rendered:
    def save(self, buf, format):
        buf.write(b"PNG-BYTES")


class _FakePage:
    def to_image(self, resolution=150):
        # 返回带 .original 的对象，模仿 pdfplumber page.to_image().original
        return type("_ImgWrapper", (), {"original": _Rendered()})


class _FakePdf:
    def __init__(self, n_pages):
        self.pages = [_FakePage() for _ in range(n_pages)]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_sparse_page_whole_render_only(monkeypatch):
    """只有文本稀疏的页被整页渲染；稠密页不渲染、零开销"""
    texts = ["x" * 500, "几行", "y" * 300]  # 中间页稀疏
    monkeypatch.setattr(ds.pdfplumber, "open", lambda fp: _FakePdf(len(texts)))
    imgs = ds._extract_sparse_page_images("f.pdf", texts)
    assert [i[0] for i in imgs] == [1], "只应整页渲染稀疏的第 2 页"
    assert imgs[0][2] == "image/png"


def test_sparse_page_returns_empty_when_all_dense(monkeypatch):
    """文本都够稠密 → 返回空列表，完全不渲染"""
    texts = ["a" * 500, "b" * 400, "c" * 600]
    monkeypatch.setattr(ds.pdfplumber, "open", lambda fp: _FakePdf(len(texts)))
    assert ds._extract_sparse_page_images("f.pdf", texts) == []


def test_sparse_page_skips_blank(monkeypatch):
    """0 字空白页不整页渲染（防 VL 对空白页幻觉）；只有'有文本但短'的页才兜底"""
    texts = ["", "真实内容", "   "]  # 前后两页空白
    monkeypatch.setattr(ds.pdfplumber, "open", lambda fp: _FakePdf(len(texts)))
    imgs = ds._extract_sparse_page_images("f.pdf", texts)
    assert [i[0] for i in imgs] == [1], "空白页跳过，只渲染中间有文本的稀疏页"


def test_sparse_page_skips_render_failure(monkeypatch):
    """某页渲染失败 → 跳过该页不崩，其余稀疏页照常"""
    class _BadPage:
        def to_image(self, resolution=150):
            raise RuntimeError("render boom")

    class _Pdf:
        def __init__(self):
            self.pages = [_FakePage(), _BadPage()]
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(ds.pdfplumber, "open", lambda fp: _Pdf())
    # 必须 mock 掉 logger，否则 pytest 直接输出 warning 噪音（可跑通，只是刷屏）
    monkeypatch.setattr(ds.logger, "warning", lambda *a, **k: None)
    imgs = ds._extract_sparse_page_images("f.pdf", ["短", "也很短"])
    assert [i[0] for i in imgs] == [0], "第 2 页渲染失败被跳过，第 1 页保留"
