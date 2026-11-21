import "@/styles/globals.css";
import type { AppProps } from "next/app";
import Head from "next/head";
import Footer from "@/components/Footer";
import TickerTape from "@/components/TickerTape";

export default function App({ Component, pageProps }: AppProps) {
  return (
    <>
      <Head>
        <title>The Tech Lab Times</title>
      </Head>
      <div className="flex min-h-screen flex-col">
        <div className="flex-1">
          <TickerTape />
          <Component {...pageProps} />
        </div>
        <Footer />
      </div>
    </>
  );
}
