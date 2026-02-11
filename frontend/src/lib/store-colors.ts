export const STORE_COLORS: Record<string, string> = {
  Tesco: "#00539F",
  Dunnes: "#6B2D5B",
  SuperValu: "#E31837",
  Aldi: "#00205B",
  Lidl: "#0050AA",
};

const DEFAULT_COLOR = "#888888";

export function getStoreColor(storeName: string): string {
  for (const [key, color] of Object.entries(STORE_COLORS)) {
    if (storeName.toLowerCase().includes(key.toLowerCase())) {
      return color;
    }
  }
  return DEFAULT_COLOR;
}
