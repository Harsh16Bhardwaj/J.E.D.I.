import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  async rewrites() {
    return process.env.NODE_ENV === "development"
      ? [{ source: "/svc/ml/:path*", destination: "http://127.0.0.1:8000/:path*" }]
      : [];
  },
  images: {
    // Vercel Services currently routes /_next/image away from the Next service.
    // Local assets are already deployment-owned, so serve them directly.
    unoptimized: true,
  },
  reactCompiler: true,
};

export default nextConfig;
