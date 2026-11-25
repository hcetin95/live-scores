# Live Scores

A small live football scoreboard for my phone: **https://hcetin95.github.io/live-scores/**

- Scores, match minute, goals, assists, cards and lineups come straight from ESPN's public scoreboard, refreshed every 30 seconds while a game is live.
- Every hour, a GitHub Action checks the official YouTube channels for highlights of finished games and adds a ▶ Highlights link.

Leagues: Champions League, Premier League, La Liga, Serie A, Bundesliga, Ligue 1, Süper Lig.

Nothing personal is stored here. Optional secret: `YOUTUBE_API_KEY` (YouTube Data API) to find highlights the RSS feeds miss.
