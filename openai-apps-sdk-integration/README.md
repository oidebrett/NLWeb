# NLWeb Apps SDK Integration

[![MIT License](https://img.shields.io/ba```bash
cd nlweb_server_node

# Start MCP Server
npm start

# Run test suite
npm run test
```

**Documentation:**
- [nlweb_server_node/README.md](nlweb_server_node/README.md) - Detailed usage instructions
- [nlweb_server_node/DEPLOYMENT.md](nlweb_server_node/DEPLOYMENT.md) - Production deployment guidegreen.svg)](LICENSE)

This repository contains the NLWeb MCP (Model Context Protocol) server with rich UI widgets for ChatGPT integration.

## MCP + Apps SDK overview

The Model Context Protocol (MCP) is an open specification for connecting large language model clients to external tools, data, and user interfaces. An MCP server exposes tools that a model can call during a conversation and returns results according to the tool contracts. Those results can include extra metadata—such as inline HTML—that the Apps SDK uses to render rich UI components (widgets) alongside assistant messages.

Within the Apps SDK, MCP keeps the server, model, and UI in sync. By standardizing the wire format, authentication, and metadata, it lets ChatGPT reason about your connector the same way it reasons about built-in tools. A minimal MCP integration for Apps SDK implements three capabilities:

1. **List tools** – Your server advertises the tools it supports, including their JSON Schema input/output contracts and optional annotations (for example, `readOnlyHint`).
2. **Call tools** – When a model selects a tool, it issues a `call_tool` request with arguments that match the user intent. Your server executes the action and returns structured content the model can parse.
3. **Return widgets** – Alongside structured content, return embedded resources in the response metadata so the Apps SDK can render the interface inline in the Apps SDK client (ChatGPT).

Because the protocol is transport agnostic, you can host the server over Server-Sent Events or streaming HTTP—Apps SDK supports both.

The MCP servers in this demo highlight how each tool can light up widgets by combining structured payloads with `_meta.openai/outputTemplate` metadata returned from the MCP servers.

## Repository structure

- `src/nlweb-list/` – Hybrid NLWeb widget (handles both Schema.org results and visualizations)
- `src/nlweb-datacommons/` – Visualization widget components (charts, maps, rankings)
- `src/shared/` – Shared UI components used by both widgets
- `assets/` – Generated HTML, JS, and CSS bundles after running the build step
- `nlweb_server_node/` – MCP server implemented with the official TypeScript SDK
- `build-all.mts` – Vite build orchestrator that produces hashed bundles for widgets

## Prerequisites

- Node.js 18+
- npm or pnpm
- Running NLWeb backend (default: localhost:8100)

## Install dependencies

Install the workspace dependencies:

```bash
npm install
# or
pnpm install
```

## Build the widget

The NLWeb list widget is bundled into standalone assets that the MCP server references.

```bash
npm run build
```

This produces versioned `.html`, `.js`, and `.css` files inside `assets/` (e.g., `nlweb-list-2d2b.js`).

To iterate locally, launch the Vite dev server:

```bash
npm run dev
```

## Serve the widget assets

After building, serve the static assets for local development:

```bash
npm run serve
```

The assets are exposed at [`http://localhost:4444`](http://localhost:4444) with CORS enabled.

## Run the NLWeb MCP Server

### NLWeb Node server

```bash
cd nlweb_server_node

# For MCP Server
npm start

# Run test suite
npm run test
```

See [nlweb_server_node/README.md](nlweb_server_node/README.md) for detailed usage instructions and [nlweb_server_node/DEPLOYMENT.md](nlweb_server_node/DEPLOYMENT.md) for production deployment guide.

## Testing in ChatGPT

To add these apps to ChatGPT, enable [developer mode](https://platform.openai.com/docs/guides/developer-mode), and add your apps in Settings > Connectors.

To add your local server without deploying it, you can use a tool like [ngrok](https://ngrok.com/) to expose your local server to the internet.

### Quick Start with Local Server

**Terminal 1 - Serve widget assets:**
```bash
npm run serve  # Serves at http://localhost:4444
```

**Terminal 2 - Start MCP server:**
```bash
cd nlweb_server_node
npm start  # Runs on port 8000
```

**Terminal 3 - Expose with ngrok:**
```bash
ngrok http 8000
```

You will get a public URL that you can use to add your local server to ChatGPT in Settings > Connectors.

For example: `https://<custom_endpoint>.ngrok-free.app/mcp`

For production deployment, see [nlweb_server_node/DEPLOYMENT.md](nlweb_server_node/DEPLOYMENT.md).

## Widget Architecture

### Hybrid Widget Design

The NLWeb integration uses a **hybrid widget architecture** where the `nlweb-list` widget automatically detects and renders both:

1. **Schema.org Structured Data** - Traditional search results (restaurants, articles, places)
2. **Interactive Visualizations** - Data Commons charts, maps, rankings, and embedded components

This design solves ChatGPT's widget caching behavior, where the client caches which widget to load based on the tool definition. Instead of trying to dynamically switch widgets (which ChatGPT may ignore), we use a single smart widget that adapts to the data it receives.

### How It Works

```
┌──────────────────────────────────────────────────┐
│  ChatGPT loads nlweb-list widget                 │
└──────────────────────────────────────────────────┘
                     ↓
┌──────────────────────────────────────────────────┐
│  MCP Server returns structuredContent.results    │
│  Each result has: @type, name, url, etc.         │
│  OR: visualizationType, html, script, etc.       │
└──────────────────────────────────────────────────┘
                     ↓
┌──────────────────────────────────────────────────┐
│  Widget detects result type:                     │
│  - Has html/script/visualizationType?            │
│    → Use VisualizationBlock component            │
│  - Regular Schema.org data?                      │
│    → Use ResultItem component                    │
└──────────────────────────────────────────────────┘
                     ↓
┌──────────────────────────────────────────────────┐
│  VisualizationBlock:                             │
│  1. Loads Data Commons script if needed          │
│  2. Injects result.html into DOM                 │
│  3. Web components self-initialize               │
│  4. Renders interactive charts/maps              │
└──────────────────────────────────────────────────┘
```

### Key Benefits

- **No caching issues** - Single widget handles both data types
- **Backward compatible** - Existing Schema.org results still work
- **Future-proof** - Can mix visualizations and regular results in same response
- **Simpler architecture** - No complex dynamic widget selection needed

### Component Structure

```
src/
├── nlweb-list/           # Main hybrid widget
│   ├── index.jsx         # Detects and routes to correct renderer
│   └── nlweb-list.css    # Styles for Schema.org results
├── nlweb-datacommons/    # Visualization components
│   ├── index.jsx         # Standalone visualization widget (backup)
│   ├── VisualizationBlock.jsx  # Individual viz renderer
│   └── nlweb-datacommons.css   # Visualization styles
└── shared/               # Shared components
    └── NLWebComponents.jsx  # Header, Container, EmptyState
```

### Data Format Examples

**Schema.org Result:**
```json
{
  "@type": "Restaurant",
  "name": "Joe's Pizza",
  "description": "Best pizza in town",
  "image": "https://...",
  "rating": 4.5,
  "url": "https://..."
}
```

**Visualization Result:**
```json
{
  "@type": "StatisticalResult",
  "visualizationType": "map",
  "html": "<datacommons-map header='...' ...></datacommons-map>",
  "script": "<script src='https://datacommons.org/datacommons.js'></script>",
  "places": ["geoId/06"],
  "variables": ["Percent_Person_WithDiabetes"]
}
```

## Development

### Customize the Widget

Edit `src/nlweb-list/index.jsx` to modify how results are displayed. After changes:

1. Rebuild: `npm run build`
2. Note the new hash in the filename (e.g., `nlweb-list-xxxx.js`)
3. Update the hash in `nlweb_server_node/src/server.ts`
4. Restart the server

### Modify the Server

Edit `nlweb_server_node/src/server.ts` to:
- Change the NLWeb AppSDK backend URL (`NLWEB_APPSDK_BASE_URL`)
- Customize tool parameters
- Add additional tools or widgets

### Debug Logging

The integration includes comprehensive debug logging:

**Server-side (MCP):**
- Response structure from NLWeb adapter
- Result counts and types
- Widget selection logic
- Field presence checks (html, script, visualizationType)

**Client-side (Widget):**
- Widget initialization
- Data reception
- Visualization detection
- HTML injection process

Check browser console and server logs when troubleshooting.

## Environment Variables

- `NLWEB_APPSDK_BASE_URL` - NLWeb AppSDK backend API URL (default: `http://localhost:8100`)
- `REQUEST_TIMEOUT` - Timeout for NLWeb requests in ms (default: `30000`)
- `PORT` - Server port for HTTP mode (default: `8000`)

## Troubleshooting

### Visualizations Not Rendering

If Data Commons visualizations show as HTML code instead of interactive components:

1. **Check all services are running:**
   ```bash
   # NLWeb Core (port 8000)
   curl http://localhost:8000/ask?query=test
   
   # AppSDK Adapter (port 8100)
   curl http://localhost:8100/ask?query=test
   
   # Widget Server (port 4444)
   curl http://localhost:4444/nlweb-list-2d2b.js
   ```

2. **Check browser console for errors:**
   - Look for "🎨 NLWeb List Widget" log showing `hasVisualizations: true`
   - Look for "✅ Injecting HTML for visualization" messages
   - Check for script loading errors

3. **Check MCP server logs:**
   - Should show "Widget Selection Debug" with `hasVisualization: true`
   - Should show result structure with `html`, `script`, `visualizationType` fields

4. **Verify Data Commons script is loading:**
   - Open browser DevTools → Network tab
   - Look for `datacommons.js` being loaded from `datacommons.org`

5. **Common issues:**
   - **Wrong protocol:** URL should be `http://localhost:8100` not `https://`
   - **AppSDK adapter not running:** Start with `python -m webserver.appsdk_adapter_server`
   - **Results not in structuredContent.results:** Check adapter transformation
   - **Widget cache:** Hard refresh ChatGPT (Cmd+Shift+R / Ctrl+Shift+R)

### Testing the Full Stack

Run the test script to verify the adapter is working:

```bash
cd openai-apps-sdk-integration
./test_adapter_response.sh
```

This will test:
- Connectivity to port 8100
- Response structure validation
- Presence of visualization fields
- First result inspection

### Service Startup Order

For best results, start services in this order:

1. **NLWeb Core** (port 8000 or hosted)
2. **AppSDK Adapter** (port 8100 or hosted) - transforms NLWeb responses
3. **Widget Server** (port 4444) - serves static assets
4. **MCP Server** (port 8000) - connects to AppSDK adapter
