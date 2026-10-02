"""JD 解析的结构化输出模型。

这个模型有三个用途：
1. 直接作为 LLM 的工具 schema（通过 ``ToolRegistry.submit``）
2. 校验模型输出——校验失败会以 ``is_error`` 回给模型自行修正
3. 作为面试规划的输入

设计上的两个刻意选择：

- ``extra="forbid"``：模型多编一个字段就报错，而不是被静默吞掉
- ``seniority_reason`` 必填：逼模型给出判断职级的依据，解析结果可解释
- 所有字段都允许为空：JD 里没写就填 null，**不允许模型编造**
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Seniority = Literal["实习", "校招", "初级", "中级", "高级", "资深", "专家", "未知"]


class JDAnalysis(BaseModel):
    """从 JD 原文抽取的结构化信息。"""

    model_config = ConfigDict(extra="forbid")

    company: str | None = Field(
        default=None, description="公司名称。JD 未提及则为 null"
    )
    role_title: str | None = Field(
        default=None, description="岗位名称。JD 未提及则为 null"
    )
    seniority: Seniority = Field(
        default="未知", description="职级，结合年限、深度要求、职责范围综合判断"
    )
    seniority_reason: str = Field(
        description="判断职级的依据，必须引用 JD 原文措辞，例如'要求 3 年以上经验'"
    )
    business_domain: str | None = Field(
        default=None, description="业务方向，例如'企业服务 SaaS'、'金融科技'"
    )
    skills_required: list[str] = Field(
        default_factory=list, description="硬性技能要求，JD 明确要求或必须会的"
    )
    skills_nice_to_have: list[str] = Field(
        default_factory=list, description="加分项，JD 中以'优先''加分'等措辞出现"
    )
    responsibilities: list[str] = Field(
        default_factory=list, description="主要职责，每条一句话"
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="用于后续简历匹配和面试出题的技术关键词，3-8 个",
    )
