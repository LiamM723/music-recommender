import streamlit as st
import pandas as pd
from t50_ranking import get_recommendations

# make text in song title/artist name boxes black
st.markdown(
    """
    <style>
    .stTextInput input {
        color: #191414;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

def local_css(file_name):
    with open(file_name) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

local_css("style.css")

st.title("Music Recommender", text_alignment="center")

track_name = st.text_input("Song title")
artist_name = st.text_input("Artist name")

# converted to DataFrame so I can hopefully include album cover art with each song in a future version
results_df = pd.DataFrame()

# for centering the action button
col1, col2, col3 = st.columns([1, 1, 1])

with col2:
    if st.button("Find similar songs", type="primary", use_container_width=True):
        if not track_name or not artist_name:
            st.warning("Please enter both a song title and an artist name.")
        else:
            with st.spinner("Finding similar songs..."):
                results = get_recommendations(track_name, artist_name)

            if not results:
                st.error("No results found. Try a different song.")
            else:
                results_df = pd.DataFrame(results)

# display results
st.dataframe(
    results_df, column_config={
        "album_art": st.column_config.ImageColumn("Cover", width="small")
        }
    )