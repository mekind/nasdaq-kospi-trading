# trading-dashboard

NASDAQ/KOSPI 매매 현황 웹 대시보드 (Vite + React + TypeScript).

engine의 FastAPI(`/health`, `/portfolio` 등)를 호출해 포트폴리오/전략 상태를 시각화한다.

## 개발

```bash
npm install
npm run dev        # http://localhost:5173
npm run typecheck
npm run build
```

API 주소는 `.env`의 `VITE_API_BASE_URL`로 설정한다 (기본 `http://localhost:8000`).
