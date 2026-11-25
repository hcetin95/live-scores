import unittest

from live_board import highlights as h


def game(home, away, kick="2026-11-24T17:45Z"):
    return {"id": "1", "slug": "uefa.champions", "kick": kick, "label": "x",
            "home": h.aliases(home), "away": h.aliases(away)}


class HighlightMatchTest(unittest.TestCase):
    def test_matches_extended_highlights_with_special_letters(self):
        g = game({"displayName": "Bodo/Glimt", "shortDisplayName": "Bodo/Glimt", "abbreviation": "BOD"},
                 {"displayName": "LASK Linz", "shortDisplayName": "LASK", "abbreviation": "LASK"})
        vids = [{"title": "Bodø/Glimt vs. LASK: Extended Highlights | UCL League Phase MD 5 | CBS Sports Golazo",
                 "url": "https://www.youtube.com/watch?v=a", "published": "2026-11-24T21:00:00+00:00", "channel": "CBS"}]
        self.assertEqual(h.match(g, vids)["url"], "https://www.youtube.com/watch?v=a")

    def test_ignores_preview_and_older_video_and_other_teams(self):
        g = game({"displayName": "Arsenal", "abbreviation": "ARS"}, {"displayName": "Borussia Dortmund", "abbreviation": "DOR"})
        vids = [
            {"title": "Arsenal vs. Dortmund preview and highlights", "url": "u1", "published": "2026-11-24T20:00:00+00:00", "channel": "c"},
            {"title": "Arsenal vs. Dortmund: Highlights", "url": "u2", "published": "2026-11-20T20:00:00+00:00", "channel": "c"},
            {"title": "Galatasaray vs. Aston Villa: Highlights", "url": "u3", "published": "2026-11-24T22:00:00+00:00", "channel": "c"},
        ]
        self.assertIsNone(h.match(g, vids))
        vids.append({"title": "Arsenal vs. Borussia Dortmund: Highlights", "url": "u4",
                     "published": "2026-11-24T22:00:00+00:00", "channel": "c"})
        self.assertEqual(h.match(g, vids)["url"], "u4")

    def test_turkish_ozet(self):
        g = game({"displayName": "Fenerbahce", "abbreviation": "FEN"}, {"displayName": "Besiktas", "abbreviation": "BES"})
        vids = [{"title": "Fenerbahçe 2-1 Beşiktaş | Maç Özeti", "url": "u", "published": "2026-11-24T21:00:00+00:00", "channel": "c"}]
        self.assertEqual(h.match(g, vids)["url"], "u")


if __name__ == "__main__":
    unittest.main()


class UploadsTest(unittest.TestCase):
    def test_reads_playlist_pages(self):
        import json as _j
        from unittest import mock
        from live_board import highlights as h
        pages = [{"items": [{"snippet": {"title": "A v B | Highlights", "publishedAt": "2026-11-24T22:00:00Z",
                                         "channelTitle": "X", "resourceId": {"videoId": "abc"}}}], "nextPageToken": "t"},
                 {"items": [{"snippet": {"title": "old", "publishedAt": "2026-11-01T00:00:00Z",
                                         "channelTitle": "X", "resourceId": {"videoId": "old"}}}], "nextPageToken": "t2"}]
        calls = []
        def fake(url, timeout=20):
            calls.append(url)
            return _j.dumps(pages[len(calls) - 1]).encode()
        with mock.patch.object(h, "get", fake):
            out = h.uploads("UCabcdefghijklmnopqrstuv", "k", "2026-11-20T00:00:00Z")
        self.assertEqual(len(calls), 2)  # stops once uploads are older than the lookback
        self.assertIn("playlistId=UUabcdefghijklmnopqrstuv", calls[0])
        self.assertEqual(out[0]["url"], "https://www.youtube.com/watch?v=abc")


class MatchdayTest(unittest.TestCase):
    def test_title_rules(self):
        from live_board import highlights as h
        self.assertTrue(h.is_matchday_goals("ALL GOALS | UCL Matchday 5 | CBS Sports Golazo"))
        self.assertTrue(h.is_matchday_goals("Every Goal from Champions League MD5!"))
        self.assertFalse(h.is_matchday_goals("ALL GOALS | UEL Matchday 5 Europa League"))
        self.assertFalse(h.is_matchday_goals("Arsenal vs. Dortmund: Extended Highlights | UCL League Phase MD 5"))
        self.assertFalse(h.is_matchday_goals("All goals | UWCL Matchday 3 Champions League"))

    def test_picks_newest_and_reads_round(self):
        import datetime as dt
        from live_board import highlights as h
        now = dt.datetime.now(dt.timezone.utc)
        iso = lambda d: (now - dt.timedelta(days=d)).strftime("%Y-%m-%dT%H:%M:%SZ")
        vids = [{"title": "ALL GOALS | UCL Matchday 4", "url": "https://www.youtube.com/watch?v=a", "published": iso(14), "channel": "C"},
                {"title": "ALL GOALS | UCL Matchday 5", "url": "https://www.youtube.com/watch?v=b", "published": iso(1), "channel": "C"},
                {"title": "Old | UCL Matchday 1 all goals", "url": "https://www.youtube.com/watch?v=c", "published": iso(60), "channel": "C"}]
        got = h.pick_matchday(vids, "")
        self.assertEqual((got["url"][-1], got["round"]), ("b", 5))
