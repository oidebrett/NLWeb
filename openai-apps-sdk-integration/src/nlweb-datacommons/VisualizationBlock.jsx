import React, { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

/**
 * VisualizationBlock - Renders a single Data Commons or other visualization block
 * 
 * Props:
 * - result: The visualization object with html, script, visualizationType, etc.
 * - index: The index in the results array
 * - displayMode: "pip" | "inline" | "fullscreen"
 * - isLast: Whether this is the last item
 */
export default function VisualizationBlock({ result, index, displayMode, isLast }) {
  const containerRef = useRef(null);
  const [isExpanded, setIsExpanded] = useState(true); // Expanded by default
  const [error, setError] = useState(null);

  const visualizationType = result.visualizationType || result["@type"] || "unknown";
  const html = result.html || "";
  
  // Extract header from HTML if available
  const headerMatch = html.match(/header="([^"]+)"/);
  const header = headerMatch ? headerMatch[1] : `Visualization ${index + 1}`;

  useEffect(() => {
    if (!containerRef.current || !html) {
      console.log('⚠️ VisualizationBlock: Missing container or HTML', { 
        hasContainer: !!containerRef.current, 
        htmlLength: html?.length || 0 
      });
      return;
    }

    try {
      console.log('✅ Injecting HTML for visualization:', visualizationType);
      console.log('HTML to inject:', html.substring(0, 200) + '...');
      
      // Inject the HTML directly into the container
      containerRef.current.innerHTML = html;
      
      console.log('✅ HTML injected successfully');
      
      // Wait for web components to be defined if they're used
      if (html.includes("datacommons-")) {
        console.log('🌐 Data Commons component detected, waiting for definition...');
        // Data Commons web components - they should self-initialize
        // The script tag should already be loaded by the parent component
      }
      
      setError(null);
    } catch (err) {
      console.error("❌ Error rendering visualization:", err);
      setError(err.message);
    }
  }, [html]);

  const handleToggle = () => {
    setIsExpanded(!isExpanded);
  };

  const getVisualizationTypeLabel = () => {
    switch (visualizationType) {
      case "ranking":
        return "📊 Ranking";
      case "map":
        return "🗺️ Map";
      case "highlight":
        return "✨ Highlight";
      case "timeline":
        return "📈 Timeline";
      case "scatter":
        return "📉 Scatter Plot";
      case "bar":
        return "📊 Bar Chart";
      default:
        return "📋 Visualization";
    }
  };

  return (
    <div className="px-3 -mx-2 rounded-2xl hover:bg-black/5">
      <div
        style={{
          borderBottom: isLast ? "none" : "1px solid rgba(0, 0, 0, 0.05)",
        }}
        className="py-3"
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className="text-lg">{getVisualizationTypeLabel()}</span>
            <h3 className="text-sm font-medium">{header}</h3>
          </div>
          <button
            onClick={handleToggle}
            className="p-1 hover:bg-black/5 rounded"
            aria-label={isExpanded ? "Collapse" : "Expand"}
          >
            {isExpanded ? (
              <ChevronUp className="h-4 w-4 text-black/60" />
            ) : (
              <ChevronDown className="h-4 w-4 text-black/60" />
            )}
          </button>
        </div>

        {/* Visualization Content */}
        {isExpanded && (
          <>
            <div
              ref={containerRef}
              className="min-h-[200px] my-3"
            />

            {error && (
              <div className="p-3 bg-red-50 text-red-600 rounded-lg text-sm">
                ⚠️ Error loading visualization: {error}
              </div>
            )}

            {/* Metadata */}
            {(result.places || result.variables) && (
              <div className="flex flex-wrap gap-2 mt-3 text-xs text-black/60">
                {result.places && (
                  <span>
                    <strong>Places:</strong> {result.places.join(", ")}
                  </span>
                )}
                {result.variables && (
                  <span>
                    <strong>Variables:</strong> {result.variables.join(", ")}
                  </span>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
