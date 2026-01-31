import os 
from pathlib import Path

# Load .env manually if it exists
env_path = Path("/opt/src/LogixAgent/.env")
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                key, value = line.strip().split("=", 1)
                os.environ[key] = value

from pydantic import SecretStr 
  
from openhands.sdk import ( 
    LLM, 
    Agent, 
    AgentContext, 
    Conversation, 
    Event, 
    LLMConvertibleEvent, 
    get_logger, 
) 
from openhands.sdk.context import ( 
    KeywordTrigger, 
    Skill, 
) 
from openhands.sdk.tool import Tool 
from openhands.tools.file_editor import FileEditorTool 
from openhands.tools.terminal import TerminalTool 
  
  
logger = get_logger(__name__) 
  
# Configure LLM 
api_key = os.getenv("OPENAI_API_KEY") 
assert api_key is not None, "OPENAI_API_KEY environment variable is not set." 
model = os.getenv("OPENAI_MODEL_NAME", "deepseek-chat") 
base_url = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com") 

# 为 litellm 添加 provider 前缀（如果缺失）
if "deepseek" in base_url and not ("/" in model):
    model = f"deepseek/{model}"

llm = LLM( 
    usage_id="agent", 
    model=model, 
    base_url=base_url, 
    api_key=SecretStr(api_key), 
) 
  
# Tools 
cwd = os.getcwd() 
tools = [ 
    Tool( 
        name=TerminalTool.name, 
    ), 
    Tool(name=FileEditorTool.name), 
] 
  
# AgentContext provides flexible ways to customize prompts: 
agent_context = AgentContext( 
    skills=[ 
        Skill( 
            name="repo.md", 
            content="When you see this message, you should reply like " 
            "you are a grumpy cat forced to use the internet.", 
            source=None, 
            trigger=None, 
        ), 
        Skill( 
            name="flarglebargle", 
            content=( 
                'IMPORTANT! The user has said the magic word "flarglebargle". ' 
                "You must only respond with a message telling them how smart they are" 
            ), 
            source=None, 
            trigger=KeywordTrigger(keywords=["flarglebargle"]), 
        ), 
    ], 
    system_message_suffix="Always finish your response with the word 'yay!'", 
    user_message_suffix="The first character of your response should be 'I'", 
    load_public_skills=True, 
) 
  
# Agent 
agent = Agent(llm=llm, tools=tools, agent_context=agent_context) 
  
llm_messages = []  # collect raw LLM messages 
  
  
def conversation_callback(event: Event): 
    if isinstance(event, LLMConvertibleEvent): 
        llm_messages.append(event.to_llm_message()) 
  
  
conversation = Conversation( 
    agent=agent, callbacks=[conversation_callback], workspace=cwd 
) 
  
print("=" * 100) 
print("Checking if the repo skill is activated.") 
conversation.send_message("Hey are you a grumpy cat?") 
conversation.run() 
  
print("=" * 100) 
print("Now sending flarglebargle to trigger the knowledge skill!") 
conversation.send_message("flarglebargle!") 
conversation.run() 
  
print("=" * 100) 
print("Now triggering public skill 'github'") 
conversation.send_message( 
    "About GitHub - tell me what additional info I've just provided?" 
) 
conversation.run() 
  
print("=" * 100) 
print("Conversation finished. Got the following LLM messages:") 
for i, message in enumerate(llm_messages): 
    print(f"Message {i}: {str(message)[:200]}") 
  
# Report cost 
cost = llm.metrics.accumulated_cost 
print(f"EXAMPLE_COST: {cost}")
