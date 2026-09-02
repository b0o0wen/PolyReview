#!/usr/bin/env python3
"""从 GitHub API 拉取 star 历史，渲染为 SVG 折线图。

用法: python star_chart.py --repo owner/repo --token ghp_xxx --output star.svg
"""
import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

def fetch_stargazers(repo: str, token: str) -> list[dict]:
    """分页拉取 stargazers（带 starred_at 时间戳）。"""
    url = f"https://api.github.com/repos/{repo}/stargazers?per_page=100"
    headers = {
        "Accept": "application/vnd.github.star+json",  # 带 starred_at
        "Authorization": f"Bearer {token}",
        "User-Agent": "polyreview-star-chart",
    }
    stars = []
    page = 1
    while True:
        req = urllib.request.Request(f"{url}&page={page}", headers=headers)
        with urllib.request.urlopen(req) as resp:
            batch = json.loads(resp.read())
            if not batch:
                break
            stars.extend(batch)
            if len(batch) < 100:
                break
            page += 1
    return stars


def render_svg(stars: list[dict], repo: str, width=800, height=300) -> str:
    """极简 SVG 折线图。"""
    if not stars:
        return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"><text x="20" y="50" fill="#58a6ff" font-size="16" font-family="monospace">{repo}: no stars yet</text></svg>'

    dates = sorted(
        datetime.fromisoformat(s["starred_at"].replace("Z", "+00:00")) for s in stars
    )
    t0, t1 = dates[0], max(dates[-1], datetime.now(timezone.utc))
    span = max((t1 - t0).total_seconds(), 1)

    pad_l, pad_r, pad_t, pad_b = 50, 20, 30, 40
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    # 累计曲线
    points = []
    for i, d in enumerate(dates):
        x = pad_l + (d - t0).total_seconds() / span * plot_w
        y = pad_t + plot_h - (i + 1) / len(dates) * plot_h
        points.append(f"{x:.1f},{y:.1f}")

    polyline = " ".join(points)
    area = f"{pad_l},{pad_t + plot_h} {polyline} {pad_l + plot_w},{pad_t + plot_h}"

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#0d1117"/>
  <text x="{pad_l}" y="20" fill="#58a6ff" font-size="14" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif">⭐ {repo} — {len(stars)} stars</text>
  <polygon points="{area}" fill="#1f6feb33"/>
  <polyline points="{polyline}" fill="none" stroke="#58a6ff" stroke-width="2" stroke-linejoin="round"/>
  <text x="{pad_l}" y="{height - 10}" fill="#8b949e" font-size="11" font-family="monospace">{dates[0].strftime('%Y-%m-%d')}</text>
  <text x="{width - pad_r - 60}" y="{height - 10}" fill="#8b949e" font-size="11" font-family="monospace">{t1.strftime('%Y-%m-%d')}</text>
</svg>'''


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True, help="owner/repo")
    p.add_argument("--token", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()

    try:
        stars = fetch_stargazers(args.repo, args.token)
    except Exception as exc:
        print(f"fetch failed ({exc}), rendering placeholder")
        stars = []
    svg = render_svg(stars, args.repo)
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w") as f:
        f.write(svg)
    print(f"✓ {len(stars)} stars → {args.output}")


if __name__ == "__main__":
    main()
