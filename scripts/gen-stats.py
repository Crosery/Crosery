#!/usr/bin/env python3
"""Self-hosted GitHub stats SVG generator.

Pulls live data from GitHub GraphQL and renders three SVG cards
matching the Crosery Dispatch night-edition visual system:
  - assets/stats.svg       overall numbers
  - assets/top-langs.svg   top 6 languages
  - assets/runai-pin.svg   featured repo card

Run from repo root:
    GITHUB_TOKEN=<token> python3 scripts/gen-stats.py

In GitHub Actions, set token via env (the default GITHUB_TOKEN works).
"""

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

USER = "Crosery"
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"


def gql(query: str) -> dict:
    if not TOKEN:
        out = subprocess.check_output(
            ["gh", "api", "graphql", "-f", f"query={query}"], text=True
        )
        return json.loads(out)
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def fetch_user_stats() -> dict:
    q = """query{
      user(login:"%s"){
        contributionsCollection{
          totalCommitContributions
          totalIssueContributions
          totalPullRequestContributions
          totalPullRequestReviewContributions
        }
        followers{totalCount}
        following{totalCount}
        repositories(first:100,ownerAffiliations:OWNER,isFork:false){
          totalCount
          nodes{
            name
            description
            stargazerCount
            forkCount
            primaryLanguage{name color}
            languages(first:10,orderBy:{field:SIZE,direction:DESC}){
              edges{size node{name color}}
            }
          }
        }
        pullRequests{totalCount}
        issues{totalCount}
      }
    }""" % USER
    return gql(q)["data"]["user"]


def aggregate_langs(repos: list) -> list:
    totals: dict[str, list] = {}
    for r in repos:
        for e in r["languages"]["edges"]:
            name = e["node"]["name"]
            color = e["node"]["color"] or "#7d8590"
            entry = totals.setdefault(name, [0, color])
            entry[0] += e["size"]
    items = sorted(totals.items(), key=lambda x: -x[1][0])
    total = sum(v[0] for _, v in items) or 1
    out = []
    for name, (size, color) in items:
        out.append({"name": name, "size": size, "color": color, "pct": size / total * 100})
    return out


def write_stats_svg(u: dict) -> None:
    repos = u["repositories"]["nodes"]
    stars = sum(r["stargazerCount"] for r in repos)
    forks = sum(r["forkCount"] for r in repos)
    cc = u["contributionsCollection"]
    commits = cc["totalCommitContributions"]
    prs = u["pullRequests"]["totalCount"]
    followers = u["followers"]["totalCount"]
    repos_n = u["repositories"]["totalCount"]
    issues = u["issues"]["totalCount"]

    rows = [
        ("STARS EARNED",       f"{stars}",     "#ff7b72"),
        ("PUBLIC REPOS",       f"{repos_n}",   "#58a6ff"),
        ("COMMITS · LAST YR",  f"{commits}",   "#7ee787"),
        ("PULL REQUESTS",      f"{prs}",       "#d2a8ff"),
        ("FOLLOWERS",          f"{followers}", "#ffd33d"),
        ("ISSUES OPENED",      f"{issues}",    "#f0883e"),
    ]

    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 380" role="img" aria-label="Stats">']
    parts.append('''  <defs><style>
    .title { font-family: 'Helvetica Neue', 'Arial Black', Impact, sans-serif; font-weight: 900; letter-spacing: -0.04em; }
    .h     { font-family: 'Helvetica Neue', Arial, sans-serif; font-weight: 700; letter-spacing: 0.20em; }
    .meta  { font-family: 'Courier New', 'JetBrains Mono', monospace; font-weight: 400; letter-spacing: 0.06em; }
  </style></defs>''')
    parts.append('  <rect width="600" height="380" fill="#0d1117"/>')
    parts.append('  <line x1="30" y1="30" x2="570" y2="30" stroke="#30363d" stroke-width="0.6"/>')
    parts.append('  <text x="30" y="22" class="meta" font-size="10" fill="#7d8590">// STATS · @' + USER + '</text>')
    parts.append('  <text x="570" y="22" text-anchor="end" class="meta" font-size="10" fill="#7d8590">LIVE · auto-refreshed</text>')
    parts.append('  <text x="30" y="74" class="title" font-size="38" fill="#f0f6fc">NUMBERS<tspan fill="#ff7b72">.</tspan></text>')
    parts.append('  <text x="30" y="94" class="meta" font-size="10" fill="#7d8590">pulled fresh from github graphql api</text>')

    for i, (label, value, color) in enumerate(rows):
        col = i % 3
        row = i // 3
        x = 30 + col * 190
        y = 140 + row * 110
        parts.append(f'  <g transform="translate({x},{y})">')
        parts.append(f'    <text class="meta" font-size="9" fill="#7d8590">{label}</text>')
        parts.append(f'    <text class="title" font-size="48" fill="#f0f6fc" y="48">{value}</text>')
        parts.append(f'    <line x1="0" y1="58" x2="80" y2="58" stroke="{color}" stroke-width="1.5"/>')
        # animate counter bar
        parts.append(f'    <rect x="0" y="68" width="0" height="2" fill="{color}">')
        parts.append(f'      <animate attributeName="width" from="0" to="160" dur="1.4s" begin="{0.1*i:.2f}s" fill="freeze" calcMode="spline" keyTimes="0;1" keySplines="0.22 1 0.36 1"/>')
        parts.append(f'    </rect>')
        parts.append('  </g>')

    # bottom scan line
    parts.append('  <g transform="translate(30,360)">')
    parts.append('    <line x1="0" y1="0" x2="540" y2="0" stroke="#30363d" stroke-width="0.5"/>')
    parts.append('    <rect x="0" y="-1" width="0" height="2" fill="#58a6ff">')
    parts.append('      <animate attributeName="x" values="0;540" dur="3.6s" repeatCount="indefinite"/>')
    parts.append('      <animate attributeName="width" values="40;0" dur="3.6s" repeatCount="indefinite"/>')
    parts.append('    </rect>')
    parts.append('  </g>')
    parts.append('</svg>')

    (ASSETS / "stats.svg").write_text("\n".join(parts), encoding="utf-8")


def write_top_langs_svg(langs: list) -> None:
    top = langs[:6]
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 380" role="img" aria-label="Top Languages">']
    parts.append('''  <defs><style>
    .title { font-family: 'Helvetica Neue', 'Arial Black', Impact, sans-serif; font-weight: 900; letter-spacing: -0.04em; }
    .name  { font-family: 'Helvetica Neue', Arial, sans-serif; font-weight: 700; letter-spacing: -0.01em; }
    .pct   { font-family: 'Helvetica Neue', 'Arial Black', sans-serif; font-weight: 900; letter-spacing: -0.02em; }
    .meta  { font-family: 'Courier New', 'JetBrains Mono', monospace; font-weight: 400; letter-spacing: 0.06em; }
  </style></defs>''')
    parts.append('  <rect width="600" height="380" fill="#0d1117"/>')
    parts.append('  <line x1="30" y1="30" x2="570" y2="30" stroke="#30363d" stroke-width="0.6"/>')
    parts.append('  <text x="30" y="22" class="meta" font-size="10" fill="#7d8590">// LANGUAGES · by repo file size</text>')
    parts.append('  <text x="570" y="22" text-anchor="end" class="meta" font-size="10" fill="#7d8590">SOURCE: github graphql</text>')
    parts.append('  <text x="30" y="74" class="title" font-size="38" fill="#f0f6fc">STACK · BYTES<tspan fill="#ff7b72">.</tspan></text>')
    parts.append('  <text x="30" y="94" class="meta" font-size="10" fill="#7d8590">includes html/css/assets — daily-driver lang is rust + py</text>')

    for i, lang in enumerate(top):
        y = 130 + i * 38
        pct = lang["pct"]
        bar_w = max(8, int(pct * 4))  # scale
        color = lang["color"]
        parts.append(f'  <g transform="translate(30,{y})">')
        parts.append(f'    <text class="name" font-size="14" fill="#f0f6fc">{lang["name"]}</text>')
        parts.append(f'    <text class="pct" font-size="14" fill="#7d8590" text-anchor="end" x="540">{pct:.1f}%</text>')
        parts.append(f'    <line x1="0" y1="12" x2="540" y2="12" stroke="#21262d" stroke-width="2"/>')
        parts.append(f'    <line x1="0" y1="12" x2="0" y2="12" stroke="{color}" stroke-width="3">')
        parts.append(f'      <animate attributeName="x2" from="0" to="{bar_w}" dur="1.6s" begin="{0.15*i:.2f}s" fill="freeze" calcMode="spline" keyTimes="0;1" keySplines="0.22 1 0.36 1"/>')
        parts.append(f'    </line>')
        parts.append('  </g>')

    # bottom moving dot
    parts.append('  <g transform="translate(30,360)">')
    parts.append('    <line x1="0" y1="0" x2="540" y2="0" stroke="#30363d" stroke-width="0.5"/>')
    parts.append('    <circle cx="0" cy="0" r="3" fill="#ff7b72">')
    parts.append('      <animateMotion dur="5s" repeatCount="indefinite" path="M0,0 L540,0 L540,0 L0,0"/>')
    parts.append('    </circle>')
    parts.append('  </g>')
    parts.append('</svg>')

    (ASSETS / "top-langs.svg").write_text("\n".join(parts), encoding="utf-8")


def write_repo_pin_svg(repo_name: str, repos: list) -> None:
    repo = next((r for r in repos if r["name"].lower() == repo_name.lower()), None)
    if repo is None:
        return
    desc = (repo.get("description") or "").strip()
    if len(desc) > 120:
        desc = desc[:117] + "..."
    stars = repo["stargazerCount"]
    forks = repo["forkCount"]
    lang = repo["primaryLanguage"]["name"] if repo["primaryLanguage"] else "—"
    lang_color = repo["primaryLanguage"]["color"] if repo["primaryLanguage"] else "#7d8590"

    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 380" role="img" aria-label="Pinned: ' + repo_name + '">']
    parts.append('''  <defs><style>
    .title { font-family: 'Helvetica Neue', 'Arial Black', Impact, sans-serif; font-weight: 900; letter-spacing: -0.04em; }
    .h     { font-family: 'Helvetica Neue', Arial, sans-serif; font-weight: 700; letter-spacing: 0.20em; }
    .body  { font-family: 'Helvetica Neue', Arial, sans-serif; font-weight: 400; }
    .meta  { font-family: 'Courier New', 'JetBrains Mono', monospace; font-weight: 400; letter-spacing: 0.06em; }
    .num   { font-family: 'Helvetica Neue', 'Arial Black', sans-serif; font-weight: 900; }
  </style></defs>''')
    parts.append('  <rect width="600" height="380" fill="#0d1117"/>')
    parts.append('  <line x1="30" y1="30" x2="570" y2="30" stroke="#30363d" stroke-width="0.6"/>')
    parts.append('  <text x="30" y="22" class="meta" font-size="10" fill="#7d8590">// PINNED · featured repo</text>')
    parts.append('  <text x="570" y="22" text-anchor="end" class="meta" font-size="10" fill="#7d8590">github.com/' + USER + '/' + repo_name + '</text>')
    parts.append(f'  <text x="30" y="86" class="title" font-size="48" fill="#f0f6fc">{repo_name.upper()}<tspan fill="#ff7b72">.</tspan></text>')

    # description wrap (1-2 lines)
    if desc:
        line1 = desc[:60] if len(desc) > 60 else desc
        line2 = desc[60:120] if len(desc) > 60 else ""
        parts.append(f'  <text x="30" y="120" class="body" font-size="13" fill="#c9d1d9">{line1}</text>')
        if line2:
            parts.append(f'  <text x="30" y="140" class="body" font-size="13" fill="#c9d1d9">{line2}</text>')

    # stats row
    parts.append('  <g transform="translate(30,200)">')
    parts.append('    <g>')
    parts.append('      <text class="meta" font-size="9" fill="#7d8590">STARS</text>')
    parts.append(f'      <text class="num" font-size="44" fill="#f0f6fc" y="44">{stars}</text>')
    parts.append('      <line x1="0" y1="54" x2="60" y2="54" stroke="#ffd33d" stroke-width="1.5"/>')
    parts.append('    </g>')
    parts.append('    <g transform="translate(160,0)">')
    parts.append('      <text class="meta" font-size="9" fill="#7d8590">FORKS</text>')
    parts.append(f'      <text class="num" font-size="44" fill="#f0f6fc" y="44">{forks}</text>')
    parts.append('      <line x1="0" y1="54" x2="60" y2="54" stroke="#58a6ff" stroke-width="1.5"/>')
    parts.append('    </g>')
    parts.append('    <g transform="translate(320,0)">')
    parts.append('      <text class="meta" font-size="9" fill="#7d8590">LANG</text>')
    parts.append(f'      <text class="num" font-size="44" fill="#f0f6fc" y="44">{lang.upper()[:5]}</text>')
    parts.append(f'      <line x1="0" y1="54" x2="60" y2="54" stroke="{lang_color}" stroke-width="1.5"/>')
    parts.append('    </g>')
    parts.append('  </g>')

    # bottom tagline
    parts.append('  <text x="30" y="316" class="h" font-size="11" fill="#7d8590">FLAGSHIP &#183; OPEN SOURCE &#183; INSTALL VIA CARGO</text>')
    parts.append('  <text x="30" y="338" class="meta" font-size="11" fill="#7ee787">$ cargo install runai-cli</text>')

    parts.append('  <g transform="translate(30,360)">')
    parts.append('    <line x1="0" y1="0" x2="540" y2="0" stroke="#30363d" stroke-width="0.5"/>')
    parts.append('    <rect x="0" y="-1" width="0" height="2" fill="#ff7b72">')
    parts.append('      <animate attributeName="x" values="0;540" dur="3.6s" repeatCount="indefinite"/>')
    parts.append('      <animate attributeName="width" values="40;0" dur="3.6s" repeatCount="indefinite"/>')
    parts.append('    </rect>')
    parts.append('  </g>')
    parts.append('</svg>')

    (ASSETS / "runai-pin.svg").write_text("\n".join(parts), encoding="utf-8")


def main() -> int:
    u = fetch_user_stats()
    langs = aggregate_langs(u["repositories"]["nodes"])
    write_stats_svg(u)
    write_top_langs_svg(langs)
    write_repo_pin_svg("runai", u["repositories"]["nodes"])
    print("wrote assets/stats.svg, assets/top-langs.svg, assets/runai-pin.svg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
