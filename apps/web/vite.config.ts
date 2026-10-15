import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// data/mock/case/*.json을 저장소 원본 그대로 읽는다. 복사본을 두면 fixture가
// 갱신될 때 화면이 옛 값을 그린다 — 「web은 CaseView를 그대로 소비한다」의 증빙이
// 사본이 되어서는 안 된다. 그래서 루트 밖 읽기를 열어 둔다.
// `/cases`는 API 서버로 넘긴다(`?api`) — 같은 origin처럼 부르므로 CORS 설정이 필요 없다.
// ponytail: 기본 주소 8000은 uvicorn 기본값을 가정한 것이다 — 서버 포트가 정해지면(RT-08) 맞춘다. `API_PROXY_TARGET`으로 바꾼다.
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  server: {
    fs: { allow: ['../..'] },
    proxy: { '/cases': loadEnv(mode, '.', '').API_PROXY_TARGET ?? 'http://localhost:8000' },
  },
}))
