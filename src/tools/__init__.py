"""Tool registries for the App Store Connect MCP server."""

from tools.analysis import ANALYSIS_TOOLS
from tools.cpp import CPP_TOOLS
from tools.generic import GENERIC_TOOLS
from tools.read import READ_TOOLS
from tools.subscriber import SUBSCRIBER_TOOLS
from tools.versioning import VERSIONING_TOOLS
from tools.write import WRITE_TOOLS


ALL_TOOLS = [
    *READ_TOOLS,
    *WRITE_TOOLS,
    *VERSIONING_TOOLS,
    *CPP_TOOLS,
    *ANALYSIS_TOOLS,
    *GENERIC_TOOLS,
    *SUBSCRIBER_TOOLS,
]
