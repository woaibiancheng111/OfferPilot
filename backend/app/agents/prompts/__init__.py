"""Prompt 模板与版本号。

版本号从内容算出来，不要手写。手写的版本号迟早会和 prompt 内容对不上，
到时候"优化前后的对比"就悄悄失效了，而且查不出来。
"""

import hashlib

__all__ = ["version_of"]


def version_of(prompt: str) -> str:
    """prompt 内容的短指纹。同内容必定同版本，改一个字版本就变。"""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:8]
