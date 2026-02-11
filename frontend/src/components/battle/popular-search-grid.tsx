"use client";

import { Button } from "@/components/ui/button";

const POPULAR_SEARCHES = [
  "milk", "bread", "chicken", "rice", "butter", "cheese",
  "eggs", "pasta", "sugar", "tea", "coffee", "water",
  "beef", "salmon", "yoghurt", "cereal", "oil", "flour",
];

interface PopularSearchGridProps {
  onSelect: (term: string) => void;
}

export function PopularSearchGrid({ onSelect }: PopularSearchGridProps) {
  return (
    <div>
      <p className="text-sm text-muted-foreground mb-2">Popular searches:</p>
      <div className="grid grid-cols-3 sm:grid-cols-6 lg:grid-cols-9 gap-2">
        {POPULAR_SEARCHES.map((term) => (
          <Button
            key={term}
            variant="outline"
            size="sm"
            className="capitalize"
            onClick={() => onSelect(term)}
          >
            {term}
          </Button>
        ))}
      </div>
    </div>
  );
}
