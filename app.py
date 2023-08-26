import string
from flask import Flask, render_template, request, send_file, session
from datetime import datetime
from pytube import YouTube, Playlist, Channel
from pytube.exceptions import AgeRestrictedError, RegexMatchError
import os, zipfile, concurrent.futures, shutil

app = Flask(__name__)
app.secret_key = "buy_me_car"

TEMP_DIR = 'temp_downloads'
TEMP_ZIP_DIR = 'temp_zips'
MAX_THREADS = 30

RUNNING_DOWNLOADED_VIDEOS = 0

def create_temp_dir_if_not_exists(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)

def clean_filename(title):
    valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
    cleaned_title = ''.join(c if c in valid_chars else '_' for c in title)
    return cleaned_title

def download_video(video_url):
    try:
        video = YouTube(video_url)
        youtube_stream = video.streams.get_lowest_resolution()
        cleaned_title = clean_filename(video.title)
        temp_file_path = os.path.join(TEMP_DIR, f"{cleaned_title}.mp4")
        youtube_stream.download(output_path=TEMP_DIR, filename=f"{cleaned_title}.mp4")
        check_exist = os.path.exists(temp_file_path)

        data = {
            'video': video,
            'download_started_at': datetime.now(),
            'download_ended_at': datetime.now(),
            'downloaded_in': (datetime.now() - datetime.now()).seconds
        }

        return data if check_exist else None

    except Exception as e:
        return None

def download_multiple_videos(link, option):
    global RUNNING_DOWNLOADED_VIDEOS
    if option == 'single':
        video_urls = [link]
    elif option == 'channel':
        try:
            video_urls = Channel(link).video_urls
        except RegexMatchError:
            video_urls = []
    elif option == 'playlist':
        video_urls = Playlist(link).video_urls
    else:
        return [], [], 0

    total_videos = len(video_urls)
    downloaded_videos = []
    videos_with_error = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        futures = [executor.submit(download_video, video_url) for video_url in video_urls]
        concurrent.futures.wait(futures)

        for future in futures:
            result = future.result()
            if result:
                downloaded_videos.append(result)
                RUNNING_DOWNLOADED_VIDEOS += 1
            else:
                videos_with_error.append(result)

    return downloaded_videos, videos_with_error, total_videos

def create_zip(downloaded_videos):
    try:
        create_temp_dir_if_not_exists(TEMP_ZIP_DIR)
        temp_zip_path = os.path.join(TEMP_ZIP_DIR, "downloaded_videos.zip")
        with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for index, video_data in enumerate(downloaded_videos, start=1):
                video = video_data['video']
                try:
                    cleaned_title = clean_filename(video.title)
                    video_stream_path = os.path.join(TEMP_DIR, f"{cleaned_title}.mp4")
                    if os.path.exists(video_stream_path):
                        unique_filename = f"{cleaned_title}_{index}.mp4"
                        zipf.write(video_stream_path, unique_filename)
                except AgeRestrictedError:
                    pass

        return temp_zip_path
    except Exception as e:
        return None

def cleanup_temp_directory():
    try:
        shutil.rmtree(TEMP_DIR)
        shutil.rmtree(TEMP_ZIP_DIR)
    except Exception as e:
        print(f"Error cleaning up temp directory: {e}")

@app.route('/', methods=['GET', 'POST'])
def index():
    downloaded_videos = []
    total_videos = 0

    if request.method == 'POST':
        link = request.form['link']
        option = request.form['option']
        create_temp_dir_if_not_exists(TEMP_DIR)
        downloaded_videos, _, total_videos = download_multiple_videos(link, option)
        zip_file_path = create_zip(downloaded_videos)
        session['downloaded_zip'] = zip_file_path

    return render_template('index.html', downloaded_videos=downloaded_videos, total_videos=total_videos, total_downloaded_videos=RUNNING_DOWNLOADED_VIDEOS)

@app.route('/download_zip', methods=['GET'])
def download_zip():
    zip_file_path = session.get('downloaded_zip')
    if zip_file_path and os.path.exists(zip_file_path):
        zip_file_name = os.path.basename(zip_file_path)

        response = send_file(zip_file_path, as_attachment=True, download_name=zip_file_name)

        cleanup_temp_directory()

        return response
    else:
        return "Zip file not available !", 404

if __name__ == '__main__':
    app.run(debug=True)

'''
        # edge cases
        if option == 'playlist':
            if 'watch?v' in link:
                error = "invalid option ! please select video for a video URL."
            elif '@' in link:
                error = "invalid option ! please select channel for a channel URL."
            
        elif option == 'channel':
            if 'watch?v' in link:
                error = "invalid option ! please select video for a video URL."
            elif 'playlist?list=' in link:
                error = "invalid option ! please select playlist for a playlist URL."
        
        elif option == 'single':
            if '@' in link:
                error = "invalid option ! please select channel for a channel URL."
            elif 'playlist?list=' in link:
                error = "invalid option ! please select playlist for a playlist URL."

'''