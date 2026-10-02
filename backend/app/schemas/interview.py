"""面试流程的结构化模型。

两个模型对应两个需要落库和对比的对象：
- ``InterviewPlan``：规划 Agent 产出，是整场面试的骨架
- ``TurnEvaluation``：评估 Agent 每轮产出，**这是评测闭环的信号源**，
  字段设计要能直接变成 rubric 和评测集里的一条 case

``TurnEvaluation`` 的多维打分刻意和人类标注的维度对齐，
这样第 5 周算 kappa 时不用再做一次字段映射。
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Difficulty = Literal["基础", "进阶", "深入"]


class PlanTopic(BaseModel):
    """一个考察点。"""

    model_config = ConfigDict(extra="forbid")

    topic: str = Field(description="考察的知识点，如「Redis 持久化」")
    difficulty: Difficulty = Field(default="进阶", description="难度")
    source: Literal["jd", "resume", "both"] = Field(
        default="jd", description="这个考察点来自 JD、简历还是两者都提到"
    )
    why: str = Field(description="为什么问这个，结合 JD 要求或简历内容说一句话")


class InterviewPlan(BaseModel):
    """面试大纲。"""

    model_config = ConfigDict(extra="forbid")

    topics: list[PlanTopic] = Field(
        min_length=3, max_length=10, description="考察点，3-10 个，按面试顺序排列"
    )
    focus_points: list[str] = Field(
        default_factory=list, description="本场最想验证的 1-3 个能力，面试官会重点围绕它们追问"
    )
    opening: str = Field(description="开场白，直接对候选人说的一段话，2-3 句")


class TurnEvaluation(BaseModel):
    """一轮问答的评估。

    维度选择的原则：和「人工标注时你会打哪几个分」对齐。
    权重都在 1-5 的整数区间，人类也好对齐。
    """

    model_config = ConfigDict(extra="forbid")

    technical_depth: int = Field(ge=1, le=5, description="技术深度：是否触及原理而非背诵")
    clarity: int = Field(ge=1, le=5, description="表达清晰度：结构是否清楚")
    evidence: int = Field(ge=1, le=5, description="有据可依：是否给出具体细节、数字或权衡")
    relevance: int = Field(ge=1, le=5, description="切题程度：有没有跑题")

    summary: str = Field(description="一句话总结这轮表现")
    next_action: Literal["follow_up", "switch_topic", "increase_difficulty"] = Field(
        description="给面试官的下一步建议：追问 / 换题 / 加难度"
    )
    follow_up_reason: str = Field(
        description="为什么这么建议，必须结合上面的打分和候选人的实际回答，"
        "不能写「建议深入」这种空话"
    )
