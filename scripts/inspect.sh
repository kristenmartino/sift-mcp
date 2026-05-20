#!/usr/bin/env bash
# Launch MCP Inspector against this server with timeouts sized for the
# compare_outlets tool (live LangGraph + Claude web_search, ~15–60s).
#
# Inspector's default request timeout is 10s, which only suits the four
# Postgres-backed tools. compare_outlets needs ~2 min of headroom.

set -euo pipefail

cd "$(dirname "$0")/.."

export MCP_SERVER_REQUEST_TIMEOUT="${MCP_SERVER_REQUEST_TIMEOUT:-120000}"
export MCP_REQUEST_MAX_TOTAL_TIMEOUT="${MCP_REQUEST_MAX_TOTAL_TIMEOUT:-180000}"
export MCP_REQUEST_TIMEOUT_RESET_ON_PROGRESS="${MCP_REQUEST_TIMEOUT_RESET_ON_PROGRESS:-true}"

exec uv run mcp dev src/sift_mcp/server.py
