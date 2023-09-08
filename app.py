import string
from flask import Flask, render_template, request, send_file, session
from datetime import datetime
from pytube import YouTube, Playlist
from pytube.exceptions import AgeRestrictedError
import os, zipfile, concurrent.futures, shutil, csv
import moviepy.editor as mp

app = Flask(__name__)
app.secret_key = "buy_me_car"

TEMP_DIR = 'temp_downloads'
TEMP_ZIP_DIR = 'temp_zips'
TEMP_CONVERT_DIR = 'temp_converted'
MAX_THREADS = 50 # pending, might increase

RUNNING_DOWNLOADED_VIDEOS = 0

def make_dir_if_not_exists(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)

def clean_title(title):
    valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
    cleaned_title = ''.join(c if c in valid_chars else '_' for c in title)
    return cleaned_title

def download(url):
    try:
        vid = YouTube(url)
        stream = vid.streams.get_lowest_resolution()
        title = clean_title(vid.title)
        temp_path = os.path.join(TEMP_DIR, f"{title}.mp4")
        stream.download(output_path=TEMP_DIR, filename=f"{title}.mp4")
        exists = os.path.exists(temp_path)

        data = {
            'vid': vid,
            'start': datetime.now(),
            'end': datetime.now(),
            'duration': (datetime.now() - datetime.now()).seconds
        }

        return data if exists else None

    except Exception as e:
        print("Error during video download:", e)
        return None

def download_all(link, option):
    global RUNNING_DOWNLOADED_VIDEOS
    if option == 'single':
        urls = [link]
    elif option == 'playlist':
        urls = Playlist(link).video_urls
    else:
        return [], [], 0

    total = len(urls)
    downloaded = []
    errors = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        futures = [executor.submit(download, u) for u in urls]
        concurrent.futures.wait(futures)

        for future in futures:
            result = future.result()
            if result:
                downloaded.append(result)
                RUNNING_DOWNLOADED_VIDEOS += 1
            else:
                errors.append(result)

    return downloaded, errors, total

def convert_to_audio(vid_path, audio_format):
    try:
        vid = mp.VideoFileClip(vid_path)
        make_dir_if_not_exists(TEMP_CONVERT_DIR)
        new_path = vid_path.replace(TEMP_DIR, TEMP_CONVERT_DIR).replace('.mp4', f'.{audio_format}')
        vid.audio.write_audiofile(new_path, codec='pcm_s16le', fps=44100)
        return new_path
    except Exception as e:
        return None

def convert_all_videos(vid_paths, audio_format):
    converted_paths = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        futures = [executor.submit(convert_to_audio, v_path, audio_format) for v_path in vid_paths]
        concurrent.futures.wait(futures)
        for future in futures:
            result = future.result()
            if result:
                converted_paths.append(result)
    return converted_paths

def create_zip(downloaded, audio_format, converted_paths=None):
    try:
        make_dir_if_not_exists(TEMP_ZIP_DIR)
        temp_zip_path = os.path.join(TEMP_ZIP_DIR, "downloaded.zip")
        with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for index, vid_data in enumerate(downloaded, start=1):
                vid = vid_data['vid']
                try:
                    title = clean_title(vid.title)
                    original_path = os.path.join(TEMP_DIR, f"{title}.mp4")
                    zipf.write(original_path, f"{title}_{index}.mp4")
                except AgeRestrictedError:
                    pass

            csv_path = os.path.join(TEMP_DIR, "logs.csv")
            with open(csv_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
                csv_writer = csv.writer(csvfile)
                csv_writer.writerow(['Time', 'Title', 'Description'])
                for vid_data in downloaded:
                    vid = vid_data['vid']
                    csv_writer.writerow([
                        vid_data['end'],
                        vid.title,
                        vid.description
                    ])
            
            zipf.write(csv_path, "logs.csv")

        return temp_zip_path
    except Exception as e:
        return None

def cleanup():
    try:
        shutil.rmtree(TEMP_DIR)
        shutil.rmtree(TEMP_ZIP_DIR)
        shutil.rmtree(TEMP_CONVERT_DIR)
    except Exception as e:
        print(f"Error cleaning up: {e}")

@app.route('/', methods=['GET', 'POST'])
def index():
    downloaded = []
    not_downloaded = []  
    total = 0

    if request.method == 'POST':
        link = request.form['link']
        option = request.form['option']
        audio_format = request.form['format']
        make_dir_if_not_exists(TEMP_DIR)
        downloaded, errors, total = download_all(link, option)
        not_downloaded = errors 
        
        if audio_format == 'wav':
            converted_paths = convert_all_videos([os.path.join(TEMP_DIR, f"{clean_title(vid['vid'].title)}.mp4") for vid in downloaded], 'wav')
            zip_path = create_zip(downloaded, 'wav', converted_paths)
        else:
            zip_path = create_zip(downloaded, 'mp4')
        
        session['downloaded_zip'] = zip_path

    return render_template('index.html', downloaded_videos=downloaded, not_downloaded_videos=not_downloaded, total_videos=total, total_downloaded_videos=RUNNING_DOWNLOADED_VIDEOS)

@app.route('/download_zip', methods=['GET'])
def download_zip():
    zip_path = session.get('downloaded_zip')
    if zip_path and os.path.exists(zip_path):
        zip_name = os.path.basename(zip_path)

        response = send_file(zip_path, as_attachment=True, download_name=zip_name)

        cleanup()

        return response
    else:
        return "Zip file not available!", 404

if __name__ == '__main__':
    make_dir_if_not_exists(TEMP_DIR)
    make_dir_if_not_exists(TEMP_CONVERT_DIR)  
    make_dir_if_not_exists(TEMP_ZIP_DIR)
    app.run(debug=True)
