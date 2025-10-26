import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  experimental: {
    // @ts-expect-error — turbo alias пока не типизирован
    turbo: {
      resolveAlias: {
        "@radix-ui/react-avatar": path.resolve(
          __dirname,
          "node_modules/@radix-ui/react-avatar"
        ),
      },
    },
  },
};

export default nextConfig;
