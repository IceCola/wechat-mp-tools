"""Preserve article metadata and rendered comments without localizing resources.

An HTTP response may contain only comment placeholders. Absence is recorded as
unavailable, never interpreted as proof that the article has no comments.
"""
from datetime import datetime, timezone, timedelta
from html import escape

from bs4 import BeautifulSoup


def extract_rendered_comments(page_html: str) -> str:
    soup = BeautifulSoup(page_html, "html.parser")
    for selector in ("#js_cmt_list", "#js_cmt_area", ".comment"):
        for region in soup.select(selector):
            entries = region.select(".comment-item, .comment_item, .js_comment_item, .js_comment_content")
            if not any(item.get_text(strip=True) for item in entries):
                continue
            for unwanted in region.select("script, style, button, textarea"):
                unwanted.decompose()
            return '<section class="archived-comments"><h2>精选留言</h2>' + str(region) + '</section>'
    # Some rendered pages expose items without a containing comment area.
    entries = soup.select(".comment-item, .comment_item, .js_comment_item")
    if entries:
        return '<section class="archived-comments"><h2>精选留言</h2>' + ''.join(map(str, entries)) + '</section>'
    return ""


def original_metadata(page_html: str) -> dict:
    soup = BeautifulSoup(page_html, "html.parser")
    author = soup.select_one('meta[name="author"], meta[property="og:article:author"]')
    author_text = author.get("content", "") if author else ""
    if not author_text:
        node = soup.select_one("#meta_content .rich_media_meta_text")
        author_text = node.get_text(" ", strip=True) if node else ""
    source = soup.select_one("#js_name, .profile_nickname")
    original = soup.select_one("#copyright_logo, .copyright_logo")
    return {
        "author": author_text,
        "source": source.get_text(" ", strip=True) if source else "",
        "is_original": bool(original and "原创" in original.get_text()),
    }


def metadata_header(meta: dict) -> str:
    parts = ['<header class="article-meta"><h1>' + escape(meta.get("title", "")) + '</h1><p>']
    parts.append('原创 ' if meta.get("is_original") else '')
    parts.append(escape(meta.get("author", "")) + ' ' + escape(meta.get("source", "")))
    parts.append('</p>')
    if meta.get("publish_time"):
        published = datetime.fromtimestamp(meta["publish_time"], timezone(timedelta(hours=8)))
        parts.append('<p><em>' + published.strftime('%Y年%m月%d日 %H:%M') + '</em></p>')
    parts.append('</header>')
    return ''.join(parts)


def complete_raw_html(page_html: str, meta: dict, comments_html: str = "") -> str:
    """Keep the fetched page, including its head and scripts, and add only missing metadata/comments."""
    soup = BeautifulSoup(page_html, "html.parser")
    if not soup.body:
        soup = BeautifulSoup('<!doctype html><html><head><meta charset="utf-8"></head><body>'
                             + page_html + '</body></html>', "html.parser")
    if not soup.select_one("#meta_content, .article-meta"):
        soup.body.insert(0, BeautifulSoup(metadata_header(meta), "html.parser"))
    if comments_html and not extract_rendered_comments(str(soup)):
        soup.body.append(BeautifulSoup(comments_html, "html.parser"))
    return str(soup)
