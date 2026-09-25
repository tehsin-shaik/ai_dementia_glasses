import type { Metadata } from "next";
import { IBM_Plex_Sans_Arabic, Inter, Outfit } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
});

const outfit = Outfit({
  subsets: ["latin"],
  variable: "--font-display",
});

const plexArabic = IBM_Plex_Sans_Arabic({
  subsets: ["arabic"],
  weight: ["400", "500", "600"],
  variable: "--font-arabic",
});

export const metadata: Metadata = {
  title: "MemoryCue — Memory, when you need it.",
  description: "AI-assisted memory support that brings everyday context back into view for people experiencing memory loss and their caregivers.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${outfit.variable} ${plexArabic.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}
