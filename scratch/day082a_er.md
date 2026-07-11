users
-id PK
-username
-email


conversations
-id PK
-user_id FK->users.id
-title
-created_at

messages
-id PK
-conversation_id FK->conversations.id
-role
-content
-created_at

关系:
-一个user有多个conversation
-一个conversation有多个message
-message通过conversation间接归属于user

索引:
-conversation.user_id
-conversation(user_id,created_at)
-messages.conversation.id
-message(conversation_id,created_at)

事务边界:
-创建会话+写入第一条消息应该在同一个事务中完成
-追加消息只写messages,但必须确认conversation属于当前user，防止用户a向用户b的会话里塞消息
-删除conversation是messages应该一起删除