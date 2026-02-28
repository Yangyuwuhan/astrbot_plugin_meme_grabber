# AstrBot 表情包提取插件

## 功能介绍

这是一个专为 AstrBot 设计的插件，用于将 QQ 表情包提取为可保存的文件格式。
支持直接发送图片或回复包含图片的消息来提取表情包。

## 功能特点

- 支持提取普通表情包和官方表情包
- 自动检测图片类型并使用相应的扩展名
- 支持多种图片格式（如 JPG、PNG、GIF 等）

## 安装方法

1. 下载zip文件并解压，将插件目录 `astrbot_plugin_meme_grabber` 复制到 AstrBot 的 `data/plugins` 目录下
2. 重启 AstrBot 或在插件管理页面中手动加载插件

## 使用说明

引用表情包并使用指令 `/转换`

## 配置选项

插件支持以下配置选项，可在插件管理页面中修改：

| 配置项            | 描述                   | 默认值                                       |
| ----------------- | ---------------------- | -------------------------------------------- |
| temp_dir          | 临时文件保存目录       | data/plugin_data/astrbot_plugin_meme_grabber |
| delete_after_send | 发送后删除临时文件     | true                                         |
| default_extension | 默认图片扩展名         | jpg                                          |
| download_timeout  | 图片下载超时时间（秒） | 10                                           |

## 注意事项

该插件仅支持 QQ 平台（aiocqhttp）

## 许可证

AGPL License

## 声明

1. 本插件的最初构想来源于 [orchidsziyou](https://github.com/orchidsziyou) 的 [astrbot_plugins_ConvetPicture](https://github.com/orchidsziyou/astrbot_plugins_ConvetPicture) 插件，Yangyuwuhan 将整个插件进行了重构。
2. 本插件使用了AI，但作者已对其进行了严格的审查和测试。

## 改动

与 [astrbot_plugins_ConvetPicture](https://github.com/orchidsziyou/astrbot_plugins_ConvetPicture) 相比，本插件做了如下改动:

1. 优化代码逻辑，大幅简化代码
2. 新增了可能用到的配置文件
3. 修复了输出的文件名不正确的问题
4. 修复了插件会阻止LLM功能的问题

## 相关链接

- [astrbot_plugins_ConvetPicture](https://github.com/orchidsziyou/astrbot_plugins_ConvetPicture)
- [astrbot_plugin_meme_grabber](https://github.com/Yangyuwuhan/astrbot_plugin_meme_grabber)
- [AstrBot](https://astrbot.app)


