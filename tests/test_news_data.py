import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from news_data import (
    classify_article,
    fetch_feed,
    get_relative_time,
    parse_published_date,
)


class NewsDataTests(unittest.TestCase):
    def test_parse_published_date_normalizes_naive_date_to_utc(self):
        parsed = parse_published_date("2026-11-05 10:00:00")
        self.assertEqual(parsed, datetime(2026, 11, 5, 10, tzinfo=timezone.utc))

    def test_parse_published_date_returns_none_for_invalid_value(self):
        self.assertIsNone(parse_published_date("not a date"))

    def test_relative_time_handles_future_dates(self):
        now = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)
        self.assertEqual(
            get_relative_time("2026-11-05 13:00:00 +0000", now=now),
            "In the future",
        )

    def test_relative_time_uses_consistent_utc_values(self):
        now = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)
        self.assertEqual(
            get_relative_time("2026-11-05 11:30:00 +0000", now=now),
            "30 mins ago",
        )

    def test_crypto_classification(self):
        self.assertEqual(
            classify_article("Bitcoin rises", "ETF demand increases", True),
            "Bitcoin & Major Coins",
        )

    def test_atom_feed_extracts_alternate_link_and_summary(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.content = b"""
            <feed xmlns="http://www.w3.org/2005/Atom">
              <entry>
                <title>Markets advance</title>
                <link rel="self" href="https://example.com/feed"/>
                <link rel="alternate" href="https://example.com/story"/>
                <summary>Investors respond to earnings.</summary>
                <updated>2026-11-05T10:00:00Z</updated>
              </entry>
            </feed>
        """
        response.iter_content.return_value = [response.content]

        with patch("news_data.requests.get", return_value=response):
            articles, error = fetch_feed("https://example.com/feed", "Example", False)

        self.assertEqual(error, "")
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["link"], "https://example.com/story")
        self.assertEqual(articles[0]["summary"], "Investors respond to earnings.")
        self.assertEqual(articles[0]["pubDate"], "2026-11-05T10:00:00Z")

    @patch("news_data.requests.get")
    def test_fetch_feed_extracts_article_and_cleans_description(self, mock_get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.content = b"""
            <rss><channel><item>
              <title>Bitcoin gains</title>
              <description><![CDATA[<p>Prices <b>rise</b> today.</p>]]></description>
              <link>https://example.com/bitcoin</link>
              <pubDate>Thu, 05 Nov 2026 10:00:00 GMT</pubDate>
            </item></channel></rss>
        """
        response.iter_content.return_value = [response.content]
        mock_get.return_value = response

        articles, error = fetch_feed("https://example.com/rss", "Example", True)

        self.assertEqual(error, "")
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["title"], "Bitcoin gains")
        self.assertEqual(articles[0]["summary"], "Prices rise today.")
        self.assertEqual(articles[0]["link"], "https://example.com/bitcoin")
        self.assertEqual(articles[0]["category"], "Bitcoin & Major Coins")

    @patch("news_data.requests.get")
    def test_fetch_feed_rejects_non_http_article_links(self, mock_get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.content = b"""
            <rss><channel><item>
              <title>Market update</title>
              <link>javascript:alert(1)</link>
            </item></channel></rss>
        """
        response.iter_content.return_value = [response.content]
        mock_get.return_value = response

        articles, error = fetch_feed("https://example.com/rss", "Example", False)

        self.assertEqual(error, "")
        self.assertEqual(articles[0]["link"], "")

    @patch("news_data.requests.get")
    def test_fetch_feed_reports_invalid_xml(self, mock_get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.content = b"<rss><channel>"
        response.iter_content.return_value = [response.content]
        mock_get.return_value = response

        articles, error = fetch_feed("https://example.com/rss", "Example", False)

        self.assertEqual(articles, [])
        self.assertIn("Example returned invalid RSS data", error)

    @patch("news_data.requests.get")
    def test_fetch_feed_enforces_size_limit(self, mock_get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.iter_content.return_value = [b"x" * (5 * 1024 * 1024 + 1)]
        mock_get.return_value = response

        articles, error = fetch_feed("https://example.com/rss", "Example", False)

        self.assertEqual(articles, [])
        self.assertIn("exceeded the 5 MB size limit", error)
        response.close.assert_called_once()

    @patch("news_data.requests.get")
    def test_fetch_feed_reports_network_errors(self, mock_get):
        import requests

        mock_get.side_effect = requests.Timeout("timed out")
        articles, error = fetch_feed("https://example.com/rss", "Example", False)

        self.assertEqual(articles, [])
        self.assertIn("Example could not be loaded", error)


if __name__ == "__main__":
    unittest.main()
