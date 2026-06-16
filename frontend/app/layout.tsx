import "./globals.css";
import type { Metadata } from "next";


export const metadata: Metadata = {
  title: "Timeblind AI",
  description: "Adaptive temporal support for people who experience time blindness."
};


export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
