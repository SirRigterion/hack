import asyncio
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path
import threading
import queue
import time

# Импорты с проверкой доступности
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    import numpy as np

from src.core.config_log import logger
from src.video.utils import FileManager


class RecordingManager:
    """Менеджер записи видеоконференций."""
    
    def __init__(self, recordings_dir: str = "recordings"):
        self.recordings_dir = Path(recordings_dir)
        self.recordings_dir.mkdir(exist_ok=True)
        self.active_recordings: Dict[int, 'RoomRecorder'] = {}
        self._lock = asyncio.Lock()
    
    async def start_recording(
        self,
        room_id: int,
        started_by: int,
        participants: List[Dict]
    ) -> str:
        """Начало записи комнаты."""
        async with self._lock:
            if room_id in self.active_recordings:
                raise ValueError(f"Запись комнаты {room_id} уже активна")
            
            # Создаем директорию для записи
            room_dir = self.recordings_dir / f"room_{room_id}"
            room_dir.mkdir(exist_ok=True)
            
            # Генерируем имя файла
            timestamp = datetime.now()
            filename = FileManager.generate_recording_filename(room_id, timestamp)
            file_path = room_dir / filename
            
            # Создаем рекордер
            recorder = RoomRecorder(
                room_id=room_id,
                file_path=str(file_path),
                participants=participants
            )
            
            # Запускаем запись
            await recorder.start()
            
            # Сохраняем активную запись
            self.active_recordings[room_id] = recorder
            
            logger.info(f"Начата запись комнаты {room_id} пользователем {started_by}")
            return str(file_path)
    
    async def stop_recording(self, room_id: int) -> Optional[Dict]:
        """Остановка записи комнаты."""
        async with self._lock:
            if room_id not in self.active_recordings:
                return None
            
            recorder = self.active_recordings[room_id]
            recording_info = await recorder.stop()
            
            # Удаляем из активных записей
            del self.active_recordings[room_id]
            
            logger.info(f"Остановлена запись комнаты {room_id}")
            return recording_info
    
    async def add_participant_to_recording(self, room_id: int, participant_data: Dict):
        """Добавление участника к записи."""
        if room_id in self.active_recordings:
            await self.active_recordings[room_id].add_participant(participant_data)
    
    async def remove_participant_from_recording(self, room_id: int, participant_id: int):
        """Удаление участника из записи."""
        if room_id in self.active_recordings:
            await self.active_recordings[room_id].remove_participant(participant_id)
    
    async def get_recording_status(self, room_id: int) -> bool:
        """Получение статуса записи."""
        return room_id in self.active_recordings
    
    async def get_active_recordings(self) -> List[int]:
        """Получение списка активных записей."""
        return list(self.active_recordings.keys())


class RoomRecorder:
    """Рекордер для записи комнаты."""
    
    def __init__(self, room_id: int, file_path: str, participants: List[Dict]):
        self.room_id = room_id
        self.file_path = file_path
        self.participants = {p['participant_id']: p for p in participants}
        self.is_recording = False
        self.start_time = None
        self.end_time = None
        
        # Настройки записи
        self.fps = 30
        self.width = 1920
        self.height = 1080
        
        # Видео писатель
        self.video_writer = None
        self.audio_writer = None
        
        # Очереди для кадров
        self.video_frames = queue.Queue(maxsize=100)
        self.audio_frames = queue.Queue(maxsize=1000)
        
        # Потоки обработки
        self.video_thread = None
        self.audio_thread = None
        
        # Счетчики кадров
        self.frame_count = 0
        self.audio_sample_count = 0
    
    async def start(self):
        """Начало записи."""
        try:
            # Инициализируем видео писатель
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            self.video_writer = cv2.VideoWriter(
                self.file_path,
                fourcc,
                self.fps,
                (self.width, self.height)
            )
            
            if not self.video_writer.isOpened():
                raise RuntimeError("Не удалось инициализировать видео писатель")
            
            # Запускаем потоки обработки
            self.is_recording = True
            self.start_time = datetime.now()
            
            self.video_thread = threading.Thread(target=self._process_video_frames)
            self.video_thread.daemon = True
            self.video_thread.start()
            
            self.audio_thread = threading.Thread(target=self._process_audio_frames)
            self.audio_thread.daemon = True
            self.audio_thread.start()
            
            logger.info(f"Запись начата: {self.file_path}")
            
        except Exception as e:
            logger.error(f"Ошибка начала записи: {e}")
            raise
    
    async def stop(self) -> Dict:
        """Остановка записи."""
        try:
            self.is_recording = False
            self.end_time = datetime.now()
            
            # Ждем завершения потоков
            if self.video_thread:
                self.video_thread.join(timeout=5.0)
            
            if self.audio_thread:
                self.audio_thread.join(timeout=5.0)
            
            # Закрываем писатели
            if self.video_writer:
                self.video_writer.release()
            
            if self.audio_writer:
                self.audio_writer.release()
            
            # Получаем информацию о файле
            file_size = FileManager.get_file_size_mb(self.file_path)
            duration = FileManager.get_recording_duration(self.file_path)
            
            # Создаем превью
            thumbnail_path = await self._create_thumbnail()
            
            recording_info = {
                'file_path': self.file_path,
                'file_size': file_size,
                'duration': duration,
                'start_time': self.start_time,
                'end_time': self.end_time,
                'thumbnail_path': thumbnail_path,
                'participants_count': len(self.participants)
            }
            
            logger.info(f"Запись остановлена: {self.file_path}")
            return recording_info
            
        except Exception as e:
            logger.error(f"Ошибка остановки записи: {e}")
            raise
    
    async def add_participant(self, participant_data: Dict):
        """Добавление участника к записи."""
        self.participants[participant_data['participant_id']] = participant_data
        logger.info(f"Добавлен участник {participant_data['participant_id']} к записи")
    
    async def remove_participant(self, participant_id: int):
        """Удаление участника из записи."""
        if participant_id in self.participants:
            del self.participants[participant_id]
            logger.info(f"Удален участник {participant_id} из записи")
    
    def add_video_frame(self, frame: np.ndarray, participant_id: int):
        """Добавление видео кадра."""
        if self.is_recording:
            try:
                frame_data = {
                    'frame': frame,
                    'participant_id': participant_id,
                    'timestamp': time.time()
                }
                self.video_frames.put_nowait(frame_data)
            except queue.Full:
                # Удаляем старый кадр если очередь полная
                try:
                    self.video_frames.get_nowait()
                    self.video_frames.put_nowait(frame_data)
                except queue.Empty:
                    pass
    
    def add_audio_frame(self, audio_data: bytes, participant_id: int):
        """Добавление аудио кадра."""
        if self.is_recording:
            try:
                audio_frame = {
                    'data': audio_data,
                    'participant_id': participant_id,
                    'timestamp': time.time()
                }
                self.audio_frames.put_nowait(audio_frame)
            except queue.Full:
                # Удаляем старые данные если очередь полная
                try:
                    self.audio_frames.get_nowait()
                    self.audio_frames.put_nowait(audio_frame)
                except queue.Empty:
                    pass
    
    def _process_video_frames(self):
        """Обработка видео кадров в отдельном потоке."""
        while self.is_recording:
            try:
                frame_data = self.video_frames.get(timeout=1.0)
                frame = frame_data['frame']
                participant_id = frame_data['participant_id']
                
                # Создаем композитный кадр
                composite_frame = self._create_composite_frame(frame, participant_id)
                
                # Записываем кадр
                if self.video_writer and self.video_writer.isOpened():
                    self.video_writer.write(composite_frame)
                    self.frame_count += 1
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Ошибка обработки видео кадра: {e}")
                break
    
    def _process_audio_frames(self):
        """Обработка аудио кадров в отдельном потоке."""
        while self.is_recording:
            try:
                audio_frame = self.audio_frames.get(timeout=1.0)
                audio_data = audio_frame['data']
                participant_id = audio_frame['participant_id']
                
                # Обрабатываем аудио данные
                # Здесь должна быть реализация микширования аудио
                self.audio_sample_count += len(audio_data)
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Ошибка обработки аудио кадра: {e}")
                break
    
    def _create_composite_frame(self, frame: np.ndarray, participant_id: int) -> np.ndarray:
        """Создание композитного кадра из кадров участников."""
        if not CV2_AVAILABLE:
            logger.warning("OpenCV не установлен. Создание композитного кадра недоступно.")
            return np.zeros((self.height, self.width, 3), dtype=np.uint8)
            
        try:
            # Если это первый кадр, создаем базовый кадр
            if not hasattr(self, '_composite_frame'):
                self._composite_frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
                self._participant_frames = {}
            
            # Сохраняем кадр участника
            self._participant_frames[participant_id] = frame
            
            # Создаем сетку участников
            participants_list = list(self._participant_frames.keys())
            if not participants_list:
                return self._composite_frame
            
            # Вычисляем размеры ячеек сетки
            cols = min(3, len(participants_list))  # Максимум 3 колонки
            rows = (len(participants_list) + cols - 1) // cols
            
            cell_width = self.width // cols
            cell_height = self.height // rows
            
            # Очищаем композитный кадр
            self._composite_frame.fill(0)
            
            # Размещаем кадры участников
            for i, pid in enumerate(participants_list):
                if pid in self._participant_frames:
                    frame = self._participant_frames[pid]
                    
                    # Вычисляем позицию
                    row = i // cols
                    col = i % cols
                    
                    x = col * cell_width
                    y = row * cell_height
                    
                    # Изменяем размер кадра
                    resized_frame = cv2.resize(frame, (cell_width, cell_height))
                    
                    # Размещаем кадр
                    self._composite_frame[y:y+cell_height, x:x+cell_width] = resized_frame
                    
                    # Добавляем имя участника
                    participant_name = self.participants.get(pid, {}).get('user_name', f'User {pid}')
                    cv2.putText(
                        self._composite_frame,
                        participant_name,
                        (x + 10, y + 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (255, 255, 255),
                        2
                    )
            
            return self._composite_frame
            
        except Exception as e:
            logger.error(f"Ошибка создания композитного кадра: {e}")
            return np.zeros((self.height, self.width, 3), dtype=np.uint8)
    
    async     def _create_thumbnail(self) -> Optional[str]:
        """Создание превью записи."""
        if not CV2_AVAILABLE:
            logger.warning("OpenCV не установлен. Создание превью недоступно.")
            return None
            
        try:
            if not os.path.exists(self.file_path):
                return None
            
            # Открываем видео файл
            cap = cv2.VideoCapture(self.file_path)
            if not cap.isOpened():
                return None
            
            # Получаем кадр из середины видео
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            middle_frame = total_frames // 2
            
            cap.set(cv2.CAP_PROP_POS_FRAMES, middle_frame)
            ret, frame = cap.read()
            cap.release()
            
            if not ret:
                return None
            
            # Создаем превью
            thumbnail_path = self.file_path.replace('.mp4', '_thumb.jpg')
            thumbnail = cv2.resize(frame, (320, 180))
            cv2.imwrite(thumbnail_path, thumbnail)
            
            return thumbnail_path
            
        except Exception as e:
            logger.error(f"Ошибка создания превью: {e}")
            return None


class RecordingProcessor:
    """Процессор для обработки записей."""
    
    @staticmethod
    async def process_recording(recording_path: str) -> Dict:
        """Обработка записи после завершения."""
        try:
            # Получаем информацию о файле
            file_size = FileManager.get_file_size_mb(recording_path)
            duration = FileManager.get_recording_duration(recording_path)
            
            # Создаем превью
            thumbnail_path = await RecordingProcessor._create_thumbnail(recording_path)
            
            # Оптимизируем видео
            optimized_path = await RecordingProcessor._optimize_video(recording_path)
            
            return {
                'original_path': recording_path,
                'optimized_path': optimized_path,
                'file_size': file_size,
                'duration': duration,
                'thumbnail_path': thumbnail_path,
                'processed_at': datetime.now()
            }
            
        except Exception as e:
            logger.error(f"Ошибка обработки записи: {e}")
            raise
    
    @staticmethod
    async def _create_thumbnail(video_path: str) -> Optional[str]:
        """Создание превью видео."""
        if not CV2_AVAILABLE:
            logger.warning("OpenCV не установлен. Создание превью недоступно.")
            return None
            
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return None
            
            # Получаем кадр из середины
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            middle_frame = total_frames // 2
            
            cap.set(cv2.CAP_PROP_POS_FRAMES, middle_frame)
            ret, frame = cap.read()
            cap.release()
            
            if not ret:
                return None
            
            # Создаем превью
            thumbnail_path = video_path.replace('.mp4', '_thumb.jpg')
            thumbnail = cv2.resize(frame, (320, 180))
            cv2.imwrite(thumbnail_path, thumbnail)
            
            return thumbnail_path
            
        except Exception as e:
            logger.error(f"Ошибка создания превью: {e}")
            return None
    
    @staticmethod
    async def _optimize_video(video_path: str) -> str:
        """Оптимизация видео файла."""
        try:
            # Создаем оптимизированную версию
            optimized_path = video_path.replace('.mp4', '_optimized.mp4')
            
            # Используем FFmpeg для оптимизации
            import subprocess
            
            cmd = [
                'ffmpeg',
                '-i', video_path,
                '-c:v', 'libx264',
                '-crf', '23',
                '-c:a', 'aac',
                '-b:a', '128k',
                '-movflags', '+faststart',
                optimized_path,
                '-y'  # Перезаписывать файл
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                # Удаляем оригинальный файл
                os.remove(video_path)
                return optimized_path
            else:
                logger.error(f"Ошибка оптимизации видео: {result.stderr}")
                return video_path
                
        except Exception as e:
            logger.error(f"Ошибка оптимизации видео: {e}")
            return video_path


# Глобальный экземпляр менеджера записи
recording_manager = RecordingManager()
