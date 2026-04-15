/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  basePath: '',
  async rewrites() {
    return [
      {
        source: '/api/fazle/wbom/:path*',
        destination: `${process.env.WBOM_URL || 'http://fazle-wbom:9900'}/api/wbom/:path*`,
      },
      {
        source: '/api/fazle/:path*',
        destination: `${process.env.FAZLE_API_URL || 'http://fazle-api:8100'}/fazle/:path*`,
      },
      {
        source: '/api/facebook/:path*',
        destination: `${process.env.FAZLE_API_URL || 'http://fazle-api:8100'}/fazle/gdpr/facebook-deletion`,
      },
    ];
  },
};

module.exports = nextConfig;
