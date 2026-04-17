import { getServerSession } from "next-auth";
import { authOptions } from "../../auth/[...nextauth]/route";

const WBOM_URL = process.env.WBOM_URL || process.env.WBOM_API_URL || "http://fazle-wbom:9900";
const WBOM_KEY = process.env.WBOM_INTERNAL_KEY || "";

async function proxy(req, { params }) {
  const session = await getServerSession(authOptions);
  if (!session) {
    return Response.json({ detail: "Unauthorized" }, { status: 401 });
  }

  const { path } = await params;
  const segments = Array.isArray(path) ? path.join("/") : path;
  const url = new URL(req.url);
  const target = `${WBOM_URL}/api/wbom/${segments}${url.search}`;

  const headers = {
    "Content-Type": "application/json",
    ...(WBOM_KEY ? { "X-INTERNAL-KEY": WBOM_KEY } : {}),
  };

  const fetchOpts = { method: req.method, headers };
  if (req.method !== "GET" && req.method !== "HEAD") {
    try {
      fetchOpts.body = await req.text();
    } catch (_) {}
  }

  const upstream = await fetch(target, fetchOpts);
  const body = await upstream.text();

  return new Response(body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("Content-Type") || "application/json" },
  });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const DELETE = proxy;
export const PATCH = proxy;
