import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // The news feed is the front page of the deployed site.
  async redirects() {
    return [{ source: "/", destination: "/news", permanent: false }];
  },
};

export default nextConfig;
