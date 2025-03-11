from flask import Flask, request, jsonify, send_file, render_template, Response
from pytubefix import YouTube
import os
import subprocess
import time

app = Flask(__name__)

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

progress_data = {}
completed_files = {}

def download_youtube_video(url, client_id):
    try:
        yt = YouTube(url)
        video_stream = yt.streams.filter(adaptive=True, file_extension="mp4", only_video=True).order_by("resolution").desc().first()
        audio_stream = yt.streams.filter(adaptive=True, file_extension="mp4", only_audio=True).order_by("abr").desc().first()

        video_path = os.path.join(DOWNLOAD_FOLDER, f"{client_id}_video.mp4")
        audio_path = os.path.join(DOWNLOAD_FOLDER, f"{client_id}_audio.mp4")
        final_filename = f"{yt.title}.mp4"
        final_path = os.path.join(DOWNLOAD_FOLDER, final_filename)

        def progress_callback(stream, chunk, bytes_remaining):
            total_size = stream.filesize
            bytes_downloaded = total_size - bytes_remaining
            percentage = bytes_downloaded / total_size * 100
            progress_data[client_id] = f"{stream.type.capitalize()} Download: {percentage:.2f}%"
        
        yt.register_on_progress_callback(progress_callback)

        # 動画と音声のダウンロード
        yt.streams.get_by_itag(video_stream.itag).download(output_path=DOWNLOAD_FOLDER, filename=f"{client_id}_video.mp4")
        yt.streams.get_by_itag(audio_stream.itag).download(output_path=DOWNLOAD_FOLDER, filename=f"{client_id}_audio.mp4")

        progress_data[client_id] = "Merging Video and Audio..."
        command = ["ffmpeg", "-i", video_path, "-i", audio_path, "-c:v", "copy", "-c:a", "aac", "-strict", "experimental", final_path]
        subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # 一時ファイルを削除
        if os.path.exists(video_path):
            os.remove(video_path)
        if os.path.exists(audio_path):
            os.remove(audio_path)

        progress_data[client_id] = "Download Complete!"
        completed_files[client_id] = final_filename  # 完了したファイル名を保存

        return final_filename
    except Exception as e:
        progress_data[client_id] = f"Error: {e}"
        return None

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/download", methods=["POST"])
def download():
    url = request.json.get("url")
    client_id = str(int(time.time()))  # 一意のクライアントID（タイムスタンプ）
    
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    progress_data[client_id] = "Starting Download..."
    
    def download_task():
        filename = download_youtube_video(url, client_id)
        completed_files[client_id] = filename  # 完了したファイル名を保存

    from threading import Thread
    Thread(target=download_task).start()

    return jsonify({"message": "Download started", "client_id": client_id})

@app.route("/progress/<client_id>")
def progress(client_id):
    def event_stream():
        while True:
            time.sleep(1)
            yield f"data: {progress_data.get(client_id, 'Waiting...')}\n\n"

    return Response(event_stream(), mimetype="text/event-stream")

@app.route("/get_filename/<client_id>")
def get_filename(client_id):
    filename = completed_files.get(client_id)
    if filename:
        return jsonify({"filename": filename})
    return jsonify({"error": "File not ready"}), 404

@app.route("/file/<filename>")
def get_file(filename):
    file_path = os.path.join(DOWNLOAD_FOLDER, filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    return jsonify({"error": "File not found"}), 404

if __name__ == "__main__":
    app.run(debug=True, threaded=True)
