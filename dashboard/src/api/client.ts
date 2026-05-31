const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface Position {
  symbol: string;
  quantity: number;
  avg_price: number;
}

export interface Portfolio {
  cash: number;
  positions: Position[];
  total_value: number;
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`);
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  health: () => getJson<{ status: string }>("/health"),
  version: () => getJson<{ version: string }>("/version"),
  portfolio: () => getJson<Portfolio>("/portfolio"),
};
