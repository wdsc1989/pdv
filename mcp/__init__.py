"""
MCP (Model Context Protocol) para o PDV.
Serviços in-process: detect, extract, validate, list, format.
"""
from mcp.detector import MCPDetector
from mcp.extractor import MCPExtractor
from mcp.validator import MCPValidator
from mcp.lister import MCPLister
from mcp.formatter import MCPFormatter

__all__ = [
    "MCPDetector",
    "MCPExtractor",
    "MCPValidator",
    "MCPLister",
    "MCPFormatter",
]
