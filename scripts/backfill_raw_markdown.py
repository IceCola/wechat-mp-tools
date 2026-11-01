"""Offline export of original remote-image Markdown from saved article data.

Does not fetch pages or comments, overwrite existing raw exports, or alter HTML.
Usage: python scripts/backfill_raw_markdown.py "D:/Application/WeChat MP Tools re/data/1024"
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bs4 import BeautifulSoup
from backend.downloader import activate_lazy_images, html_to_markdown
from backend.original_article import extract_rendered_comments


def backfill(root: Path) -> dict:
    stats = {"created": 0, "existing": 0, "errors": [], "comments_unavailable": 0}
    for html_path in sorted(root.rglob("*_raw.html")):
        try:
            target = html_path.with_suffix('.md')
            if target.exists():
                stats["existing"] += 1
                continue
            meta_path = html_path.parent / 'metadata.json'
            meta = json.loads(meta_path.read_text(encoding='utf-8-sig')) if meta_path.exists() else {}
            data_path = html_path.parent / 'data.json'
            data = json.loads(data_path.read_text(encoding='utf-8-sig')) if data_path.exists() else {}
            page = html_path.read_text(encoding='utf-8-sig')
            soup = BeautifulSoup(page, 'html.parser')
            body = soup.select_one('#js_content, .rich_media_content')
            content = data.get('content') or (body.decode_contents() if body else '')
            if not content.strip():
                raise ValueError('No saved article body')
            combined = {**meta, **{key: value for key, value in data.items() if key != 'content'}}
            combined.setdefault('source', html_path.parent.parent.name)
            comments = data.get('comments_html') or extract_rendered_comments(page)
            md = html_to_markdown(activate_lazy_images(content) + comments, meta=combined) + '\n'
            # Exclusive creation protects original exports from future runs.
            with target.open('x', encoding='utf-8') as output:
                output.write(md)
            meta.update(has_raw_markdown=True, raw_markdown_file=target.name,
                        comments_status='captured' if comments else 'unavailable_in_saved_files')
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            stats['created'] += 1
            stats['comments_unavailable'] += int(not comments)
        except Exception as exc:
            stats['errors'].append({'path': str(html_path), 'error': str(exc)})
    return stats


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('download_root', type=Path)
    args = parser.parse_args()
    if not args.download_root.is_dir():
        parser.error('download_root must be an existing directory')
    result = backfill(args.download_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(bool(result['errors']))
