import "./globals.css";
import type { Metadata } from "next";


export const metadata: Metadata = {
  title: "TimeBlindAI",
  description: "Task planning, scheduling, focus sessions, and review insights for time-blind productivity."
};


export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
