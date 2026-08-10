/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  allowedDevOrigins: ["127.0.0.1"],
  distDir: process.env.RADAR_NEXT_DIST_DIR || ".next",
  async rewrites() {
    const backend = process.env.RADAR_BACKEND_URL || "http://127.0.0.1:8001";
    return [
      { source: "/api/:path*", destination: `${backend}/api/:path*` },
      { source: "/health", destination: `${backend}/health` }
    ];
  },
};

export default nextConfig;
