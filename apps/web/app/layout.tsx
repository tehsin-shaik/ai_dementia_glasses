import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MemoryCue",
  description: "Software memory assistant prototype",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
