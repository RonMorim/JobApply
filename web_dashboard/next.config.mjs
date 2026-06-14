/** @type {import('next').NextConfig} */
const nextConfig = {
  // Keep the underlying Node HTTP agent alive and raise the socket timeout
  // so the rewrite proxy doesn't drop long-running LLM responses (~25-35s).
  httpAgentOptions: {
    keepAlive: true,
  },
  experimental: {
    // Increase the proxy response timeout to 120s (default is ~30s in some
    // Next.js versions). Covers TailorAgent + PDF build time with headroom.
    proxyTimeout: 300_000,
  },
  async rewrites() {
    return [
      {
        // Proxy every /api/* request to the FastAPI backend.
        // This makes all fetches same-origin (no CORS) and lets the
        // frontend use relative paths regardless of which port FastAPI runs on.
        source:      '/api/:path*',
        destination: 'http://127.0.0.1:8000/api/:path*',
      },
    ]
  },
}
export default nextConfig;
