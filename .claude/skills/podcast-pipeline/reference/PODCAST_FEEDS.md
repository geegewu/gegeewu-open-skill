# AI 播客 RSS Feed 清单

> 最后更新：2026-03-21

## 英文播客（6 个）

| 播客 | RSS Feed | 过滤 |
|------|----------|------|
| Practical AI | `https://changelog.com/practicalai/feed` | 关键词过滤 |
| Latent Space | `https://rss.flightcast.com/vgnxzgiwwzwke85ym53fjnzu` | 关键词过滤 |
| TWIML AI Podcast | `https://twimlai.com/feed/` | 关键词过滤 |
| Lex Fridman Podcast | `https://lexfridman.com/feed/podcast/` | 关键词过滤 |
| Dwarkesh Podcast | `https://api.substack.com/feed/podcast/69345.rss` | 全量 |
| The Cognitive Revolution | `https://feeds.megaphone.fm/RINTP3108857801` | 关键词过滤 |

> ✅ Latent Space：2025-05 迁移至 FlightCast，新 feed 有标准 enclosure，通用逻辑可直接下载。

## 中文播客（4 个）

| 播客 | RSS Feed | 过滤 | 语言 |
|------|----------|------|------|
| 硅谷101 | `https://feeds.fireside.fm/sv101/rss` | 关键词过滤 | zh |
| 晚点聊 LateTalk | `https://feeds.fireside.fm/latetalk/rss` | 关键词过滤 | zh |
| 张小珺Jun | `https://feed.xyzfm.space/dk4yh3pkpjp3` | 关键词过滤 | zh |
| 屠龙之术 | `https://feed.xyzfm.space/834hyx3v9k74` | 关键词过滤 | zh |

> 中文播客处理差异：转录引擎相同（mlx-whisper），Step 3 提炼时不需要翻译，直接用中文原文提炼。
> 晚点聊/张小珺 话题范围较广，需要 AI/科技关键词过滤（类似 Lex Fridman）。

## YouTube 频道（2 个）

| 频道 | YouTube RSS | 过滤 | 语言 |
|------|-------------|------|------|
| AI Explained | `https://www.youtube.com/feeds/videos.xml?channel_id=UCNJ1Ymd5yFuUPtn21xtRbbw` | 关键词过滤 | en |
| Matthew Berman | `https://www.youtube.com/feeds/videos.xml?channel_id=UCawZsQWqfGSbCI5yjkdVkTA` | 关键词过滤 | en |

> YouTube 频道不下载音频，直接抓取自动生成字幕（YouTube ASR）作为转录文本，跳过 Step 2。
> 依赖：`yt-dlp`（安装在 `~/myenv/`）
