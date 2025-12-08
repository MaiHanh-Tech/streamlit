# FILE: tts_server.py
import asyncio
import os
import io
from http.server import SimpleHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import edge_tts

# Cấu hình cổng chạy server TTS
TTS_PORT = 8000
TTS_VOICE = "zh-CN-XiaoyiNeural" # Giọng Trung Quốc mặc định

def generate_audio(text, voice, rate="+0%"):
    """Sử dụng Edge TTS để tạo âm thanh (non-async version for HTTP server)"""
    # Xóa file cũ
    output_file = 'output.mp3'
    if os.path.exists(output_file):
        os.remove(output_file)
        
    async def _gen():
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        await communicate.save(output_file)
        
    try:
        # Chạy asyncio đồng bộ (cần thiết cho http server)
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Nếu đang chạy trong môi trường Streamlit, chạy task
            asyncio.ensure_future(_gen())
            time.sleep(2) # Chờ 2 giây để file được tạo
        else:
            # Nếu chạy độc lập, dùng run_until_complete
            loop.run_until_complete(_gen())
    except:
        asyncio.run(_gen())

    return output_file

class TTSHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        # Lấy tham số từ URL
        parsed_path = urlparse(self.path)
        query_params = parse_qs(parsed_path.query)
        
        text = query_params.get('text', [''])[0]
        
        if not text:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'Error: Missing text parameter')
            return

        # 1. Tạo file MP3
        try:
            output_mp3 = generate_audio(text, TTS_VOICE)
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f'Error generating audio: {e}'.encode('utf-8'))
            return

        # 2. Phục vụ file MP3 đã tạo
        try:
            self.send_response(200)
            self.send_header('Content-type', 'audio/mp3')
            self.send_header('Content-Length', os.path.getsize(output_mp3))
            self.end_headers()
            
            with open(output_mp3, 'rb') as f:
                self.wfile.write(f.read())
                
        except Exception as e:
            print(f"Error serving file: {e}")
            
# Chạy Server
def run_tts_server():
    server_address = ('0.0.0.0', TTS_PORT)
    httpd = HTTPServer(server_address, TTSHandler)
    print(f"Starting TTS server on port {TTS_PORT}...")
    httpd.serve_forever()

if __name__ == "__main__":
    # Để tránh server Streamlit và TTS chạy lẫn nhau (Nếu chị chạy docker-compose thì sẽ tốt hơn)
    # Nếu chạy local: Chạy file này trong một terminal khác
    run_tts_server()
