# XiyusLogin - 安全登录验证模组

![Minecraft](https://img.shields.io/badge/Minecraft-1.21.1-green.svg)
![NeoForge](https://img.shields.io/badge/NeoForge-21.1.180-orange.svg)
![Java](https://img.shields.io/badge/Java-21-blue.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

一个功能强大且安全的Minecraft服务器登录验证模组，为服务器提供完整的玩家身份验证和保护系统。

## 🌟 核心特性

### 🔐 安全认证系统
- **通用验证**: 所有玩家（包括正版和盗版）都需要注册/登录
- **密码加密**: 使用SHA-256加盐哈希算法，确保密码安全
- **会话管理**: 智能会话跟踪，防止重复登录

### 🛡️ 全面保护机制
- **背包保护**: 登录前背包内容完全隐藏，验证成功后自动恢复
- **移动限制**: 未验证玩家无法移动、攻击或使用物品
- **视觉效果**: 失明、隐身、无敌等效果确保安全
- **超时踢出**: 可配置的验证超时时间，自动踢出未验证玩家

### 💾 智能数据管理
- **JSON存储**: 轻量级数据存储，易于备份和迁移
- **背包备份**: 自动备份和恢复玩家物品，防止数据丢失
- **登录统计**: 记录玩家登录次数和时间

### 🔄 密码重置系统
- **玩家申请**: 玩家可通过游戏内命令申请密码重置
- **管理员审核**: 完整的审核流程，防止恶意重置
- **可视化界面**: 点击式按钮操作，管理更便捷

## 📋 命令系统

### 玩家命令
```
/register <密码> <确认密码>  - 注册新账户
/reg <密码> <确认密码>       - 注册新账户（简写）
/login <密码>               - 登录账户
/lg <密码>                  - 登录账户（简写）
/psforget "原因" <新密码>    - 申请密码重置
```

### 管理员命令
```
/xiyuslogin info <玩家名>              - 查看玩家信息
/xiyuslogin resetpassword <玩家名> <新密码> - 直接重置密码
/xiyuslogin resetrequests             - 查看密码重置请求
/xiyuslogin approve <玩家名>          - 批准密码重置
/xiyuslogin reject <玩家名>           - 拒绝密码重置
/xiyuslogin forceauth <玩家>          - 强制验证玩家
```

## ⚙️ 配置选项

```toml
# 最小密码长度
min_password_length = 4
# 最大密码长度  
max_password_length = 32
# 验证超时时间（秒）
freeze_duration = 300
```

## 🚀 安装指南

1. **下载模组**: 从发布页面下载最新版本的XiyusLogin
2. **安装NeoForge**: 确保服务器运行NeoForge 21.1.180或更高版本
3. **放置模组**: 将模组文件放入服务器的`mods`文件夹
4. **启动服务器**: 重启服务器以加载模组
5. **配置设置**: 根据需要修改配置文件

## 🎮 使用流程

### 新玩家注册
1. 玩家首次进入服务器
2. 系统提示注册命令
3. 使用`/register 密码 确认密码`注册
4. 注册成功后自动验证，恢复背包

### 老玩家登录
1. 已注册玩家进入服务器
2. 系统提示登录命令
3. 使用`/login 密码`登录
4. 登录成功后解除限制，恢复背包

### 密码重置
1. 玩家使用`/psforget "忘记原因" 新密码`申请
2. 管理员使用`/xiyuslogin resetrequests`查看申请
3. 管理员点击批准或拒绝按钮处理申请

## 🔧 技术特性

- **异步处理**: 非阻塞式验证，不影响服务器性能
- **内存优化**: 高效的数据结构，最小化内存占用
- **并发安全**: 线程安全的设计，支持高并发访问
- **错误恢复**: 完善的异常处理和数据恢复机制

## 📁 文件结构

```
world/
├── xiyus_player_data.json           # 玩家数据文件
├── xiyus_password_reset_requests.json # 密码重置请求
└── xiyus_player_inventories/        # 背包备份目录
    ├── player1_inventory.json
    └── player2_inventory.json
```

## 🛠️ 开发信息

- **开发者**: Xiyu
- **版本**: 1.0.0
- **兼容性**: Minecraft 1.21.1 + NeoForge 21.1.180+
- **开发语言**: Java 21

## 📝 更新日志

### v1.0.0
- ✨ 初始发布版本
- 🔐 完整的注册/登录系统
- 🛡️ 背包保护和移动限制
- 🔄 密码重置功能
- 🎮 可视化管理界面

## 🤝 支持与反馈

如果您在使用过程中遇到问题或有建议，请：
- 在Gitee上提交Issue
- 加入我们的QQ群：973951057

## 📄 许可证

本项目采用MIT许可证，详情请参阅[LICENSE](LICENSE)文件。

## ⭐ 致谢

感谢所有使用和支持XiyusLogin的服务器管理员和玩家！

---

**让您的Minecraft服务器更加安全可靠！** 🚀
