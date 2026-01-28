import os
import sys
import argparse
import logging
from pathlib import Path
from typing import Optional, List
from dotenv import load_dotenv

# 优先加载环境变量，确保 OpenHands SDK 能够识别到 Laminar 配置
load_dotenv()

from pydantic import SecretStr

from openhands.sdk import (
    LLM,
    Agent,
    AgentContext,
    Conversation,
    MessageEvent,
    get_logger,
)
from openhands.sdk.llm import content_to_str
from openhands.sdk.context.skills import Skill, load_skills_from_dir
from openhands.sdk.tool import Tool
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.terminal import TerminalTool
from rich.console import Console
from rich.panel import Panel

# 初始化日志输出路径
project_root = os.getenv("PROJECT_ROOT", "/opt/src/LogixAgent")
log_dir = os.path.join(project_root, "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "agent.log")

# 配置标准日志
logger = get_logger(__name__)
file_handler = logging.FileHandler(log_file, encoding='utf-8')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# 配置 Rich Console
# 为了同时在终端显示并记录到文件，我们创建一个辅助函数
log_file_handle = open(log_file, "a", encoding="utf-8")
console = Console()
file_console = Console(file=log_file_handle, width=120, force_terminal=False)

def log_print(message, style=None, title=None, is_panel=False):
    """同时打印到终端和日志文件"""
    if is_panel:
        panel = Panel(message, border_style=style or "blue", title=title)
        console.print(panel)
        file_console.print(panel)
    else:
        console.print(message, style=style)
        file_console.print(message, style=style)
    # 确保文件写入
    log_file_handle.flush()

# 检查 Laminar 配置状态
if os.getenv("LMNR_PROJECT_API_KEY"):
    logger.info("Laminar Observability 已启用 (LMNR_PROJECT_API_KEY 已设置)")
else:
    logger.warning("Laminar Observability 未启用 (缺少 LMNR_PROJECT_API_KEY)")

def setup_log_storage(base_path: str) -> str:
    """初始化日志存储目录结构"""
    log_types = ["ftrace"]
    storage_info = [f"Default log storage base path: {base_path}"]
    storage_info.append("Structured log directories:")
    
    if not os.path.exists(base_path):
        os.makedirs(base_path, exist_ok=True)
        
    for log_type in log_types:
        type_path = os.path.join(base_path, log_type)
        os.makedirs(type_path, exist_ok=True)
        storage_info.append(f"- {log_type}: {type_path}")
        
    return "\n".join(storage_info)

def create_logix_agent():
    """创建并返回 Logix OpenHands Agent"""
    
    # 获取配置
    project_root = os.getenv("PROJECT_ROOT", "/opt/src/LogixAgent")
    model_name = os.getenv("OPENAI_MODEL_NAME", "deepseek-chat")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com")
    api_key = os.getenv("OPENAI_API_KEY")
    log_storage_path = os.getenv("LOG_STORAGE_PATH", os.path.join(project_root, "logs"))

    # 为 litellm 添加 provider 前缀（如果缺失）
    if "deepseek" in base_url and not ("/" in model_name):
        model_name = f"deepseek/{model_name}"
    elif "openai" in base_url and not ("/" in model_name):
        model_name = f"openai/{model_name}"
    
    # 设置日志存储信息
    log_storage_info = setup_log_storage(log_storage_path)

    # 1. 配置 LLM
    llm = LLM(
        usage_id="logix-agent",
        model=model_name,
        base_url=base_url,
        api_key=SecretStr(api_key) if api_key else None,
    )

    # 2. 加载 Skills (参考官方示例 01_loading_agentskills/main.py)
    # 注意：当前 SDK 返回 (repo_skills, knowledge_skills)，我们合并为 agent_skills 以对齐示例模式
    repo_skills, knowledge_skills = load_skills_from_dir(project_root)
    agent_skills = {**repo_skills, **knowledge_skills}

    log_print("\nLoaded skills from directory:")
    log_print(f"  - Repo skills: {list(repo_skills.keys())}")
    log_print(f"  - Knowledge skills: {list(knowledge_skills.keys())}")
    log_print(f"  - Agent skills (Total): {list(agent_skills.keys())}")
    log_print(f"  - Agent skills (Values): {list(agent_skills.values())}")

    # 显示加载的技能详情 (参考示例，但适配当前 SDK 字段)
    if agent_skills:
        skill_name = "ftrace-analyzer" if "ftrace-analyzer" in agent_skills else next(iter(agent_skills))
        loaded_skill = agent_skills[skill_name]
        log_print(f"\nDetails for '{skill_name}' (AgentSkills fields):")
        log_print(f"  - Name: {loaded_skill.name}")
        log_print(f"  - Trigger: {type(loaded_skill.trigger).__name__ if loaded_skill.trigger else 'None (Always Active)'}")
        log_print(f"  - Source: {loaded_skill.source}")
        # content 可能很大，只显示开头
        content_preview = loaded_skill.content.strip().split('\n')[0][:70]
        log_print(f"  - Content Preview: {content_preview}...")

    # 3. 设置 AgentContext (参考示例)
    agent_context = AgentContext(
        skills=list(agent_skills.values()),
        load_public_skills=False,
        system_message_suffix=f"\n\n## Log Storage Information\n{log_storage_info}"
    )

    # 4. 配置 Tools
    tools = [
        Tool(name=TerminalTool.name),
        Tool(name=FileEditorTool.name),
    ]

    # 5. 初始化 Agent
    agent = Agent(
        llm=llm,
        tools=tools,
        agent_context=agent_context,
    )

    return agent

def main():
    """LogixAgent CLI 入口 (OpenHands 版本)"""
    parser = argparse.ArgumentParser(
        description="LogixAgent: 基于 ftrace-analyzer 的日志分析 Agent (OpenHands 实现)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python openhand_instance.py "请分析一下 /opt/src/LogixAgent/logs/ftrace/trace.log，找出导致 KVM CPU 负载过高的原因。"
        """
    )
    parser.add_argument(
        "question",
        type=str,
        nargs="?",
        default="请分析一下日志文件 /opt/src/LogixAgent/logs/ftrace/trace.log，找出导致 KVM CPU 负载过高的具体原因是什么。",
        help="需要 Agent 分析的问题"
    )

    args = parser.parse_args()

    # 显示问题面板
    log_print(f"[bold cyan]Question (OpenHands):[/bold cyan] {args.question}", style="cyan", title="🚀 LogixAgent", is_panel=True)

    # 创建 Agent
    log_print("[dim]正在初始化 LogixAgent (OpenHands SDK)...[/dim]")
    agent = create_logix_agent()

    # 创建会话
    conversation = Conversation(agent, workspace=project_root)
    
    # 执行查询
    log_print("[dim]正在处理分析请求...[/dim]\n")

    try:
        # 1. 发送消息
        conversation.send_message(args.question)
        
        # 2. 运行 Agent 直到完成
        # 通过在循环中检查事件，我们可以监控技能的触发情况
        logger.info("开始 Agent 执行循环...")
        
        last_event_idx = 0
        while conversation.state.execution_status not in ["finished", "error", "stuck"]:
            conversation.run() # 运行一个或多个步骤
            
            # 检查新产生的事件，寻找技能触发迹象
            current_events = conversation.state.events
            for i in range(last_event_idx, len(current_events)):
                event = current_events[i]
                
                # 监控 MessageEvent 中的技能激活
                if isinstance(event, MessageEvent):
                    if event.activated_skills:
                        log_print(f"[bold green]技能激活:[/bold green] {event.activated_skills}")
                        logger.info(f"检测到技能激活: {event.activated_skills} (来源: {event.source})")
                    if event.extended_content:
                        logger.info(f"检测到 Prompt 扩展 (技能注入内容)，来源: {event.source}")
                
                # 如果是工具调用，也可以记录一下
                elif hasattr(event, "tool_call"):
                    log_print(f"[bold yellow]工具调用:[/bold yellow] {event.tool_call.name}")
                    logger.info(f"Agent 调用了工具: {event.tool_call.name}")
            
            last_event_idx = len(current_events)
            
            # 如果已经完成则跳出
            if conversation.state.execution_status == "finished":
                break

        # 打印消耗统计 (参考示例)
        log_print(f"\nTotal cost: ${agent.llm.metrics.accumulated_cost:.4f}")
        logger.info(f"Agent 执行完毕，总消耗: ${agent.llm.metrics.accumulated_cost:.4f}")
        
        logger.info(f"Agent 执行结束，最终状态: {conversation.state.execution_status}")
        
        # 3. 从事件列表中提取 Agent 的最后一条回复
        answer = "Agent 没有返回任何有效回答。"
        for event in reversed(conversation.state.events):
            if isinstance(event, MessageEvent) and event.source == "agent":
                # 使用 content_to_str 将复杂的消息内容转换为字符串
                answer = "".join(content_to_str(event.llm_message.content))
                break

        log_print(f"[bold green]Analysis Answer:[/bold green]\n\n{answer}", style="green", title="✅ Analysis Complete", is_panel=True)

    except Exception as e:
        log_print(f"[bold red]Error:[/bold red]\n\n{str(e)}", style="red", title="❌ Execution Failed", is_panel=True)
        if "401" in str(e) or "credentials" in str(e).lower():
            log_print("[yellow]提示: 请检查 .env 中的 API Key 或配置。[/yellow]")
        sys.exit(1)

if __name__ == "__main__":
    main()
