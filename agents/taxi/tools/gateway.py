"""SigV4-authenticated MCP client for Taxi Gateway tools."""

import os

from mcp_proxy_for_aws.client import aws_iam_streamablehttp_client
from strands.tools.mcp import MCPClient


def build_gateway_client() -> MCPClient | None:
    endpoint = os.getenv("TAXI_GATEWAY_URL")
    if not endpoint:
        return None
    region = os.getenv("AWS_REGION", "us-west-2")
    return MCPClient(
        lambda: aws_iam_streamablehttp_client(
            endpoint=endpoint,
            aws_region=region,
            aws_service="bedrock-agentcore",
        )
    )
