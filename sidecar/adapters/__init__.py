"""Adapter layer for OpenClaw ↔ sidecar integration."""

from .agent_invoke import AgentInvokeAdapter
from .ingress import IngressAdapter
from .result import ResultAdapter

__all__ = [
	"AgentInvokeAdapter",
	"IngressAdapter",
	"ResultAdapter",
]
