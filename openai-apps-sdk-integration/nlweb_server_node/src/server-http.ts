// server.ts
import {
  createServer,
  type IncomingMessage,
  type ServerResponse,
} from "node:http";
import { URL } from "node:url";
import { z } from "zod";
import fetch from "node-fetch";

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import {
  CallToolRequestSchema,
  ListResourcesRequestSchema,
  ListToolsRequestSchema,
  ReadResourceRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

// Configuration (preserve your environment-driven config)
const NLWEB_APPSDK_BASE_URL =
  process.env.NLWEB_APPSDK_BASE_URL || "http://localhost:8100";
const REQUEST_TIMEOUT = parseInt(process.env.REQUEST_TIMEOUT || "30000", 10);

// ------------------------ Widget configuration ------------------------
type NLWebWidget = {
  id: string;
  title: string;
  templateUri: string;
  invoking: string;
  invoked: string;
  html: string;
};

function widgetMeta(widget: NLWebWidget) {
  return {
    "openai/outputTemplate": widget.templateUri,
    "openai/toolInvocation/invoking": widget.invoking,
    "openai/toolInvocation/invoked": widget.invoked,
    "openai/widgetAccessible": true,
    "openai/resultCanProduceWidget": true,
  } as const;
}

const nlwebListWidget: NLWebWidget = {
  id: "nlweb-list",
  title: "NLWeb Results",
  templateUri: "ui://widget/nlweb-list.html",
  invoking: "Searching NLWeb",
  invoked: "Found results",
  html: `
<div id="nlweb-list-root"></div>
<link rel="stylesheet" href="http://localhost:4444/nlweb-list-2d2b.css">
<script type="module" src="http://localhost:4444/nlweb-list-2d2b.js"></script>
  `.trim(),
};

const nlwebVisualizationWidget: NLWebWidget = {
  id: "nlweb-visualization",
  title: "NLWeb Visualizations",
  templateUri: "ui://widget/nlweb-visualization.html",
  invoking: "Creating visualization",
  invoked: "Visualized data",
  html: `
<div id="nlweb-datacommons-root"></div>
<link rel="stylesheet" href="http://localhost:4444/nlweb-datacommons-2d2b.css">
<script type="module" src="http://localhost:4444/nlweb-datacommons-2d2b.js"></script>
  `.trim(),
};

// Decide which widget to use based on structuredContent
function selectWidget(response: NLWebResponse): NLWebWidget {
  const results = response.structuredContent?.results || [];

  const hasVisualization = results.some(
    (result) =>
      Boolean(result.visualizationType) ||
      Boolean(result.html) ||
      Boolean(result.script)
  );

  // Debug log similar to your original
  console.log("Widget Selection Debug:", {
    resultCount: results.length,
    hasVisualization,
    firstResult: results[0]
      ? {
          hasVisualizationType: !!results[0].visualizationType,
          hasHtml: !!results[0].html,
          hasScript: !!results[0].script,
          type: results[0]["@type"],
        }
      : null,
    selectedWidget: hasVisualization ? "visualization" : "list",
  });

  return hasVisualization ? nlwebVisualizationWidget : nlwebListWidget;
}

// ------------------------ NLWeb API shapes & call ------------------------
const NLWebAskInputSchema = z.object({
  query: z.string().describe("The question or search query"),
  site: z.string().optional().describe("Optional site to search"),
  mode: z.enum(["list", "summarize", "generate"]).optional().describe("The type of response to generate"),
  prev: z.array(z.string()).optional().describe("Previous conversation context"),
});
type NLWebAskInput = z.infer<typeof NLWebAskInputSchema>;

interface NLWebBlock {
  "@type"?: string;
  visualizationType?: string;
  html?: string;
  script?: string;
  places?: string[];
  variables?: string[];
  embed_instructions?: string;
  [key: string]: any;
}

interface NLWebResponse {
  structuredContent: {
    query?: string;
    results: NLWebBlock[];
    messages?: any[];
    metadata?: any;
    conversationId?: string;
    generatedAnswers?: any[];
    legacyResponse?: any;
  };
  content: Array<{ type: string; text: string }>;
}

async function callNLWebAsk(params: NLWebAskInput): Promise<NLWebResponse> {
  const queryParams = new URLSearchParams({
    query: params.query,
    streaming: "false",
  });

  if (params.site) queryParams.set("site", params.site);
  if (params.mode) queryParams.set("mode", params.mode);

  const url = `${NLWEB_APPSDK_BASE_URL}/ask?${queryParams.toString()}`;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT);

  try {
    const response = await fetch(url, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(
        `NLWeb API error: ${response.status} - ${errorText.substring(0, 200)}`
      );
    }

    const data = (await response.json()) as NLWebResponse;

    // Helpful debug logs (keeps parity with original)
    console.log("=== NLWeb API Response ===");
    console.log("structuredContent keys:", Object.keys(data.structuredContent || {}));
    console.log("results count:", data.structuredContent?.results?.length || 0);
    console.log("content count:", data.content?.length || 0);
    if (data.structuredContent?.results?.length > 0) {
      console.log("First result keys:", Object.keys(data.structuredContent.results[0]));
      console.log("First result @type:", data.structuredContent.results[0]["@type"]);
      console.log("First result has html:", !!data.structuredContent.results[0].html);
      console.log("First result has script:", !!data.structuredContent.results[0].script);
      console.log("First result has visualizationType:", !!data.structuredContent.results[0].visualizationType);
      console.log("First result (full):", JSON.stringify(data.structuredContent.results[0], null, 2));
    }
    console.log("========================");

    if (!data.structuredContent || !data.content) {
      throw new Error("Invalid response format from NLWeb adapter");
    }

    return data;
  } catch (err) {
    clearTimeout(timeoutId);

    if (err instanceof Error) {
      if (err.name === "AbortError") {
        throw new Error(`Request timeout after ${REQUEST_TIMEOUT}ms`);
      }
      throw err;
    }
    throw new Error("Unknown error occurred while calling NLWeb");
  }
}

// ------------------------ Create MCP Server (preserve logic) ------------------------
function createNLWebServer(): Server {
  const server = new Server(
    {
      name: "nlweb-mcp-server",
      version: "0.1.0",
    },
    {
      capabilities: {
        tools: {},
        resources: {},
      },
    }
  );

  const allWidgets = [nlwebListWidget, nlwebVisualizationWidget];

  // List resources (widgets)
  server.setRequestHandler(ListResourcesRequestSchema, async () => {
    return {
      resources: allWidgets.map((widget) => ({
        uri: widget.templateUri,
        mimeType: "text/html+skybridge",
        name: widget.title,
        description: `${widget.title} widget markup`,
        _meta: widgetMeta(widget),
      })),
    };
  });

  // Read resource (return widget HTML)
  server.setRequestHandler(ReadResourceRequestSchema, async (request) => {
    const widget = allWidgets.find((w) => w.templateUri === request.params.uri);
    if (widget) {
      return {
        contents: [
          {
            uri: widget.templateUri,
            mimeType: "text/html+skybridge",
            text: widget.html,
            _meta: widgetMeta(widget),
          },
        ],
      };
    }
    throw new Error(`Resource not found: ${request.params.uri}`);
  });

  // List tools
  server.setRequestHandler(ListToolsRequestSchema, async () => {
    return {
      tools: [
        {
          name: "nlweb-search",
          title: "NLWeb Search",
          description:
            "Query NLWeb to search and analyze information from configured data sources. " +
            "Returns structured results (Schema.org data) or visualizations (charts, maps, rankings, embedded content). " +
            "Use mode='list' by default unless user specifically asks to 'generate' or 'summarize'.",
          inputSchema: {
            type: "object",
            properties: {
              query: {
                type: "string",
                description: "The question or search query",
              },
              site: {
                type: "string",
                description:
                  "Optional site to search (e.g., 'datacommons'). Use the bare site name without domain extension.",
              },
              mode: {
                type: "string",
                enum: ["list", "summarize", "generate"],
                description:
                  "Response generation mode. Use 'list' (default) to show structured results. Only use 'summarize' if user explicitly asks for a summary, or 'generate' if user asks to generate new content.",
                default: "list",
              },
              prev: {
                type: "array",
                items: { type: "string" },
                description: "Previous conversation turns for context",
              },
            },
            required: ["query"],
          },
          _meta: widgetMeta(nlwebListWidget),
        },
      ],
    };
  });

  // Call tool (nlweb-search)
  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    if (request.params.name === "nlweb-search") {
      try {
        const params = NLWebAskInputSchema.parse(request.params.arguments);
        const response = await callNLWebAsk(params);

        const widget = selectWidget(response);

        const widgetResource = {
          type: "resource" as const,
          resource: {
            uri: widget.templateUri,
            mimeType: "text/html+skybridge",
            text: widget.html,
          },
        };

        return {
          content: response.content,
          structuredContent: response.structuredContent,
          _meta: {
            "openai.com/widget": widgetResource,
            ...widgetMeta(widget),
          },
        };
      } catch (error) {
        if (error instanceof z.ZodError) {
          throw new Error(`Invalid input parameters: ${error.message}`);
        }

        const errorMessage = error instanceof Error ? error.message : "Unknown error";

        return {
          content: [
            {
              type: "text",
              text: `Error: ${errorMessage}`,
            },
          ],
          isError: true,
        };
      }
    }

    throw new Error(`Unknown tool: ${request.params.name}`);
  });

  return server;
}

// ------------------------ HTTP transport + server ------------------------

// Helper to parse JSON body from IncomingMessage
async function parseJsonBody(req: IncomingMessage): Promise<any> {
  const chunks: Buffer[] = [];
  for await (const chunk of req) {
    chunks.push(typeof chunk === "string" ? Buffer.from(chunk) : chunk);
  }
  if (chunks.length === 0) return {};
  const raw = Buffer.concat(chunks).toString();
  try {
    return JSON.parse(raw);
  } catch {
    // If client sends non-JSON or empty, return empty object
    return {};
  }
}

const PORT = Number(process.env.PORT ?? 8000);

const httpServer = createServer(async (req: IncomingMessage, res: ServerResponse) => {
  try {
    if (!req.url) {
      res.writeHead(400).end("Missing URL");
      return;
    }

    const url = new URL(req.url, `http://${req.headers.host ?? "localhost"}`);

    // CORS preflight for /mcp
    if (req.method === "OPTIONS" && url.pathname === "/mcp") {
      res.writeHead(204, {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "content-type",
      });
      res.end();
      return;
    }

    if (req.method === "POST" && url.pathname === "/mcp") {
      // parse body (we pass parsed JSON to transport.handleRequest)
      const body = await parseJsonBody(req);

      // create server and transport per request
      const server = createNLWebServer();
      const transport = new StreamableHTTPServerTransport({
        sessionIdGenerator: undefined,
        enableJsonResponse: true,
      });

      // Ensure transport closed if client disconnects
      res.on("close", () => {
        try {
          transport.close();
        } catch (e) {
          // ignore
        }
      });

      await server.connect(transport);
      await transport.handleRequest(req, res, body);
      return;
    }

    // Not found
    res.writeHead(404).end("Not Found");
  } catch (err) {
    console.error("Unhandled error in HTTP server:", err);
    if (!res.headersSent) {
      res.writeHead(500).end("Internal Server Error");
    } else {
      try {
        res.end();
      } catch {}
    }
  }
});

httpServer.on("clientError", (err: Error, socket) => {
  console.error("HTTP client error", err);
  socket.end("HTTP/1.1 400 Bad Request\r\n\r\n");
});

httpServer.listen(PORT, () => {
  console.log(`NLWeb MCP server (Streamable HTTP) listening on http://localhost:${PORT}/mcp`);
  console.log(`  NLWEB_APPSDK_BASE_URL: ${NLWEB_APPSDK_BASE_URL}`);
  console.log(`  REQUEST_TIMEOUT: ${REQUEST_TIMEOUT}ms`);
});
