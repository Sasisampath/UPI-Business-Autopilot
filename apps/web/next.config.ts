import type { NextConfig } from "next";

// The browser only ever talks to this origin; /api/* is proxied to the FastAPI service.
const API_URL = process.env.API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async headers() {
    // Baseline hardening for a shared preview. The microphone is allowed for the voice assistant only.
    return [{
      source: "/:path*",
      headers: [
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "X-Frame-Options", value: "DENY" },
        { key: "Referrer-Policy", value: "no-referrer" },
        { key: "Permissions-Policy", value: "microphone=(self), camera=(self), geolocation=()" },
        { key: "X-Robots-Tag", value: "noindex, nofollow" },
      ],
    }];
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/:path*` }];
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
