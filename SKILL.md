---
name: markdown-to-feishu
description: 将 Markdown 文件（含本地图片）发布为飞书文档。当用户要求将 md/markdown 文档上传、发布、创建到飞书时使用。支持自动解析 frontmatter 标题、标题层级、列表、代码块、表格、图片（本地图片自动上传）。默认上传到「学习」文件夹。
---

# feishu_create_doc

将 Markdown 文件发布为飞书在线文档。

## 环境变量

```bash
FEISHU_APP_ID      # 飞书应用 app_id
FEISHU_APP_SECRET  # 飞书应用 app_secret
```

## 使用方式

```bash
python skills/feishu_create_doc/scripts/create_doc.py <md_file> [folder_token] [title]
```

**示例：**
```bash
# 上传到「学习」文件夹
python skills/feishu_create_doc/scripts/create_doc.py "~/文档/笔记.md"

# 上传到指定文件夹
python skills/feishu_create_doc/scripts/create_doc.py "~/文档/笔记.md" "fldxxxxxx" "自定义标题"
```

## 工作流程

1. 读取 MD 文件，解析 frontmatter（如有 title 字段则优先使用）
2. 从第一个 `# 标题` 或文件名提取文档标题
3. 获取 tenant_access_token
4. 在指定 folder 创建文档
5. 将本地图片上传到飞书（获取 image_key）
6. 将 Markdown 转换为飞书块结构（批量创建，每次最多 50 个）
7. 返回文档链接

## Markdown → 块类型映射

| Markdown | 飞书 block_type |
|---|---|
| `# H1` | 3 |
| `## H2` | 4 |
| ... | ... |
| `---` | 22 (Divider) |
| `` `code` `` | 2 (inline) |
| ` ```lang\ncode\n``` ` | 14 (Code) |
| `- item` | 12 (Bullet) |
| `1. item` | 13 (Ordered) |
| `> quote` | 15 (Quote) |
| `!!! tip` | 34 (Callout) |
| `| table |` | 30+31 (Table) |
| `![alt](local_path)` | 27 (Image) |

**速率限制：**
- API 全局：3 次/秒，429 时自动重试
- 单文档编辑：3 次/秒，429 时自动重试
- 每次批量最多 50 个 block

详细 block_type 代码见 `references/block_types.md`。

## 参数说明

- **folder_token**：飞书文件夹 ID，省略则上传到默认文件夹（见下方备注）
- **title**：文档标题，省略则从 MD 文件的 frontmatter 或第一个 `#` 标题自动提取

