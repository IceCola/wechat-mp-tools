"""Original exports must be independent of filters, localization and comment availability."""
import json
from unittest.mock import patch
from flask import Flask

from backend import config, downloader
from backend import articles
from backend.original_article import extract_rendered_comments
from scripts.backfill_raw_markdown import backfill
import test_download_options as fixtures
from test_download_options import IMAGE, PAGE


class OriginalExportsTests(fixtures.DownloadOptionsTests):
    def test_defaults_and_settings_migration(self):
        self.assertTrue(config.DEFAULT_SETTINGS['save_raw_markdown'])
        self.assertTrue(config.DEFAULT_SETTINGS['save_raw_html'])
        settings = self.root / 'settings.json'
        settings.write_text('{"save_markdown": false}')
        with patch.object(config, 'APP_SETTINGS_FILE', settings):
            self.assertTrue(config.get_settings()['save_raw_markdown'])

    def test_remote_original_and_local_markdown_coexist(self):
        self.settings.update(save_raw_html=True, save_raw_markdown=True)
        page = PAGE.replace('<body>', '<body><div id="meta_content"><span id="copyright_logo">原创</span>'
                            '<span class="rich_media_meta_text">作者甲</span><a id="js_name">账号</a></div>')
        comments = '<div class="comment"><div class="comment-item">读者甲：留言正文<div class="reply">作者回复</div></div></div>'
        self.fetch_mock.return_value = (page.replace('</body>', comments + '</body>'), 'https://mp.weixin.qq.com/s/test', '')
        with patch('backend.content_filter.filter_article_html', return_value='<p>清理后的正文</p><img src="' + IMAGE + '">'):
            path = self.download()
        raw_md = (path / '测试标题_raw.md').read_text(encoding='utf-8')
        raw_html = (path / '测试标题_raw.html').read_text(encoding='utf-8')
        local_md = (path / '测试标题.md').read_text(encoding='utf-8')
        self.assertIn(IMAGE, raw_md)
        self.assertNotIn('media/', raw_md)
        self.assertIn('测试正文', raw_md)
        self.assertIn('原创', raw_md)
        self.assertIn('作者甲', raw_md)
        self.assertIn('精选留言', raw_md)
        self.assertIn('作者回复', raw_md)
        self.assertIn('js_name', raw_html)
        self.assertIn('留言正文', raw_html)
        self.assertIn('清理后的正文', local_md)
        self.assertIn('media/img_001.png', local_md)
        meta = json.loads((path / 'metadata.json').read_text(encoding='utf-8'))
        self.assertTrue(meta['has_raw_markdown'])
        self.assertEqual(meta['comments_status'], 'captured')

    def test_browser_comments_and_failure_are_explicit(self):
        self.settings.update(save_raw_markdown=True, fetch_comments=True)
        rendered = '<div id="js_cmt_area"><div class="comment_item">动态留言与回复</div></div>'
        with patch.object(downloader, 'fetch_via_headless_browser', return_value=(rendered, '')) as browser:
            path = self.download()
        browser.assert_called_once()
        self.assertIn('动态留言与回复', (path / '测试标题_raw.md').read_text(encoding='utf-8'))
        with patch.object(downloader, 'fetch_via_headless_browser', return_value=('', '缺少登录态')):
            path = self.download()
        meta = json.loads((path / 'metadata.json').read_text(encoding='utf-8'))
        self.assertEqual(meta['comments_status'], 'unavailable')
        self.assertIn('登录态', meta['comments_warning'])
        self.assertFalse(extract_rendered_comments('<div id="js_cmt_area">写留言</div>'))

    def test_section_paragraphs_lazy_images_and_originality_unknown(self):
        md = downloader.html_to_markdown('<section>第一段</section><section>第二段</section>'
                                        '<img src="placeholder" data-src="' + IMAGE + '">',
                                        meta={'title': '测试'})
        self.assertIn('第一段\n\n第二段', md)
        self.assertIn(IMAGE, md)
        self.assertNotIn('placeholder', md)
        self.assertNotIn('原创', md)

    def test_raw_only_history_and_opening_two_markdown_versions(self):
        self.settings.update(save_markdown=False, save_raw_markdown=True)
        super().test_history_and_rss_without_html()
        path = self.download()
        app = Flask(__name__)
        app.register_blueprint(articles.articles_bp)
        def opened_name():
            with patch.object(articles, 'desktop_available', return_value=False):
                response = app.test_client().post('/api/articles/open-file', json={'path': str(path), 'type': 'md'})
            self.assertEqual(response.status_code, 200)
            return response.json['container_path']
        self.assertTrue(opened_name().endswith('_raw.md'))
        (path / '测试标题.md').write_text('阅读版', encoding='utf-8')
        self.assertFalse(opened_name().endswith('_raw.md'))

    def test_offline_backfill_preserves_downloads_and_is_repeatable(self):
        self.settings.update(save_raw_html=True)
        path = self.download()
        original = (path / '测试标题_raw.html').read_bytes()
        local = (path / '测试标题.md').read_bytes()
        result = backfill(self.root)
        self.assertEqual(result['created'], 1)
        self.assertFalse(result['errors'])
        self.assertIn(IMAGE, (path / '测试标题_raw.md').read_text(encoding='utf-8'))
        self.assertEqual((path / '测试标题_raw.html').read_bytes(), original)
        self.assertEqual((path / '测试标题.md').read_bytes(), local)
        self.assertEqual(backfill(self.root)['existing'], 1)
