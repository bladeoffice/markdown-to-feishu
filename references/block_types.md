# Feishu Block Types

| block_type | Name | Notes |
|---|---|---|
| 1 | Page | Root block (auto-created) |
| 2 | Text | Paragraph |
| 3 | Heading1 | |
| 4 | Heading2 | |
| 5 | Heading3 | |
| 6 | Heading4 | |
| 7 | Heading5 | |
| 8 | Heading6 | |
| 9 | Heading7 | |
| 10 | Heading8 | |
| 11 | Heading9 | |
| 12 | Bullet | indent_level in style |
| 13 | Ordered | |
| 14 | Code | style.language: 1=plain, 3=python, 4=bash, 5=sql, 6=html, 7=css, 8=xml, 9=json, 10=yaml, 11=js, 12=typescript, 15=go, 16=java, 17=csharp, 18=c, 19=cpp, 20=php |
| 15 | Quote | |
| 17 | Todo | |
| 22 | Divider | |
| 27 | Image | image.token = upload key |
| 30 | Table | |
| 31 | TableCell | |
| 34 | Callout | |

# Image Upload

`POST https://open.feishu.cn/open-apis/im/v1/images`

- Header: `Authorization: Bearer <token>`
- `data`: `{"image_type": "message"}` (form field)
- `files`: `{"file": (filename, binary)}`
- Returns: `{"code": 0, "data": {"image_key": "..."}}`

# Rate Limits

- App: 3 calls/sec max
- Per document: 3 concurrent edits/sec → HTTP 429 when exceeded
- Block batch: max 50 per request
