import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MemoryCue — Memory, when you need it.",
  description: "AI-assisted memory support for people experiencing memory loss and the caregivers who support them.",
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
