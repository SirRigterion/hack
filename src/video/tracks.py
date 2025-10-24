import asyncio
import cv2
import numpy as np
from aiortc.media import VideoStreamTrack, AudioStreamTrack
from aiortc.contrib.media import MediaPlayer
import logging
from typing import Optional
import threading
import queue
import time

from src.core.config_log import logger


class CustomVideoTrack(VideoStreamTrack):
    """Кастомный видео трек для WebRTC."""
    
    def __init__(self, width: int = 640, height: int = 480, fps: int = 30):
        super().__init__()
        self.width = width
        self.height = height
        self.fps = fps
        self.frame_interval = 1.0 / fps
        self.last_frame_time = 0
        self.muted = False
        self._camera = None
        self._frame_queue = queue.Queue(maxsize=10)
        self._capture_thread = None
        self._running = False
        
        # Инициализируем камеру
        self._init_camera()
    
    def _init_camera(self):
        """Инициализация камеры."""
        if not CV2_AVAILABLE:
            logger.warning("OpenCV не установлен. Видео захват недоступен.")
            return
            
        try:
            self._camera = cv2.VideoCapture(0)
            if not self._camera.isOpened():
                # Пробуем другие индексы камеры
                for i in range(1, 5):
                    self._camera = cv2.VideoCapture(i)
                    if self._camera.isOpened():
                        break
            
            if self._camera.isOpened():
                self._camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                self._camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                self._camera.set(cv2.CAP_PROP_FPS, self.fps)
                logger.info(f"Камера инициализирована: {self.width}x{self.height}@{self.fps}fps")
            else:
                logger.warning("Не удалось инициализировать камеру")
                
        except Exception as e:
            logger.error(f"Ошибка инициализации камеры: {e}")
    
    def start(self):
        """Запуск захвата видео."""
        if not self._running and self._camera and self._camera.isOpened():
            self._running = True
            self._capture_thread = threading.Thread(target=self._capture_frames)
            self._capture_thread.daemon = True
            self._capture_thread.start()
            logger.info("Захват видео запущен")
    
    def stop(self):
        """Остановка захвата видео."""
        self._running = False
        if self._capture_thread:
            self._capture_thread.join(timeout=1.0)
        
        if self._camera:
            self._camera.release()
            self._camera = None
        
        logger.info("Захват видео остановлен")
    
    def _capture_frames(self):
        """Захват кадров в отдельном потоке."""
        if not CV2_AVAILABLE:
            logger.warning("OpenCV не установлен. Видео захват недоступен.")
            return
            
        while self._running and self._camera and self._camera.isOpened():
            try:
                ret, frame = self._camera.read()
                if ret and not self.muted:
                    # Изменяем размер кадра
                    frame = cv2.resize(frame, (self.width, self.height))
                    
                    # Конвертируем BGR в RGB
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    
                    # Добавляем кадр в очередь
                    try:
                        self._frame_queue.put_nowait(frame)
                    except queue.Full:
                        # Удаляем старый кадр если очередь полная
                        try:
                            self._frame_queue.get_nowait()
                            self._frame_queue.put_nowait(frame)
                        except queue.Empty:
                            pass
                
                time.sleep(self.frame_interval)
                
            except Exception as e:
                logger.error(f"Ошибка захвата кадра: {e}")
                break
    
    async def recv(self):
        """Получение следующего кадра."""
        if self.muted:
            # Возвращаем черный кадр если видео выключено
            frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        else:
            try:
                # Получаем кадр из очереди
                frame = self._frame_queue.get(timeout=0.1)
            except queue.Empty:
                # Возвращаем черный кадр если нет кадров
                frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        
        # Конвертируем в формат для WebRTC
        if not AV_AVAILABLE:
            logger.warning("PyAV не установлен. Видео трек недоступен.")
            return None
            
        from av import VideoFrame
        av_frame = VideoFrame.from_ndarray(frame, format="rgb24")
        av_frame.pts = int(time.time() * 90000)  # 90kHz clock
        
        return av_frame


class CustomAudioTrack(AudioStreamTrack):
    """Кастомный аудио трек для WebRTC."""
    
    def __init__(self):
        super().__init__()
        self.muted = False
        self._audio_queue = queue.Queue(maxsize=100)
        self._running = False
        self._capture_thread = None
        
        # Инициализируем аудио захват
        self._init_audio()
    
    def _init_audio(self):
        """Инициализация аудио захвата."""
        if not PYAUDIO_AVAILABLE:
            logger.warning("PyAudio не установлен. Аудио захват недоступен.")
            self.audio = None
            self.stream = None
            return
            
        try:
            self.audio = pyaudio.PyAudio()
            self.stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=48000,
                input=True,
                frames_per_buffer=1024
            )
            logger.info("Аудио захват инициализирован")
            
        except Exception as e:
            logger.error(f"Ошибка инициализации аудио: {e}")
            self.audio = None
            self.stream = None
    
    def start(self):
        """Запуск захвата аудио."""
        if not self._running and self.stream:
            self._running = True
            self._capture_thread = threading.Thread(target=self._capture_audio)
            self._capture_thread.daemon = True
            self._capture_thread.start()
            logger.info("Захват аудио запущен")
    
    def stop(self):
        """Остановка захвата аудио."""
        self._running = False
        if self._capture_thread:
            self._capture_thread.join(timeout=1.0)
        
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        
        if self.audio:
            self.audio.terminate()
        
        logger.info("Захват аудио остановлен")
    
    def _capture_audio(self):
        """Захват аудио в отдельном потоке."""
        while self._running and self.stream:
            try:
                if not self.muted:
                    data = self.stream.read(1024, exception_on_overflow=False)
                    try:
                        self._audio_queue.put_nowait(data)
                    except queue.Full:
                        # Удаляем старые данные если очередь полная
                        try:
                            self._audio_queue.get_nowait()
                            self._audio_queue.put_nowait(data)
                        except queue.Empty:
                            pass
                else:
                    # Отправляем тишину если аудио заглушено
                    silence = b'\x00' * 1024
                    try:
                        self._audio_queue.put_nowait(silence)
                    except queue.Full:
                        pass
                
            except Exception as e:
                logger.error(f"Ошибка захвата аудио: {e}")
                break
    
    async def recv(self):
        """Получение следующего аудио фрейма."""
        try:
            if self.muted:
                # Возвращаем тишину если аудио заглушено
                data = b'\x00' * 1024
            else:
                data = self._audio_queue.get(timeout=0.1)
        except queue.Empty:
            # Возвращаем тишину если нет данных
            data = b'\x00' * 1024
        
        # Конвертируем в формат для WebRTC
        if not AV_AVAILABLE:
            logger.warning("PyAV не установлен. Аудио трек недоступен.")
            return None
            
        from av import AudioFrame
        audio_frame = AudioFrame.from_ndarray(
            np.frombuffer(data, dtype=np.int16).reshape(1, -1),
            format="s16",
            layout="mono"
        )
        audio_frame.sample_rate = 48000
        
        return audio_frame


class ScreenShareTrack(VideoStreamTrack):
    """Трек для демонстрации экрана."""
    
    def __init__(self):
        super().__init__()
        self.width = 1280
        self.height = 720
        self.fps = 15
        self.frame_interval = 1.0 / self.fps
        self.last_frame_time = 0
        self.muted = False
        self._running = False
        self._capture_thread = None
        self._frame_queue = queue.Queue(maxsize=5)
        
        # Инициализируем захват экрана
        self._init_screen_capture()
    
    def _init_screen_capture(self):
        """Инициализация захвата экрана."""
        if not MSS_AVAILABLE:
            logger.warning("MSS не установлен. Захват экрана недоступен.")
            self.sct = None
            return
            
        try:
            self.sct = mss.mss()
            logger.info("Захват экрана инициализирован")
        except Exception as e:
            logger.error(f"Ошибка инициализации захвата экрана: {e}")
            self.sct = None
    
    def start(self):
        """Запуск захвата экрана."""
        if not self._running and self.sct:
            self._running = True
            self._capture_thread = threading.Thread(target=self._capture_screen)
            self._capture_thread.daemon = True
            self._capture_thread.start()
            logger.info("Захват экрана запущен")
    
    def stop(self):
        """Остановка захвата экрана."""
        self._running = False
        if self._capture_thread:
            self._capture_thread.join(timeout=1.0)
        
        if self.sct:
            self.sct.close()
        
        logger.info("Захват экрана остановлен")
    
    def _capture_screen(self):
        """Захват экрана в отдельном потоке."""
        while self._running and self.sct:
            try:
                if not self.muted:
                    # Захватываем весь экран
                    screenshot = self.sct.grab(self.sct.monitors[1])
                    
                    # Конвертируем в numpy array
                    frame = np.array(screenshot)
                    
                    # Изменяем размер
                    frame = cv2.resize(frame, (self.width, self.height))
                    
                    # Конвертируем BGRA в RGB
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2RGB)
                    
                    # Добавляем кадр в очередь
                    try:
                        self._frame_queue.put_nowait(frame)
                    except queue.Full:
                        # Удаляем старый кадр если очередь полная
                        try:
                            self._frame_queue.get_nowait()
                            self._frame_queue.put_nowait(frame)
                        except queue.Empty:
                            pass
                else:
                    # Возвращаем черный кадр если демонстрация выключена
                    frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
                    try:
                        self._frame_queue.put_nowait(frame)
                    except queue.Full:
                        pass
                
                time.sleep(self.frame_interval)
                
            except Exception as e:
                logger.error(f"Ошибка захвата экрана: {e}")
                break
    
    async def recv(self):
        """Получение следующего кадра экрана."""
        try:
            if self.muted:
                # Возвращаем черный кадр если демонстрация выключена
                frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
            else:
                frame = self._frame_queue.get(timeout=0.1)
        except queue.Empty:
            # Возвращаем черный кадр если нет кадров
            frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        
        # Конвертируем в формат для WebRTC
        if not AV_AVAILABLE:
            logger.warning("PyAV не установлен. Видео трек недоступен.")
            return None
            
        from av import VideoFrame
        av_frame = VideoFrame.from_ndarray(frame, format="rgb24")
        av_frame.pts = int(time.time() * 90000)  # 90kHz clock
        
        return av_frame


class RecordingTrack(VideoStreamTrack):
    """Трек для записи видео."""
    
    def __init__(self, output_path: str, width: int = 1280, height: int = 720, fps: int = 30):
        super().__init__()
        self.output_path = output_path
        self.width = width
        self.height = height
        self.fps = fps
        self.frames = []
        self._recording = False
        
        # Инициализируем видеозапись
        self._init_recording()
    
    def _init_recording(self):
        """Инициализация записи."""
        try:
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            self.writer = cv2.VideoWriter(
                self.output_path,
                fourcc,
                self.fps,
                (self.width, self.height)
            )
            logger.info(f"Запись инициализирована: {self.output_path}")
        except Exception as e:
            logger.error(f"Ошибка инициализации записи: {e}")
            self.writer = None
    
    def start_recording(self):
        """Начало записи."""
        self._recording = True
        logger.info("Запись начата")
    
    def stop_recording(self):
        """Остановка записи."""
        self._recording = False
        if self.writer:
            self.writer.release()
        logger.info("Запись остановлена")
    
    async def recv(self):
        """Получение кадра для записи."""
        # Здесь должна быть реализация получения кадра
        # Пока что возвращаем пустой кадр
        from av import VideoFrame
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        av_frame = VideoFrame.from_ndarray(frame, format="rgb24")
        av_frame.pts = int(time.time() * 90000)
        
        # Записываем кадр если запись активна
        if self._recording and self.writer:
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            self.writer.write(frame_bgr)
        
        return av_frame
