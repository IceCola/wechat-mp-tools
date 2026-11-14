"""Exercise real response classification and recovery without network or credentials."""
import json
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

from backend import articles, waterwall


def response(status, data):
    return Mock(status_code=status, text=json.dumps(data), headers={}, json=lambda: data)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(waterwall.WATERWALL, waterwall.WATERWALL.copy()))
        self.stack.enter_context(patch.object(waterwall, 'record_failure'))
        waterwall.waterwall_reset()
        self.session = Mock()
        self.stack.enter_context(patch.object(articles, 'get_weread_session', return_value=self.session))
        self.stack.enter_context(patch.object(articles, 'borrow_weread_session', return_value=('acc', '', '', {})))
        self.stack.enter_context(patch.object(articles, 'biz_to_book_id', return_value='book'))
        self.stack.enter_context(patch.object(articles.account_pool, 'report'))
        self.stack.enter_context(patch.object(articles.time, 'sleep'))
        self.stack.enter_context(patch.object(articles, 'sleep_backoff'))
        self.activate = self.stack.enter_context(patch('backend.weread_signer.activate_terminal_session', return_value=True))

    def fetch(self):
        return articles._fetch_articles_page('account', 0, 10)

    def success(self):
        return response(200, {'chapters': [{'title': 'ok', 'reviewId': 'MP_WXS_1_test',
            'createTime': 100, 'mpInfo': {'doc_url': 'https://mp.weixin.qq.com/s/test'}}], 'hasMore': False})

    def test_session_error_reaches_activation_then_recovers(self):
        self.session.get.side_effect = [response(499, {'errcode': -2041}), self.success()]
        result = self.fetch()
        self.assertEqual(len(result[0]), 1)
        self.activate.assert_called_once()
        self.assertFalse(waterwall.WATERWALL['active'])

    def test_persistent_rate_limit_does_not_require_captcha(self):
        self.session.get.return_value = response(499, {'errcode': -2014})
        with self.assertRaisesRegex(RuntimeError, '-2014'):
            self.fetch()
        self.assertFalse(waterwall.WATERWALL['active'])
        self.assertEqual(self.session.get.call_count, 4)

    def test_persistent_session_failure_is_reported_as_session_failure(self):
        self.session.get.return_value = response(499, {'errcode': -2041})
        with self.assertRaisesRegex(RuntimeError, '-2041'):
            self.fetch()
        self.assertFalse(waterwall.WATERWALL['active'])

    def test_old_global_flag_does_not_override_success(self):
        waterwall.waterwall_hit('https://example.test', 499, '-2014')
        self.session.get.return_value = self.success()
        self.assertEqual(len(self.fetch()[0]), 1)

    def test_explicit_captcha_still_blocks(self):
        self.session.get.return_value = response(403, {'errmsg': 'tcaptcha'})
        with self.assertRaises(PermissionError):
            self.fetch()
        self.assertTrue(waterwall.WATERWALL['active'])
        self.assertEqual(self.session.get.call_count, 1)

    def test_captcha_on_retry_still_blocks(self):
        self.session.get.side_effect = [response(499, {'errcode': -2014}), response(403, {'errmsg': 'tcaptcha'})]
        with self.assertRaises(PermissionError):
            self.fetch()
        self.assertTrue(waterwall.WATERWALL['active'])

    def test_rate_limit_remains_visible_when_pool_is_cooling(self):
        self.session.get.return_value = response(499, {'errcode': -2014})
        with patch.object(articles, 'borrow_weread_session', side_effect=[('acc', '', '', {}), RuntimeError('cooldown')]):
            with self.assertRaisesRegex(RuntimeError, '-2014'):
                self.fetch()
        self.assertFalse(waterwall.WATERWALL['active'])
