import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Lets the live HTTP test run its own server next to a running `npm run dev`.
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
};

export default nextConfig;
