# Month3 前端预览

这是当前 FastAPI 后端的 React + TypeScript 前端预览。

## 当前功能

- 服务健康、PostgreSQL 和 OpenAPI 状态检查；
- 用户名注册；
- 用户名密码登录；
- 当前标签页恢复 JWT 登录状态；
- 退出登录；
- JWT 用户聊天流式输出；
- 取消生成和失败重试。

## API 边界

浏览器统一请求同源 /api。开发服务器把它代理到后端。

用户聊天只调用：

- /api/auth/login
- /api/users
- /api/users/me
- /api/v1/user-chat/stream

浏览器不保存应用 API Key，也不接触 DASHSCOPE_API_KEY。access token 只放在当前标签页的 sessionStorage 中，refresh token 和聊天历史持久化尚未实现。

## 运行命令

~~~bash
npm install
npm run api:types
npm run build
npm run dev