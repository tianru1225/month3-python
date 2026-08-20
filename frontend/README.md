# Month3 前端预览

这是当前 FastAPI 后端的 React + TypeScript 前端预览工作台。

## 当前范围

- FastAPI OpenAPI 是前端 API 契约的唯一来源。
- 浏览器请求统一使用同源 `/api` 前缀。
- API Key、JWT、密码、数据库地址和 Provider 密钥不得写入 `VITE_*` 变量。
- Frontend-P1 只实现服务总览；流式对话和登录状态分别在 P2、P3 实现。

## 常用命令

```bash
npm install
npm run api:types
npm run build
npm run dev
```