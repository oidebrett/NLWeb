import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { useWidgetProps } from "../use-widget-props";
import { useOpenAiGlobal } from "../use-openai-global";
import { useMaxHeight } from "../use-max-height";
import { NLWebHeader, NLWebContainer, NLWebEmptyState } from "../shared/NLWebComponents";
import VisualizationBlock from "./VisualizationBlock";
import "./nlweb-datacommons.css";

/**
 * Type definitions matching your data schema:
 * 
 * Message: { message_id, sender_type, message_type, timestamp, content, conversation_id, sender_info }
 * VisualizationResult: { @type, visualizationType, html, script, places, variables, embed_instructions }
 * StructuredContent: { messages, results, metadata, query }
 * NLWebData: { structuredContent, content }
 */

function App() {
  // Get data passed from MCP server via useWidgetProps
  const data = useWidgetProps({});
  const displayMode = useOpenAiGlobal("displayMode");
  const maxHeight = useMaxHeight() ?? undefined;
  const theme = useOpenAiGlobal("theme") || "light";

  const structuredContent = data?.structuredContent;
  const results = structuredContent?.results || [];
  const query = structuredContent?.query || "";
  const messages = structuredContent?.messages || [];

  // Debug logging
  console.log('🎨 Visualization Widget Loaded!');
  console.log('Data received:', { 
    hasData: !!data,
    hasStructuredContent: !!structuredContent,
    resultsCount: results.length,
    query 
  });
  if (results.length > 0) {
    console.log('First result:', results[0]);
  }

  // Track which scripts have been loaded to avoid duplicates
  const [loadedScripts, setLoadedScripts] = useState<Set<string>>(new Set());

  // Extract and load required scripts from results
  useEffect(() => {
    if (!results || results.length === 0) return;

    results.forEach((result) => {
      if (result.script && !loadedScripts.has(result.script)) {
        const scriptTag = document.createElement("div");
        scriptTag.innerHTML = result.script;
        const scriptElement = scriptTag.querySelector("script");
        
        if (scriptElement && scriptElement.src) {
          // Check if script is already in document
          const existingScript = document.querySelector(`script[src="${scriptElement.src}"]`);
          if (!existingScript) {
            const newScript = document.createElement("script");
            newScript.src = scriptElement.src;
            newScript.async = true;
            document.head.appendChild(newScript);
            setLoadedScripts((prev) => new Set(prev).add(result.script));
          }
        }
      }
    });
  }, [results]);

  return (
    <NLWebContainer>
      <NLWebHeader 
        query={query}
        resultCount={results.length}
        onSave={() => console.log('Save functionality')}
      />

      {/* Results Grid */}
      {results.length > 0 ? (
        <div className="min-w-full">
          {results.map((result, index) => (
            <VisualizationBlock
              key={index}
              result={result}
              index={index}
              displayMode={displayMode || "inline"}
              isLast={index === results.length - 1}
            />
          ))}
        </div>
      ) : (
        <NLWebEmptyState message="No visualizations available" />
      )}

      {/* Debug info in development */}
      {process.env.NODE_ENV === "development" && (
        <details className="nlweb-debug">
          <summary>Debug Info</summary>
          <pre>{JSON.stringify(data, null, 2)}</pre>
        </details>
      )}
    </NLWebContainer>
  );
}

// Export for build system
export { App };
export default App;

// Mount the app
const root = document.getElementById("nlweb-datacommons-root");
if (root) {
  createRoot(root).render(<App />);
}
