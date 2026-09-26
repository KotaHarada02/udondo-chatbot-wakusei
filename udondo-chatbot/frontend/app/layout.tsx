import type React from "react"
import type { Metadata, Viewport } from "next"
import { Dela_Gothic_One, Zen_Kaku_Gothic_New } from "next/font/google"
import { Analytics } from "@vercel/analytics/next"
import "./globals.css"
import "@/components/manga/manga.css"

// 案B 漫画のコマのテーマの字体。店を足すときは theme.yaml の字体に合わせて差し替える
const display = Dela_Gothic_One({ weight: "400", subsets: ["latin"], variable: "--font-display", display: "swap" })
const body = Zen_Kaku_Gothic_New({ weight: ["500", "700", "900"], subsets: ["latin"], variable: "--font-body", display: "swap" })

export const metadata: Metadata = {
  title: "ウドンド | 惑星のウドンド",
  description: "惑星のウドンドの案内役ウドンドが、店の使い方を答える AI チャットの見本です。",
  icons: {
    icon: [
      { url: "/icon-light-32x32.png", media: "(prefers-color-scheme: light)" },
      { url: "/icon-dark-32x32.png", media: "(prefers-color-scheme: dark)" },
      { url: "/icon.svg", type: "image/svg+xml" },
    ],
    apple: "/apple-icon.png",
  },
}

export const viewport: Viewport = {
  themeColor: "#111111",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ja">
      <body className={`${display.variable} ${body.variable}`} style={{ margin: 0 }}>
        {children}
        <Analytics />
      </body>
    </html>
  )
}
