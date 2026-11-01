This project is for exploring the operation of Claude Desktop, a macOS app.

## Claude Desktop

- Findings are documented in `analysis/` (start at `analysis/README.md`)

## Model Context Protocol functionality

Areas of interest are MCP Server integration: Claude Desktop support of MCP and MCP Apps

- MCP Specification is available via the `mcp-specification` tool
- "MCP Apps" is an extension specification to the MCP Specification, it descriptions GUI components inside Claude Desktop
  - ~/src/modelcontextprotocol/ext-apps/main/specification/
  - ~/src/modelcontextprotocol/ext-apps/main/docs/patterns.md

We build MCP servers with FastMCP and Prefab which are MCP frameworks in Python:

- Documentation available for both via tools: `fastmcp_documentation` and `prefab_documentation`
  - ~/src/fastmcp/fastmcp/main
  - ~/src/fastmcp/prefab/main
- Important: prefab bundles the MCP Apps SDK in its renderer
  - ~/src/fastmcp/prefab/main/renderer
