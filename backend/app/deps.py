"""FastAPI 依赖注入。

路由层不自己从 ``app.state`` 里掏东西，统一走这里声明。好处：

- 路由签名就能看出它依赖了什么，不用读函数体
- 测试时用 ``app.dependency_overrides[...]`` 就能替换掉真实实现
- 依赖关系集中在一处，不用到处找 ``request.app.state``
"""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings, get_settings
from app.llm.base import LLMClient


def get_llm(request: Request) -> LLMClient:
    """模型客户端。在 lifespan 里构造一次，整个进程共用。"""
    return request.app.state.llm


def get_settings_dep() -> Settings:
    return get_settings()


def get_session_factory(
    request: Request,
) -> async_sessionmaker[AsyncSession]:
    return request.app.state.session_factory


LLMDep = Annotated[LLMClient, Depends(get_llm)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
SessionFactoryDep = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]
