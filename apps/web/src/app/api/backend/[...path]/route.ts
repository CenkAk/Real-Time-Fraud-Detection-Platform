import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

const backendUrl = process.env.API_INTERNAL_URL ?? "http://localhost:8000";
const allowedRoots = new Set([
  "admin",
  "alerts",
  "analytics",
  "health",
  "model",
  "predictions",
  "transactions",
]);

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  if (!path.length || !allowedRoots.has(path[0])) {
    return NextResponse.json({ detail: "Route is not available through the BFF" }, { status: 404 });
  }
  const upstream = new URL(path.map(encodeURIComponent).join("/"), `${backendUrl}/`);
  upstream.search = request.nextUrl.search;
  const body = request.method === "GET" || request.method === "HEAD" ? undefined : await request.text();
  try {
    const response = await fetch(upstream, {
      method: request.method,
      body,
      headers: {
        accept: "application/json",
        "content-type": request.headers.get("content-type") ?? "application/json",
        "x-request-id": request.headers.get("x-request-id") ?? crypto.randomUUID(),
      },
      cache: "no-store",
    });
    return new NextResponse(response.body, {
      status: response.status,
      headers: {
        "content-type": response.headers.get("content-type") ?? "application/json",
        "x-request-id": response.headers.get("x-request-id") ?? "",
      },
    });
  } catch {
    return NextResponse.json({ detail: "Fraud API is unavailable" }, { status: 503 });
  }
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
