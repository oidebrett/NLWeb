import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { PlusCircle, Star, FileText, MapPin, ExternalLink } from "lucide-react";
import { useWidgetProps } from "../use-widget-props";
import { NLWebHeader, NLWebContainer, NLWebEmptyState } from "../shared/NLWebComponents";
// Import visualization components for hybrid rendering
import VisualizationBlock from "../nlweb-datacommons/VisualizationBlock";

function getResultIcon(result) {
  const type = result["@type"] || "";
  if (type.includes("Place")) return MapPin;
  if (type.includes("Article")) return FileText;
  return Star;
}

function getResultTitle(result) {
  return result.name || result.title || result.headline || "Untitled";
}

function getResultSubtitle(result) {
  // Try various Schema.org properties
  return result.city || result.location || result.publisher || result.description?.slice(0, 50);
}

function getResultImage(result) {
  // Try direct properties first
  if (result.thumbnail) return result.thumbnail;
  if (result.image) return result.image;
  if (result.thumbnailUrl) return result.thumbnailUrl;
  
  // Check schema_object for nested image
  if (result.schema_object?.image) {
    const schemaImage = result.schema_object.image;
    // Handle if it's an array (take first)
    if (Array.isArray(schemaImage)) {
      return schemaImage[0];
    }
    return schemaImage;
  }
  
  return null;
}

function getResultRating(result) {
  // Use score as rating if available, otherwise try other rating properties
  if (result.score !== undefined && result.score !== null) {
    return result.score;
  }
  return result.rating || result.aggregateRating?.ratingValue || null;
}

function ResultItem({ result, index, isLast }) {
  const [expanded, setExpanded] = React.useState(false);
  const Icon = getResultIcon(result);
  const title = getResultTitle(result);
  const subtitle = getResultSubtitle(result);
  const image = getResultImage(result);
  const rating = getResultRating(result);
  const url = result.url || result.schema_object?.url || null;
  const fullDescription = result.description || result.schema_object?.description || "";
  const hasFullDescription = fullDescription && fullDescription.length > 50;

  return (
    <div
      key={result.id || result.url || index}
      className="px-3 -mx-2 rounded-2xl hover:bg-black/5"
    >
      <div
        style={{
          borderBottom: isLast ? "none" : "1px solid rgba(0, 0, 0, 0.05)",
        }}
        className="flex w-full items-center hover:border-black/0! gap-2"
      >
        <div className="py-3 pr-3 min-w-0 w-full sm:w-3/5">
          <div className="flex items-center gap-3">
            {image ? (
              url ? (
                <a href={url} target="_blank" rel="noopener noreferrer">
                  <img
                    src={image}
                    alt={title}
                    className="h-10 w-10 sm:h-11 sm:w-11 rounded-lg object-cover ring ring-black/5 hover:ring-blue-500 transition-all cursor-pointer"
                  />
                </a>
              ) : (
                <img
                  src={image}
                  alt={title}
                  className="h-10 w-10 sm:h-11 sm:w-11 rounded-lg object-cover ring ring-black/5"
                />
              )
            ) : (
              <div className="h-10 w-10 sm:h-11 sm:w-11 rounded-lg bg-black/5 flex items-center justify-center">
                <Icon className="h-5 w-5 text-black/40" strokeWidth={1.5} />
              </div>
            )}
            <div className="w-3 text-end sm:block hidden text-sm text-black/40">
              {index + 1}
            </div>
            <div className="min-w-0 sm:pl-1 flex flex-col items-start h-full w-full">
              {url ? (
                <a
                  href={url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-medium text-sm sm:text-md truncate max-w-[40ch] text-blue-600 hover:text-blue-700 hover:underline inline-flex items-center gap-1"
                >
                  {title}
                  <ExternalLink className="h-3 w-3 inline-block flex-shrink-0" />
                </a>
              ) : (
                <div className="font-medium text-sm sm:text-md truncate max-w-[40ch]">
                  {title}
                </div>
              )}
              <div className="mt-1 sm:mt-0.25 flex items-center gap-3 text-black/70 text-sm">
                {rating && (
                  <div className="flex items-center gap-1">
                    <Star
                      strokeWidth={1.5}
                      className="h-3 w-3 text-black"
                    />
                    <span>
                      {typeof rating === 'number' ? rating.toFixed(1) : rating}
                    </span>
                  </div>
                )}
                {subtitle && !expanded && (
                  <div className="whitespace-nowrap truncate max-w-[30ch]">
                    {subtitle}
                  </div>
                )}
              </div>
              {hasFullDescription && (
                <div className="mt-2 w-full">
                  <div 
                    className={`text-sm text-black/70 ${expanded ? '' : 'line-clamp-2'}`}
                  >
                    {fullDescription}
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setExpanded(!expanded);
                    }}
                    className="mt-1 text-xs text-blue-600 hover:text-blue-700 font-medium"
                  >
                    {expanded ? 'Show less' : 'Show more'}
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
        <div className="hidden sm:block text-end py-2 px-3 text-sm text-black/60 whitespace-nowrap flex-auto">
          {result["@type"] || "–"}
        </div>
        <div className="py-2 whitespace-nowrap flex justify-end">
          <PlusCircle strokeWidth={1.5} className="h-5 w-5" />
        </div>
      </div>
    </div>
  );
}

function App() {
  const props = useWidgetProps();
  const results = props?.results || [];
  const query = props?.query || "";
  const metadata = props?.metadata || {};
  const [loadedScripts, setLoadedScripts] = useState(new Set());

  // Detect if results contain visualizations
  const hasVisualizations = results.some(r => r.visualizationType || r.html || r.script);

  // Load required scripts for visualizations
  useEffect(() => {
    if (!hasVisualizations) return;

    results.forEach((result) => {
      if (result.script && !loadedScripts.has(result.script)) {
        const scriptTag = document.createElement("div");
        scriptTag.innerHTML = result.script;
        const scriptElement = scriptTag.querySelector("script");
        
        if (scriptElement && scriptElement.src) {
          const existingScript = document.querySelector(`script[src="${scriptElement.src}"]`);
          if (!existingScript) {
            const newScript = document.createElement("script");
            newScript.src = scriptElement.src;
            newScript.async = true;
            document.head.appendChild(newScript);
            setLoadedScripts((prev) => new Set(prev).add(result.script));
            console.log('✅ Loaded script:', scriptElement.src);
          }
        }
      }
    });
  }, [results, hasVisualizations]);

  console.log('🎨 NLWeb List Widget:', { 
    resultsCount: results.length, 
    hasVisualizations,
    firstResultType: results[0]?.['@type']
  });

  return (
    <NLWebContainer>
      <NLWebHeader 
        query={query}
        resultCount={results.length}
        onSave={() => console.log('Save results')}
      />
      
      <div className="min-w-full text-sm flex flex-col">
        {results.map((result, i) => {
          // If result has visualization data, use VisualizationBlock
          if (result.visualizationType || result.html || result.script) {
            return (
              <VisualizationBlock
                key={i}
                result={result}
                index={i}
                displayMode="inline"
                isLast={i === results.length - 1}
              />
            );
          }
          // Otherwise use regular ResultItem for Schema.org data
          return (
            <ResultItem
              key={result.id || result.url || i}
              result={result}
              index={i}
              isLast={i === results.length - 1}
            />
          );
        })}
        {results.length === 0 && (
          <NLWebEmptyState />
        )}
      </div>
      
      <div className="sm:hidden px-0 pt-2 pb-2">
        <button
          type="button"
          className="w-full cursor-pointer inline-flex items-center justify-center rounded-full bg-blue-600 text-white px-4 py-2 font-medium hover:opacity-90 active:opacity-100"
        >
          Save Results
        </button>
      </div>
    </NLWebContainer>
  );
}

// Export for build system
export { App };
export default App;

const rootElement = document.getElementById("nlweb-list-root");
if (rootElement) {
  createRoot(rootElement).render(<App />);
}
