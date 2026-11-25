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
