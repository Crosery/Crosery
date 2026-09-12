# Pixel profile — make it yours

A GitHub profile README drawn as a pixel-art RPG title screen: a portrait
sprite standing under a pastel sky, a message window that types your lines,
pinned projects, a contribution calendar, a contribution snake, and a
sign-off card. Every number is fetched from GitHub and the cards are rebuilt
daily by GitHub Actions. Nothing is installed at build time: the generator is
plain Python.

[中文说明](#中文说明) below.

## 1. Fork and rename

1. Fork this repository.
2. Rename the fork to **your login** (Settings → General → Repository name).
   GitHub only shows a profile README from the repository named after you.
3. Settings → Actions → General → *Workflow permissions*: choose **Read and
   write permissions**, so the workflows can commit the cards and push the
   snake to the `output` branch.

## 2. Edit `profile.toml`

That file is the whole configuration; every key has a comment. The ones you
must change:

| key | what |
| --- | --- |
| `github.login` | your GitHub login |
| `hero.title` | the logotype on the hero; letters a–z are hand-drawn, anything else uses the pixel font |
| `dialog.speaker`, `dialog.lines` | the message window; one to three lines |
| `signature.contacts` | the icon menu on the last card; up to six |

Optional: `signature.sign_off` and `farewell`, `hero.facts`, the `[palette]`
(six colours plus the sky bands; the build refuses text that would not be
readable), and `cards.order` to drop or reorder cards.

Text is drawn with a 10 px pixel font that covers Latin, Greek, Cyrillic,
kana and GB2312 Chinese. Emoji have no glyph and are dropped from
GitHub-sourced text; in `profile.toml` they fail the build so you notice.

## 3. Make your sprite (once, locally)

```bash
pip install pillow
python3 scripts/gen-sprite.py           # downloads your avatar, writes scripts/sprite_data.py
```

`hero.portrait = "github"` uses your avatar; set a path for a different
picture (square, 400 px or larger). The round token is found automatically
for a transparent cut-out, a drawn ring on a flat background, or a plain
square photo; if it lands wrong, set `hero.portrait_crop = [cx, cy, r]` in
source pixels. Commit `scripts/sprite_data.py`.

The sprite is made of the page palette plus colours sampled from your
portrait, so if you change `[palette]` later, run `gen-sprite.py` again.

## 4. Build

```bash
python3 scripts/gen-profile.py           # fetches with `gh` or GITHUB_TOKEN, writes assets/ and README.md
```

Push, and the two workflows take over: `refresh profile cards` rebuilds the
cards daily and on every push that touches `profile.toml` or `scripts/`;
`generate snake` redraws the snake every 12 hours in your palette. Run
either by hand from the Actions tab the first time.

The default `GITHUB_TOKEN` sees public data only. To count private
contributions, create a fine-grained personal access token with read access
to your repositories and profile, add it as the repository secret
`PROFILE_TOKEN`, and the workflow will prefer it.

## Local preview

```bash
python3 scripts/gen-profile.py --offline   # renders from .cache/github.json, no network
```

Open `assets/*.svg` in a browser, or build a page that mimics the 846 px
README column. The layout ledger fails the build on any overlap or on text
spilling out of its window, so a broken layout cannot reach GitHub.

## Licences

The generator, cards and sprite pipeline are MIT (see `LICENSE`). The pixel
font is [Fusion Pixel Font](https://github.com/TakWolf/fusion-pixel-font) by
TakWolf under the SIL Open Font License 1.1 (`scripts/fonts/OFL-fusion-pixel.txt`);
its compiled bitmaps in `scripts/font_10.py` stay under that licence.

---

## 中文说明

这是一个像素 RPG 风格的 GitHub 个人主页：像素头像站在粉彩天空下，对话框逐字打出你的台词，下面是置顶项目、贡献日历、贡献贪吃蛇和签名卡。所有数字都来自 GitHub API，由 Actions 每天重绘，构建不安装任何依赖。

1. **Fork 并改名**：仓库名改成你的登录名，Settings → Actions → General 里把 Workflow permissions 设为 Read and write。
2. **改 `profile.toml`**：必改 `github.login`、`hero.title`、`dialog`、`signature.contacts`；配色、卡片顺序、签名文案都可选。字体覆盖拉丁、希腊、西里尔、假名和 GB2312 汉字，emoji 没有字形。
3. **生成像素头像**（本地一次）：`pip install pillow` 后运行 `python3 scripts/gen-sprite.py`，会下载你的头像并写入 `scripts/sprite_data.py`，提交它。圆形裁切自动识别；不准就在 `hero.portrait_crop` 里手动给圆心和半径。改过配色后重新生成一次。
4. **构建**：`python3 scripts/gen-profile.py`，推送后两个 workflow 接管。默认 token 只看得到公开数据；想统计私有贡献，添加名为 `PROFILE_TOKEN` 的 fine-grained PAT。

生成器为 MIT 许可；像素字体 Fusion Pixel Font 为 OFL 1.1。
