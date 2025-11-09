# NLWeb MCP Server (Node)

This directory contains a Model Context Protocol (MCP) server that exposes the NLWeb ask tool with rich UI widgets. The server queries NLWeb's backend API and returns structured results displayed in a custom list widget.

## Prerequisites

- Node.js 18+
- npm, pnpm, or yarn for dependency management
- Running NLWeb backend (default: localhost)

## Install dependencies

```bash
npm install
```

If you prefer pnpm or yarn, adjust the command accordingly.

## Run the server

```bash
npm start
```

This runs the server on **HTTP port 8000** (configurable via `PORT` env variable).

**Endpoints:**
- SSE stream: `GET http://localhost:8000/mcp`
- Message post: `POST http://localhost:8000/mcp/messages?sessionId=...`

## Testing

### Test the SSE server with the test script

```bash
# Terminal 1: Start the server
npm start

# Terminal 2: Run the automated test suite
npm run test
```

The test script will automatically:
1. ✅ Connect to the SSE stream
2. ✅ List available tools
3. ✅ List available resources
4. ✅ Read the widget resource
5. ✅ Call the nlweb-results tool with a test query
6. 📊 Display a test summary

**Test with ngrok:**
```bash
ngrok http 8000
```

Then add to ChatGPT: `https://your-ngrok-url.ngrok-free.app/mcp`

## Configuration

Set environment variables to customize behavior:

```bash
# NLWeb AppSDK backend URL
export NLWEB_APPSDK_BASE_URL="http://localhost:8100"

# Request timeout in milliseconds
export REQUEST_TIMEOUT="60000"

# HTTP server port (HTTP mode only)
export PORT="8000"
```

## Tool specification

The server exposes one tool:

**`nlweb-results`** - Query NLWeb to search and analyze information

Parameters:
- `query` (required): The search query or question
- `site` (optional): Specific site to search (e.g., "datacommons.org")
- `mode` (optional): Response mode - "list", "summarize", or "generate"
- `prev` (optional): Previous conversation context

Each tool response includes:

- `content`: Text summary of results
- `structuredContent`: Full NLWeb response with results array, messages, metadata
- `_meta.openai/outputTemplate`: Widget metadata for rendering the nlweb-list UI

## Widget

The server returns the **nlweb-list** widget that displays search results with:
- Product images (from schema_object.image)
- Titles and descriptions
- Scores/ratings
- Schema.org type annotations
