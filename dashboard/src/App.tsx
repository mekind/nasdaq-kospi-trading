import { useEffect, useState } from "react";
import { api, type Portfolio } from "./api/client";

export default function App() {
  const [status, setStatus] = useState<string>("연결 확인 중...");
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);

  useEffect(() => {
    api
      .health()
      .then((h) => setStatus(`엔진 연결됨: ${h.status}`))
      .catch(() => setStatus("엔진 미연결 (engine API를 실행하세요)"));
    api.portfolio().then(setPortfolio).catch(() => setPortfolio(null));
  }, []);

  return (
    <main style={{ fontFamily: "system-ui", maxWidth: 720, margin: "2rem auto", padding: "0 1rem" }}>
      <h1>NASDAQ / KOSPI Trading Dashboard</h1>
      <p style={{ color: "#666" }}>{status}</p>

      <section>
        <h2>포트폴리오</h2>
        {portfolio ? (
          <ul>
            <li>현금: {portfolio.cash.toLocaleString()}</li>
            <li>총 평가액: {portfolio.total_value.toLocaleString()}</li>
            <li>보유 종목: {portfolio.positions.length}개</li>
          </ul>
        ) : (
          <p>데이터 없음</p>
        )}
      </section>
    </main>
  );
}
