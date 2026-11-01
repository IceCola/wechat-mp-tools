"""Range pagination regressions; no real accounts, storage or network."""
import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import articles


def item(timestamp, title='match'):
    return {'update_time': timestamp, 'title': title, 'link': 'https://mp.weixin.qq.com/s/test'}


class RangeTests(unittest.TestCase):
    def run_range(self, pages, keyword='', existing=False):
        with ExitStack() as stack:
            stack.enter_context(patch.object(articles, '_download_tasks', {'test': {
                'status': 'running', 'scanned': 0, 'total': 0, 'completed': 0,
                'failed': 0, 'results': [], 'stop_reason': ''}}))
            stack.enter_context(patch.object(articles, 'get_settings', return_value={'request_delay': 2}))
            stack.enter_context(patch.object(articles, 'load_json', return_value=[]))
            stack.enter_context(patch.object(articles, 'save_json'))
            stack.enter_context(patch('backend.db.is_article_downloaded', return_value=(existing, '/fake')))
            fetch = stack.enter_context(patch.object(articles, '_fetch_articles_page', side_effect=pages))
            download = stack.enter_context(patch.object(articles, '_download_article_into_task'))
            wait = stack.enter_context(patch.object(articles, 'sleep_throttled'))
            articles._do_range_download('test', 'account', 'name', 100, 200, keyword, 10)
            return fetch, download, wait, dict(articles._download_tasks['test'])

    def test_boundary_page_stops_without_fetching_next_and_handles_local_disorder(self):
        fetch, download, _, task = self.run_range([([item(150), item(99), item(100), item(200), item(201)], 1000, 1)])
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual([c.args[1]['update_time'] for c in download.call_args_list], [150, 100, 200])
        self.assertEqual(task['status'], 'completed')
        self.assertIn('时间范围', task['stop_reason'])

    def test_keyword_does_not_hide_date_boundary(self):
        fetch, download, _, _ = self.run_range([([item(150, 'other'), item(99, 'other')], 1000, 1)], keyword='match')
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(fetch.call_args.args[3], '')
        download.assert_not_called()

    def test_unknown_time_does_not_count_as_old(self):
        fetch, download, wait, _ = self.run_range([([item(0)], 1000, 1), ([item(150)], 1000, 0)])
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(download.call_count, 1)
        self.assertEqual(wait.call_count, 2)

    def test_skipped_existing_page_is_throttled_before_next_page(self):
        fetch, download, wait, task = self.run_range([([item(180)], 1000, 1), ([item(90)], 1000, 1)], existing=True)
        self.assertEqual(fetch.call_count, 2)
        download.assert_not_called()
        wait.assert_called_once()
        self.assertEqual(task['completed'], 1)

    def test_no_more_flag_prevents_extra_request(self):
        fetch, _, wait, _ = self.run_range([([item(250)], 1000, 0)])
        self.assertEqual(fetch.call_count, 1)
        wait.assert_not_called()

    def test_request_failure_marks_task_failed(self):
        _, _, _, task = self.run_range([RuntimeError('HTTP 429')])
        self.assertEqual(task['status'], 'failed')
        self.assertIn('429', task['stop_reason'])

    def test_list_failure_is_http_error(self):
        app = Flask(__name__)
        app.register_blueprint(articles.articles_bp)
        with patch.object(articles, '_fetch_articles_page', side_effect=RuntimeError('HTTP 429')):
            response = app.test_client().get('/api/articles/list/account')
        self.assertEqual(response.status_code, 502)
        self.assertIn('429', response.json['error'])

    def test_fetch_does_not_fallback_after_http_error(self):
        session = Mock()
        session.get.return_value.status_code = 503
        session.get.return_value.text = 'unavailable'
        with patch.object(articles, 'biz_to_book_id', return_value='book'), \
             patch.object(articles, 'get_weread_session', return_value=session), \
             patch.object(articles, 'borrow_weread_session', return_value=('acc', '', '', {})), \
             patch('backend.waterwall.detect_waterwall', return_value=None), \
             patch('backend.waterwall.is_waterwall_active', return_value=False):
            with self.assertRaisesRegex(RuntimeError, '503'):
                articles._fetch_articles_page('account', 0, 10)
        self.assertEqual(session.get.call_count, 1)

    def test_fallback_resolves_only_requested_page(self):
        session = Mock()
        page = Mock(status_code=200, text='{}')
        page.json.return_value = {'chapters': [], 'hasMore': False}
        fallback = Mock(status_code=200, text='{}')
        fallback.json.return_value = {'reviews': [
            {'title': str(i), 'reviewId': str(i), 'createTime': 200 - i,
             'mpInfo': {'doc_url': 'https://mp.weixin.qq.com/s/test'}} for i in range(30)]}
        session.get.side_effect = [page, fallback]
        with patch.object(articles, 'biz_to_book_id', return_value='book'), \
             patch.object(articles, 'get_weread_session', return_value=session), \
             patch.object(articles, 'borrow_weread_session', return_value=('acc', '', '', {})), \
             patch.object(articles.account_pool, 'report'), \
             patch('backend.waterwall.detect_waterwall', return_value=None), \
             patch('backend.waterwall.is_waterwall_active', return_value=False), \
             patch.dict('backend.waterwall.WATERWALL', {'active': False}):
            result, _, more = articles._fetch_articles_page('account', 10, 10)
        self.assertEqual([a['title'] for a in result], [str(i) for i in range(10, 20)])
        self.assertEqual(more, 1)


if __name__ == '__main__':
    unittest.main()
