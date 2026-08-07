import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    // Vercel Services currently routes /_next/image away from the Next service.
    // Local assets are already deployment-owned, so serve them directly.
    unoptimized: true,
  },
  reactCompiler: true,
};

export default nextConfig;
