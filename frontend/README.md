# Month3 前端预览

这是当前 FastAPI 后端的 React + TypeScript 前端预览。

## 当前功能

- 服务健康、PostgreSQL 和 OpenAPI 状态检查；
- 用户名注册；
- 用户名密码登录；
- 当前标签页恢复 JWT 登录状态；
- 退出登录；
- JWT 用户聊天流式输出；
- 取消生成；
- 失败后手动重试上一条；
- 401、403、429、502、503、504 错误展示；
- 流式公开错误码和 retryable 状态展示。

## API 边界

浏览器统一请求同源 /api。开发服务器把它代理到后端。

用户聊天只调用：

- /api/auth/login
- /api/users
- /api/users/me
- /api/v1/user-chat/stream

浏览器不保存应用 API Key，也不接触 DASHSCOPE_API_KEY。access token 只放在当前标签页的 sessionStorage 中，refresh token 和聊天历史持久化尚未实现。

## 错误处理

错误提示只显示后端公开错误码和面向用户的说明，不显示 DashScope 原始响应、请求体、JWT 或服务密钥。

retryable 只用于说明错误是否可能暂时恢复。页面不自动重试，但保留“重试上一条”按钮，由用户手动触发。

## 运行命令

~~~bash
npm install
npm run api:types
npm run build
npm run dev