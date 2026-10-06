"""Which tools each agent gets. GL and AP tools are added in later bundles."""
from .framework import Registry
from .shared import SHARED_TOOLS

GL_TOOLS = []
AP_TOOLS = []


def build_registry(agent):
    if agent == "gl_sentinel":
        return Registry(SHARED_TOOLS + GL_TOOLS)
    if agent == "ap_guardian":
        return Registry(SHARED_TOOLS + AP_TOOLS)
    raise ValueError(f"Unknown agent {agent!r}")
