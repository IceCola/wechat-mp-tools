"""Download/export regressions with isolated files and no external requests."""
import ast
import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import Flask, jsonify
from backend import config, downloader, articles, rss_feed, content_filter

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jS1kAAAAASUVORK5CYII=')
URL = 'https://mp.weixin.qq.com/s/example'
IMAGE = 'https://mmbiz.qpic.cn/image.png'
PAGE = ('<html><head><meta property="og:title" content="测试标题"></head><body>'
        '<script>var ct = "1792686600";</script>'  # 2026-10-22 16:30 UTC -> Oct 23 Beijing
        '<div id="js_content"><p>测试正文</p><img src="data:image/gif;base64,placeholder" srcset="https://mmbiz.qpic.cn/srcset.png 2x" data-src="' + IMAGE + '"></div></body></html>')
FORMAT_KEYS = ('save_html', 'save_markdown', 'save_pdf', 'save_text', 'save_raw_html', 'save_raw_markdown')


class DownloadOptionsTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='mp-export-test-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.settings = {**config.DEFAULT_SETTINGS, **{key: False for key in FORMAT_KEYS},
                         'save_markdown': True, 'auto_save_videos': False,
                         'fetch_comments': False,
                         'download_dir': str(self.root)}
        for target, kwargs in [
            ('backend.downloader.get_settings', {'side_effect': lambda: self.settings.copy()}),
            ('backend.downloader.fetch_wechat_article_html', {'return_value': (PAGE, URL, '')}),
            ('backend.downloader.get_proxies_dict', {'return_value': None}),
            ('backend.downloader.download_resource', {'side_effect': self.resource}),
            ('backend.content_filter.filter_article_html', {'side_effect': lambda html: html}),
        ]:
            patcher = patch(target, **kwargs)
            mock = patcher.start()
            self.addCleanup(patcher.stop)
            if target.endswith('download_resource'):
                self.resource_mock = mock
            if target.endswith('fetch_wechat_article_html'):
                self.fetch_mock = mock
        # Any accidental request outside mocked fetch boundaries must fail.
        network = patch('requests.sessions.Session.request', side_effect=AssertionError('Unexpected network'))
        network.start()
        self.addCleanup(network.stop)

    def resource(self, url, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path = path.with_suffix('.png')
        path.write_bytes(PNG)
        return path.name

    def download(self):
        result = downloader.download_single_article(URL, self.root / '账号', '测试标题')
        self.assertTrue(result['success'], result.get('error'))
        return Path(result['path'])

    def test_each_selected_format_is_the_only_export(self):
        for key, suffix in zip(FORMAT_KEYS, ('.html', '.md', '.pdf', '.txt', '_raw.html', '_raw.md')):
            with self.subTest(key=key):
                self.settings.update({k: k == key for k in FORMAT_KEYS})
                def pdf(source, target, title=''):
                    self.assertTrue(source.is_file())
                    if key == 'save_pdf':
                        self.assertIn(f'<base href="{source.parent.parent.resolve().as_uri()}/">', source.read_text())
                    target.write_bytes(b'%PDF-1.4 test')
                    return True
                with patch.object(downloader, 'export_html_to_pdf', side_effect=pdf) as export:
                    path = self.download()
                exports = [p for p in path.iterdir() if p.suffix in ('.html', '.md', '.pdf', '.txt')]
                self.assertEqual([p.name for p in exports], ['测试标题' + suffix])
                self.assertEqual(export.call_count, int(key == 'save_pdf'))
                self.assertFalse(any(p.name.startswith('.pdf-') for p in path.iterdir()))
                if key in ('save_text', 'save_raw_html', 'save_raw_markdown'):
                    self.assertFalse((path / 'media').exists())

    def test_embedded_images_have_real_mime_and_no_image_files(self):
        self.settings.update(save_html=True, image_mode='embedded')
        path = self.download()
        expected = 'data:image/png;base64,' + base64.b64encode(PNG).decode()
        for suffix in ('.html', '.md'):
            text = (path / ('测试标题' + suffix)).read_text()
            self.assertIn(expected, text)
            self.assertNotIn(IMAGE, text)
        self.assertFalse((path / 'media').exists())

    def test_local_images_reference_existing_files(self):
        self.settings.update(save_html=True, image_mode='local')
        path = self.download()
        for suffix in ('.html', '.md'):
            self.assertIn('media/img_001.png', (path / ('测试标题' + suffix)).read_text())
        self.assertEqual((path / 'media/img_001.png').read_bytes(), PNG)

    def test_disabling_images_preserves_remote_links(self):
        self.settings.update(image_mode='embedded', auto_save_images=False)
        path = self.download()
        self.resource_mock.assert_not_called()
        self.assertIn(IMAGE, (path / '测试标题.md').read_text())

    def test_date_uses_publication_day_in_beijing_without_changing_title(self):
        self.settings.update(filename_date=True)
        path = self.download()
        self.assertEqual(path.name, '2026-10-23_测试标题')
        self.assertTrue((path / '2026-10-23_测试标题.md').is_file())
        self.assertEqual(json.loads((path / 'metadata.json').read_text())['title'], '测试标题')

    def test_unknown_date_does_not_use_download_date(self):
        self.settings.update(filename_date=True)
        self.fetch_mock.return_value = (PAGE.replace('var ct = "1792686600";', ''), URL, '')
        path = self.download()
        self.assertEqual(path.name, '测试标题')
        self.assertEqual(json.loads((path / 'metadata.json').read_text())['publish_time'], 0)

    def test_markdown_only_repeated_downloads_never_overwrite(self):
        first = self.download()
        content = (first / '测试标题.md').read_bytes()
        second = self.download()
        self.assertNotEqual(first, second)
        self.assertEqual((first / '测试标题.md').read_bytes(), content)
        self.fetch_mock.return_value = ('', URL, 'network failed')
        result = downloader.download_single_article(URL, first.parent, '测试标题')
        self.assertFalse(result['success'])
        self.assertEqual((first / '测试标题.md').read_bytes(), content)

    def test_pdf_failure_is_reported_and_temp_input_is_removed(self):
        self.settings.update(save_markdown=False, save_pdf=True)
        with patch.object(downloader, 'export_html_to_pdf', return_value=False):
            result = downloader.download_single_article(URL, self.root / '账号')
        self.assertFalse(result['success'])
        self.assertIn('PDF', result['error'])
        self.assertFalse(list(Path(result['path']).rglob('*.html')))

    def test_validation_before_network_and_settings_persistence(self):
        bad_options = [dict.fromkeys(FORMAT_KEYS, False), {'image_mode': 'invalid'}, {'save_html': 'false'}]
        for bad in bad_options:
            with self.subTest(bad=bad):
                self.settings.update(bad)
                with self.assertRaises(ValueError):
                    downloader.download_single_article(URL, self.root)
                self.settings = {**config.DEFAULT_SETTINGS, 'save_pdf': False, 'fetch_comments': False}
        self.fetch_mock.assert_not_called()
        with patch.object(config, 'APP_SETTINGS_FILE', self.root / 'settings.json'):
            config.save_settings(self.settings)
            self.assertEqual(config.get_settings()['save_pdf'], False)

    def test_history_and_rss_without_html(self):
        path = self.download()
        app = Flask(__name__)
        app.register_blueprint(articles.articles_bp)
        with patch.object(articles, 'get_settings', return_value=self.settings), \
             patch.object(articles, 'OUTPUT_DIR', self.root), \
             patch.object(articles, 'DATA_DIR', self.root):
            response = app.test_client().get('/api/articles/serve-file', query_string={'path': str(path)})
            self.assertEqual(response.status_code, 200)
            self.assertIn('测试正文', response.get_data(as_text=True))
            response.close()
            history = []
            self.assertTrue(articles._sync_history_from_disk(history))
            self.assertEqual(history[0]['path'], str(path))
        body = rss_feed._read_content({'path': str(path)}, 'http://localhost/')
        self.assertIn('测试正文', body)

    def test_refilter_preserves_text_export_selection(self):
        for save_text in (False, True):
            with self.subTest(save_text=save_text):
                self.settings.update(save_html=True, save_text=save_text)
                path = self.download()
                if save_text:
                    (path / '测试标题.txt').write_text('stale')
                content_filter.refilter_existing(path.parent.parent, dry_run=False, force=True)
                self.assertFalse((path / 'content.txt').exists())
                self.assertEqual((path / '测试标题.txt').exists(), save_text)
                if save_text:
                    self.assertIn('测试正文', (path / '测试标题.txt').read_text())

    def test_settings_endpoints_return_400_for_invalid_exports(self):
        # Load just each endpoint function: no scheduler or authentication startup.
        for filename, name in [('app.py', 'save_settings'), ('app_mp.py', 'update_settings')]:
            with self.subTest(filename=filename):
                source = ast.parse((Path(__file__).resolve().parents[1] / filename).read_text())
                fn = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == name)
                fn.decorator_list = []
                env = {'jsonify': jsonify, 'get_settings': config.get_settings, 'save_settings': config.save_settings}
                exec(compile(ast.Module(body=[fn], type_ignores=[]), filename, 'exec'), env)
                app = Flask(filename)
                app.add_url_rule('/api/settings', view_func=env[name], methods=['POST'])
                with patch.object(config, 'APP_SETTINGS_FILE', self.root / (filename + '.json')):
                    client = app.test_client()
                    bad = client.post('/api/settings', json=dict.fromkeys(FORMAT_KEYS, False))
                    self.assertEqual(bad.status_code, 400)
                    self.assertEqual(client.post('/api/settings', json={'save_pdf': False}).status_code, 200)


if __name__ == '__main__':
    unittest.main()
