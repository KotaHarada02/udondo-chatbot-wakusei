/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    unoptimized: true,
  },
  // 手元の開発では、/api/v1 を手元の FastAPI に転送する。Vercel では vercel.json の rewrites が働く
  async rewrites() {
    if (process.env.NODE_ENV !== "development") return []
    return [{ source: "/api/v1/:path*", destination: `${process.env.BACKEND_URL ?? "http://127.0.0.1:8000"}/api/v1/:path*` }]
  },
}

export default nextConfig
