"""Adapter layer for OpenClaw ↔ sidecar integration."""

from .agent_invoke import AgentInvokeAdapter
from .ingress import IngressAdapter
from .openclaw_runtime import HttpOpenClawRuntimeBridge, OpenClawGatewayClient, OpenClawRuntimeBridge
from .result import ResultAdapter

__all__ = [
	"AgentInvokeAdapter",
	"OpenClawGatewayClient",
	"HttpOpenClawRuntimeBridge",
	"IngressAdapter",
	"OpenClawRuntimeBridge",
	"ResultAdapter",
]
