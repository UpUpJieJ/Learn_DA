#!/usr/bin/env python3
"""测试 Agent 升级模块能否正常导入和使用"""

import sys


def test_imports():
    print("测试模块导入...")
    
    try:
        from app.agent.intelligent_routing import (
            IntelligentRouter,
            RoutingStrategy,
            AgentRoute,
        )
        print("✓ intelligent_routing 导入成功")
    except Exception as e:
        print(f"✗ intelligent_routing 导入失败: {e}")
        return False
    
    try:
        from app.agent.streaming import chat_stream, format_sse, StreamEventType
        print("✓ streaming 导入成功")
    except Exception as e:
        print(f"✗ streaming 导入失败: {e}")
        return False
    
    try:
        from app.agent.vector_store import (
            VectorStore,
            InMemoryVectorStore,
            JSONFileVectorStore,
            get_vector_store,
        )
        print("✓ vector_store 导入成功")
    except Exception as e:
        print(f"✗ vector_store 导入失败: {e}")
        return False
    
    try:
        from app.agent.session import (
            ChatSession,
            SessionStore,
            InMemorySessionStore,
            create_session,
            get_session_store,
        )
        print("✓ session 导入成功")
    except Exception as e:
        print(f"✗ session 导入失败: {e}")
        return False
    
    try:
        from app.agent.config import (
            AgentConfig,
            ModelConfig,
            load_agent_config,
            get_model_config,
        )
        print("✓ config 导入成功")
    except Exception as e:
        print(f"✗ config 导入失败: {e}")
        return False
    
    try:
        from app.agent.service import AgentService
        print("✓ service 导入成功")
    except Exception as e:
        print(f"✗ service 导入失败: {e}")
        return False
    
    return True


def test_basic_functionality():
    print("\n测试基本功能...")
    
    try:
        from app.agent.intelligent_routing import IntelligentRouter, RoutingStrategy
        
        router = IntelligentRouter(strategy=RoutingStrategy.KEYWORD)
        print("✓ IntelligentRouter 初始化成功")
    except Exception as e:
        print(f"✗ IntelligentRouter 初始化失败: {e}")
        return False
    
    try:
        from app.agent.session import create_session, InMemorySessionStore
        
        session = create_session()
        print(f"✓ 创建会话成功: {session.id}")
        
        store = InMemorySessionStore()
        import asyncio
        asyncio.run(store.save(session))
        print("✓ 会话保存成功")
    except Exception as e:
        print(f"✗ 会话功能测试失败: {e}")
        return False
    
    try:
        from app.agent.vector_store import InMemoryVectorStore
        from app.agent.knowledge import KnowledgeChunk
        
        store = InMemoryVectorStore()
        chunk = KnowledgeChunk(
            lesson_slug="test",
            lesson_title="测试课程",
            category="test",
            heading="测试小节",
            text="测试内容",
        )
        import asyncio
        asyncio.run(store.add_chunks([chunk]))
        print("✓ 向量存储功能测试成功")
    except Exception as e:
        print(f"✗ 向量存储测试失败: {e}")
        return False
    
    try:
        from app.agent.config import load_agent_config
        
        config = load_agent_config()
        print(f"✓ Agent 配置加载成功: {len(config.models)} 个模型")
    except Exception as e:
        print(f"✗ 配置加载失败: {e}")
        return False
    
    return True


def main():
    print("=" * 60)
    print("Agent 模块升级验证")
    print("=" * 60)
    
    if not test_imports():
        print("\n✗ 导入测试失败")
        sys.exit(1)
    
    if not test_basic_functionality():
        print("\n✗ 功能测试失败")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("✓ 所有验证通过！")
    print("=" * 60)


if __name__ == "__main__":
    main()
