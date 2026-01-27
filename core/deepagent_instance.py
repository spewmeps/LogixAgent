import os
import sys
import argparse
import tempfile
from pathlib import Path
from typing import Optional, List
from dotenv import load_dotenv
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend
from deepagents.backends.filesystem import FilesystemBackend
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI
from langfuse.langchain import CallbackHandler
from rich.console import Console
from rich.panel import Panel
from langchain.agents.middleware import (
    ShellToolMiddleware,
    HostExecutionPolicy,
)

# 加载环境变量
load_dotenv()

console = Console()

def load_agents_instructions(project_root: str, log_storage_info: str = "") -> str:
    """从 AGENTS.md 加载 Agent 指令并注入日志路径信息"""
    agents_md_path = os.path.join(project_root, "AGENTS.md")
    content = ""
    if os.path.exists(agents_md_path):
        with open(agents_md_path, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        content = "You are a helpful log analysis agent."
    
    if log_storage_info:
        content += f"\n\n## Log Storage Information\n{log_storage_info}"
    
    return content

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
    """创建并返回 Logix Deep Agent"""
    
    # 获取配置
    project_root = os.getenv("PROJECT_ROOT", "/opt/src/LogixAgent")
    model_name = os.getenv("OPENAI_MODEL_NAME", "deepseek-chat")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com")
    api_key = os.getenv("OPENAI_API_KEY")
    log_storage_path = os.getenv("LOG_STORAGE_PATH", os.path.join(project_root, "logs"))
    skills_paths = [os.path.join(project_root, "skills")]

    # 设置日志存储并加载系统提示词
    log_storage_info = setup_log_storage(log_storage_path)
    system_prompt = load_agents_instructions(project_root, log_storage_info)

    # 配置后端
    base_backend = FilesystemBackend(root_dir=project_root)
    large_results_dir = tempfile.mkdtemp(prefix="logix_large_results_")
    large_results_backend = FilesystemBackend(root_dir=large_results_dir, virtual_mode=True)
    
    composite_backend = CompositeBackend(
        default=base_backend,
        routes={"/large_tool_results/": large_results_backend}
    )

    # 初始化模型
    model = ChatOpenAI(
        model=model_name,
        openai_api_key=api_key,
        openai_api_base=base_url,
        streaming=True
    )

    # 创建 Deep Agent
    checkpointer = MemorySaver()
    agent = create_deep_agent(
        model=model,
        memory=[os.path.join(project_root, "AGENTS.md")], # Agent identity and general instructions
        skills=[os.path.join(project_root, "skills")],    # Specialized workflows
        backend=FilesystemBackend(root_dir=project_root), # Persistent file storage
         middleware=[
        ShellToolMiddleware(
            workspace_root="/",
            execution_policy=HostExecutionPolicy(),
        ),
    ],
        checkpointer=checkpointer,
    )
   
    # 初始化 Langfuse 回调
    handler = CallbackHandler()

    return agent, handler

def main():
    """LogixAgent CLI 入口"""
    parser = argparse.ArgumentParser(
        description="LogixAgent: 基于 ftrace-analyzer 的日志分析 Deep Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python agent.py "请分析一下 /opt/src/LogixAgent/logs/ftrace/trace.log，找出导致 KVM CPU 负载过高的原因,使用ftrace-analyzer skill。"
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
    console.print(Panel(
        f"[bold cyan]Question:[/bold cyan] {args.question}",
        border_style="cyan",
        title="🚀 LogixAgent"
    ))

    # 创建 Agent
    console.print("[dim]正在初始化 LogixAgent (模型: DeepSeek)...[/dim]")
    agent, handler = create_logix_agent()

    # 执行查询
    console.print("[dim]正在处理分析请求...[/dim]\n")

    config = {
        "configurable": {"thread_id": "logix-cli-session"},
        "callbacks": [handler]
    }

    try:
        # 使用 invoke 获取最终结果（匹配示例风格）
        result = agent.invoke({
            "messages": [{"role": "user", "content": args.question}]
        }, config=config)

        # 提取并显示答案
        final_message = result["messages"][-1]
        answer = final_message.content if hasattr(final_message, 'content') else str(final_message)

        console.print(Panel(
            f"[bold green]Analysis Answer:[/bold green]\n\n{answer}",
            border_style="green",
            title="✅ Analysis Complete"
        ))

    except Exception as e:
        console.print(Panel(
            f"[bold red]Error:[/bold red]\n\n{str(e)}",
            border_style="red",
            title="❌ Execution Failed"
        ))
        if "401" in str(e) or "credentials" in str(e).lower():
            console.print("[yellow]提示: 请检查 .env 中的 API Key 或 Langfuse 凭据。[/yellow]")
        sys.exit(1)

if __name__ == "__main__":
    main()
