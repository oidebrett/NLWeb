import React from "react";
import { FileText } from "lucide-react";

/**
 * Shared Header component for NLWeb widgets
 * Shows query, result count, and optional action button
 */
export function NLWebHeader({ query, resultCount, icon: Icon = FileText, onSave }) {
  return (
    <div className="max-w-full">
      <div className="flex flex-row items-center gap-4 sm:gap-4 border-b border-black/5 py-4">
        <div
          className="sm:w-18 w-16 aspect-square rounded-xl bg-cover bg-center bg-blue-500/10 flex items-center justify-center"
        >
          <Icon className="h-8 w-8 text-blue-600" strokeWidth={1.5} />
        </div>
        <div>
          <div className="text-base sm:text-xl font-medium">
            {query || "NLWeb Results"}
          </div>
          <div className="text-sm text-black/60">
            {resultCount} result{resultCount !== 1 ? 's' : ''} found
          </div>
        </div>
        {onSave && (
          <div className="flex-auto hidden sm:flex justify-end pr-2">
            <button
              type="button"
              onClick={onSave}
              className="cursor-pointer inline-flex items-center rounded-full bg-blue-600 text-white px-4 py-1.5 sm:text-md text-sm font-medium hover:opacity-90 active:opacity-100"
            >
              Save Results
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Shared Container wrapper for NLWeb widgets
 */
export function NLWebContainer({ children, className = "" }) {
  return (
    <div className={`antialiased w-full text-black px-4 pb-2 border border-black/10 rounded-2xl sm:rounded-3xl overflow-hidden bg-white ${className}`}>
      {children}
    </div>
  );
}

/**
 * Shared Empty State component
 */
export function NLWebEmptyState({ message = "No results found." }) {
  return (
    <div className="py-6 text-center text-black/60">
      {message}
    </div>
  );
}
