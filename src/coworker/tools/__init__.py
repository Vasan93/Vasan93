"""Agent tools — registered as OpenAI function-call schemas."""
from .data_quality      import DATA_QUALITY_TOOLS,      run_data_quality_tool
from .knowledge_base    import KNOWLEDGE_BASE_TOOLS,     run_knowledge_base_tool
from .code_navigator    import CODE_NAVIGATOR_TOOLS,     run_code_navigator_tool
from .onboarding        import ONBOARDING_TOOLS,         run_onboarding_tool
from .pipeline_monitor  import PIPELINE_MONITOR_TOOLS,   run_pipeline_monitor_tool

ALL_TOOLS: list[dict] = (
    DATA_QUALITY_TOOLS
    + KNOWLEDGE_BASE_TOOLS
    + CODE_NAVIGATOR_TOOLS
    + ONBOARDING_TOOLS
    + PIPELINE_MONITOR_TOOLS
)


def dispatch_tool(name: str, arguments: str | dict) -> str:
    """Route a tool_call by name to the correct handler."""
    import json
    args = json.loads(arguments) if isinstance(arguments, str) else arguments

    routers = {
        **{t["function"]["name"]: run_data_quality_tool      for t in DATA_QUALITY_TOOLS},
        **{t["function"]["name"]: run_knowledge_base_tool     for t in KNOWLEDGE_BASE_TOOLS},
        **{t["function"]["name"]: run_code_navigator_tool     for t in CODE_NAVIGATOR_TOOLS},
        **{t["function"]["name"]: run_onboarding_tool         for t in ONBOARDING_TOOLS},
        **{t["function"]["name"]: run_pipeline_monitor_tool   for t in PIPELINE_MONITOR_TOOLS},
    }

    handler = routers.get(name)
    if handler is None:
        return f"Error: unknown tool '{name}'"
    return handler(name, args)
