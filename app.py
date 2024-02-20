import streamlit as st
from st_clickable_images import clickable_images
import pandas as pd
from pytube import YouTube
import os
import requests
from time import sleep

upload_endpoint = "https://api.assemblyai.com/v2/upload" 
transcript_endpoint = "https://api.assemblyai.com/v2/transcript"

headers = {
    #Authorization": st.secrets["auth_key"],
    "authorization": "39b6c7a2679547c6b21b07374b3c5fae",
    "content-type": "application/json"    
}

@st.cache_data
def save_audio(url):
    yt = YouTube(url)
    video = yt.streams.filter(only_audio=True).first()
    out_file = video.download()
    base, ext = os.path.splitext(out_file)
    file_name = base + '.mp3'
    os.rename(out_file, file_name)
    print(yt.title + " has been successfully downloaded.")
    print(file_name)
    return yt.title, file_name, yt.thumbnail_url

@st.cache_data
def upload_to_AssemblyAI(save_location):
    CHUNK_SIZE = 5242880
    print(save_location)

    def read_file(filename):
        with open(filename, 'rb') as _file:
            while True:
                print("chunk uploaded")
                data = _file.read(CHUNK_SIZE)
                if not data:
                    break
                yield data

    upload_response = requests.post(
        upload_endpoint,
        headers=headers, data=read_file(save_location)
    )
    print(upload_response.json())

    if "error" in upload_response.json():
        return None, upload_response.json()["error"]

    audio_url = upload_response.json()['upload_url']
    print('Uploaded to', audio_url)

    return audio_url, None


@st.cache_data
def start_analysis(audio_url):
    print(audio_url)

    data = {
        'audio_url': audio_url,
        'iab_categories': True,
        'content_safety': True,
        "summarization": True,
        "summary_model": "informative",
        "summary_type": "bullets"
    }

    transcript_response = requests.post(transcript_endpoint, json=data, headers=headers)
    print(transcript_response)
    st.write(transcript_response.json())

    if 'error' in transcript_response.json():
        return None, transcript_response.json()['error']

    transcript_id = transcript_response.json()['id']
    polling_endpoint = transcript_endpoint + "/" + transcript_id

    print("Transcribing at", polling_endpoint)
    return polling_endpoint, None


@st.cache_data
def get_analysis_results(polling_endpoint):

    status = 'submitted'

    while True:
        print(status)
        polling_response = requests.get(polling_endpoint, headers=headers)
        status = polling_response.json()['status']
        st.write(polling_response.json())
        st.write(status)

        if status == 'submitted' or status == 'processing' or status == 'queued':
            print('not ready yet')
            sleep(10)

        elif status == 'completed':
            print('creating transcript')

            return polling_response

            break
        else:
           print('error')
           return False
           break




st.title("YouTube Content Analyzer")
st.markdown("1. A Summary Of the Video")
st.markdown("2. The Topics Discussed in the Video")
st.markdown("3. Whether there are sensitive topics discussed in the video")



default_bool = st.checkbox("Use a default file")

if default_bool:
    file = open("./yt_links.txt")
else:
    file = st.file_uploader("Upload a file that includes the link (.txt)")

if file is not None:
    dataframe = pd.read_csv(file, header=None) #Get the txt links in a python list using pandas.read_csv
    dataframe.columns = ['urls']
    url_list = dataframe['urls'].tolist()

    titles = []
    locations = []
    thumbnails = []

    for video_url in url_list:
        # download the audio file
        video_title, save_location, video_thumbnail = save_audio(video_url)
        titles.append(video_title)
        locations.append(save_location)
        thumbnails.append(video_thumbnail)

    selected_video = clickable_images(thumbnails,
    titles = titles,
    div_style={"height": "400px", "display": "flex", "justify-content": "center", "flex-wrap": "wrap", "overflow-y":"auto"},
    img_style={"margin": "5px", "height": "150px"}
    )

    st.markdown(f"Thumbnail #{selected_video} clicked" if selected_video > -1 else "No image clicked")

    if selected_video > -1:
        video_url = url_list[selected_video]
        video_title = titles[selected_video]
        save_location = locations[selected_video]

        st.header(video_title)
        st.audio(save_location)

        # upload mp3 to assemblyAI
        audio_url = upload_to_AssemblyAI(save_location)

        # request to start analysis
        audio_url, _ = upload_to_AssemblyAI(save_location)
        polling_endpoint = start_analysis(audio_url)
        
        # receive result
        polling_endpoint, _ = start_analysis(audio_url)
        results = get_analysis_results(polling_endpoint)

        summary = results.json()['summary']
        topics = results.json()['iab_categories_result']['summary']
        sensitive_topics = results.json()['content_safety_labels']['summary']

        st.header("Summary of Videos")
        st.write(summary)

        st.header("Sensitive content")
        if sensitive_topics != {}:
            st.subheader('Mention of the following sensitive topics detected.')
            moderation_df = pd.DataFrame(sensitive_topics.items())
            moderation_df.columns = ['topic','confidence']
            st.dataframe(moderation_df, use_container_width=True)
        else:
            st.subheader('All Clear! No sensitive content detected.')

        st.header("Topics Discussed")
        topics_df = pd.DataFrame(topics.items())
        topics_df.columns = ['topic','confidence']
        topics_df["topic"] = topics_df["topic"].str.split(">")
        expanded_topics = topics_df.topic.apply(pd.Series).add_prefix('topic_level_')
        topics_df = topics_df.join(expanded_topics).drop('topic', axis=1).sort_values(['confidence'], ascending=False)

        st.dataframe(topics_df, use_container_width=True)
