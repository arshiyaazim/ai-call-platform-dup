/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  async rewrites() {
    const apiUrl = process.env.FAZLE_API_URL || "http://fazle-api:8100";
    const wbomUrl = process.env.WBOM_API_URL || "http://wbom:9900";
    return [
      {
        source: "/api/fazle/:path*",
        destination: `${apiUrl}/fazle/:path*`,
      },
      {
        source: "/api/wbom/:path*",
        destination: `${wbomUrl}/api/wbom/:path*`,
      },
      {
        source: "/api/setup-status",
        destination: `${apiUrl}/auth/setup-status`,
      },
      {
        source: "/api/setup",
        destination: `${apiUrl}/auth/setup`,
      },
      {
        source: "/api/admin/:path*",
        destination: `${apiUrl}/auth/:path*`,
      },
    ];
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-XSS-Protection", value: "1; mode=block" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
