# Music Recommendation Engine

A content- and behavior-based music recommendation system that takes a song and returns a ranked list of similar tracks, combining crowd-sourced listening data with audio feature analysis.

## How it works

1. **Candidate generation** — [Last.fm's](https://www.last.fm/api) `track.getSimilar` endpoint surfaces tracks that real listeners have historically grouped with the input song, providing a behavioral signal that complements the audio-based similarity analysis.
2. **Feature resolution** — Each candidate is resolved against [ReccoBeats](https://reccobeats.com/docs), which provides Spotify-style audio features (danceability, energy, acousticness, tempo, etc.) for the underlying track.
3. **Similarity ranking** — Each candidate's audio feature vector is normalized and compared to the input song's vector using weighted Euclidean distance, producing a final ranked list of the most acoustically similar tracks within the behaviorally-relevant candidate pool.

This two-stage approach was motivated by testing content-based similarity alone against the AcousticBrainz dataset, where low-level audio features produced recommendations that could be acoustically similar without consistently capturing the broader genre or listening context of a track.

## Tech stack

- **Python** — recommendation pipeline and API integration
- **Streamlit** — web interface
- **Pandas** - result handling and display
- **APIs** - Last.fm and ReccoBeats
- **Concurrency** — `ThreadPoolExecutor` for parallel API requests
- **Rate limiting** — shared request limiter and retry handling for API rate limits

## Setup

Clone the repo and install dependencies:
```bash
git clone https://github.com/yourusername/music_rec_project.git
cd music_rec_project
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### API keys

This project requires a free [Last.fm API key](https://www.last.fm/api/account/create). Create a '.streamlit/secrets.toml' file in the project root:
```
LASTFM_API_KEY= "your_key_here"
```

## Usage

Run the Streamlit app locally:
```bash
streamlit run streamlit_app.py
```
Enter a song title and artist, and the app returns a ranked list of similar tracks.

## Known limitations

- ReccoBeats' database doesn't have 100% coverage of every track on Spotify, so some Last.fm candidates may be dropped if their audio features aren't available.
- Both Last.fm and ReccoBeats enforce rate limits; very obscure songs with limited candidate data may return shorter result lists. Additionally, this means returning the audio feature data from ReccoBeats can be a slow process- response times for full candidate lists take approximately 30 seconds to 1 minute.
- Feature weights are currently uniform across all audio dimensions; a v2 could tune these empirically or make them user-adjustable.

## Possible future improvements

- Album art integration for presentability
- User-adjustable feature weighting (e.g. prioritize tempo/energy vs. mood)
- Persistent caching layer to reduce redundant API calls
- Deployed, publicly hosted version

## Credits

Built by Liam Miller. Uses data from [Last.fm](https://www.last.fm/api) and [ReccoBeats](https://reccobeats.com).
