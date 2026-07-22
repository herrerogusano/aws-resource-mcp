"""Uniform AWS service-adapter package."""

from aws_resource_mcp.aws.adapters.registry import ADAPTERS, get_adapters

__all__ = ["ADAPTERS", "get_adapters"]
