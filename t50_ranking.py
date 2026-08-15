import requests
import certifi
import os
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import streamlit as st

class RateLimiter:
    def __init__(self, min_interval):
        self.min_interval = min_interval
        self.lock = threading.Lock()
        self.last_call = 0

    def wait(self):
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_call
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self.last_call = time.monotonic()

RECCO_BASE = "https://api.reccobeats.com/v1"

os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

# Some features like valence/danceability are values 0.0-1.0, while others like tempo/loudness are in BPM or dB.
# These would impact the distance measure far more than the decimal values, so we must normalize each vector.
def normalize_vectors(vectors, feature_list):
    ranges = {}
    for feat in feature_list:
        vals = [v[feat] for v in vectors.values() if feat in v]
        if not vals:
            continue
        lo, hi = min(vals), max(vals)
        ranges[feat] = (lo, hi if hi != lo else lo + 1)

    normalized = {}
    for recco_id, v in vectors.items():
        nv = {}
        for feat in feature_list:
            if feat in v and feat in ranges:
                lo, hi = ranges[feat]
                nv[feat] = (v[feat] - lo) / (hi - lo)
        normalized[recco_id] = nv
    return normalized

# The final distance calculation for each candidate song to the base song
def weighted_euclidean_distance(v1, v2, feature_weights):
    common = [f for f in feature_weights if f in v1 and f in v2]
    if not common:
        return None
    return math.sqrt(sum(feature_weights[f] * (v1[f] - v2[f]) ** 2 for f in common))

# LAST.FM / RECCOBEATS STUFF -------------------------------------------------------
LASTFM_API_KEY = st.secrets["LASTFM_API_KEY"]

# Pulls the [limit] most similar tracks to the base track based on user listening data
def get_lastfm_similar(track_name, artist_name, limit=100):
    url = "http://ws.audioscrobbler.com/2.0/"
    params = {
        "method": "track.getsimilar",
        "track": track_name,
        "artist": artist_name,
        "api_key": LASTFM_API_KEY,
        "format": "json",
        "limit": limit,
        "autocorrect": 1
    }
    response = requests.get(url, params=params)
    if response.status_code != 200:
        return []
    data = response.json()
    return data.get("similartracks", {}).get("track", [])

# Finds the Reccobeats IDs for each candidate from get_lastfm_similar so we can access
# each candidate's audio features. Includes multiple threads and a rate limiter to
# expedite the process
def get_reccobeats_ids(candidate_pool, session, limiter, max_workers=2):
    recco_lookup = {}
    recco_track_info = {}

    def fetch_one(entry):
        track_name = entry.get("name")
        artist_name = entry.get("artist", {}).get("name")
        if not track_name or not artist_name:
            return None
        limiter.wait()  # <-- shared across all threads to avoid 429s
        result = search_reccobeats_track(track_name, artist_name, session)
        return (track_name, artist_name, result)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(fetch_one, entry) for entry in candidate_pool]
        for future in as_completed(futures):
            outcome = future.result()
            if not outcome:
                continue
            track_name, artist_name, result = outcome
            if result:
                recco_id = result["id"]
                recco_lookup[f"{track_name}|{artist_name}"] = recco_id
                recco_track_info[recco_id] = {
                    "title": result.get("trackTitle", track_name),
                    "artist": result.get("artists", [{}])[0].get("name", artist_name) if result.get("artists") else artist_name
                }
    return recco_lookup, recco_track_info

# Helper for get_reccobeats_ids
def search_reccobeats_track(track_name, artist_name, session):
    params = {
        "searchText": track_name,
        "artist": artist_name,
        "size": 1
    }
    response = session.get(f"{RECCO_BASE}/track/search", params=params)
    if response.status_code != 200:
        return None
    data = response.json()
    results = data.get("content", data) if isinstance(data, dict) else data
    return results[0] if results else None

# Gets audio features (danceability, valence, etc) from Reccobeats API. Requests in bulk for efficiency.
def get_audio_features_bulk(recco_ids, session, limiter, batch_size=34, max_workers=4, max_retries=3):
    """Fetch audio features for many ReccoBeats track IDs, batched and threaded with shared rate limiting."""
    features = {}

    batches = [recco_ids[i:i + batch_size] for i in range(0, len(recco_ids), batch_size)]

    def fetch_batch(batch):
        params = {"ids": ",".join(batch)}

        for attempt in range(max_retries):
            limiter.wait()  # shared across all threads
            response = session.get(f"{RECCO_BASE}/audio-features", params=params)

            if response.status_code == 429:
                wait = float(response.headers.get("Retry-After", 1))
                wait = min(wait, 5)  # safety net to avoid trying too soon after 429
                time.sleep(wait)
                continue
            break

        if response.status_code != 200:
            print(f"ReccoBeats /audio-features batch failed: {response.status_code}")
            return {}

        data = response.json()
        results = data.get("content", data) if isinstance(data, dict) else data
        return {item["id"]: item for item in results}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(fetch_batch, batch) for batch in batches]
        for future in as_completed(futures):
            batch_features = future.result()
            features.update(batch_features)

    return features

# Defines a vector for each candidate song where each entry is an audio feature
def build_recco_vectors(audio_features, feature_names):
    vectors = {}
    for recco_id, features in audio_features.items():
        vector = {f: features[f] for f in feature_names if isinstance(features.get(f), (int, float))}
        vectors[recco_id] = vector
    return vectors

# MAIN FUNCTION ----------------------------------------------------------------
def get_recommendations(track_name, artist_name, top_n=50):
    session = requests.Session()
    limiter = RateLimiter(0.05) # <-- optimal time found through trial and error

    base_track = search_reccobeats_track(track_name, artist_name, session)
    if not base_track:
        return []
    base_track_id = base_track["id"]

    candidate_pool = get_lastfm_similar(track_name, artist_name)
    if not candidate_pool:
        return []

    recco_lookup, recco_track_info = get_reccobeats_ids(candidate_pool, session, limiter)
    recco_ids = list(recco_lookup.values())

    all_ids = list(set(recco_ids + [base_track_id]))
    audio_features = get_audio_features_bulk(all_ids, session, limiter)

    recco_feature_names = [
        "acousticness", "danceability", "energy", "instrumentalness",
        "liveness", "loudness", "speechiness", "tempo", "valence"
    ]

    vectors = build_recco_vectors(audio_features, recco_feature_names)
    normalized_vectors = normalize_vectors(vectors, recco_feature_names)

    base_vector = normalized_vectors.get(base_track_id)
    if not base_vector:
        return []

    recco_feature_weights = {f: 1.0 for f in recco_feature_names}
    distances = []
    for recco_id, vec in normalized_vectors.items():
        if recco_id == base_track_id:
            continue
        dist = weighted_euclidean_distance(base_vector, vec, recco_feature_weights)
        if dist is not None:
            distances.append((recco_id, dist))
    distances.sort(key=lambda x: x[1])

    results = []
    for rank, (recco_id, dist) in enumerate(distances[:top_n], start=1):
        info = recco_track_info.get(recco_id, {"title": "Unknown", "artist": "Unknown"})
        results.append({"rank": rank, "title": info["title"], "artist": info["artist"], "distance": round(dist, 4)})
    return results