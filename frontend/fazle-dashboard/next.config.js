/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  basePath: '',
  async rewrites() {
    return [
      {
        source: '/api/fazle/:path*',
        destination: `${process.env.FAZLE_API_URL || 'http://fazle-api:8100'}/fazle/:path*`,
      },
      {
        source: '/api/ops/:path*',
        destination: `${process.env.OPS_CORE_URL || 'http://ops-core-service:9850'}/ops/:path*`,
      },
      {
        source: '/api/facebook/:path*',
        destination: `${process.env.FAZLE_API_URL || 'http://fazle-api:8100'}/fazle/gdpr/facebook-deletion`,
      },
    ];
  },
};

module.exports = nextConfig;
