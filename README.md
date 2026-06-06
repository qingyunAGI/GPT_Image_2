# GPT Image 2 Generator

一个 macOS 本地 Web 小工具，用 Azure OpenAI 的 GPT Image 部署生成图片。

## 功能

- 文本生成图片
- 上传 PNG/JPG 作为参考图或待编辑图片
- 支持多张并发生成
- 支持比例、质量和数量设置
- 自动保存生成结果到 `~/Documents/GPT_IMAGE_2`

## 使用

先设置环境变量：

```bash
launchctl setenv OPENAI_API_KEY "your-key-here"
launchctl setenv AZURE_OPENAI_IMAGE_ENDPOINT "your-endpoint"
```

可选：覆盖图片 API 版本。

```bash
launchctl setenv AZURE_OPENAI_IMAGE_API_VERSION "2025-04-01-preview"
```

然后双击 `GPT_Image_2.command` 启动。

