# API Видеоконференций

## Обзор

Система видеоконференций предоставляет полный набор функций для проведения видеозвонков с поддержкой WebRTC, записи, шифрования и управления участниками.

## Основные возможности

### 🎥 Видеоконференции
- Создание и управление комнатами
- WebRTC для аудио/видео потоков
- Демонстрация экрана
- Управление качеством медиа

### 🔐 Безопасность
- Шифрование медиа данных
- Безопасный обмен ключами
- Токены сессий
- Валидация участников

### 📹 Запись
- Запись видеозвонков
- Создание превью
- Оптимизация видео
- Хранение записей

### 👥 Управление участниками
- Роли и права
- Модерация
- Приглашения
- Статусы участников

## API Endpoints

### Комнаты

#### Создание комнаты
```http
POST /video/rooms
```

**Тело запроса:**
```json
{
  "room_name": "Моя комната",
  "room_description": "Описание комнаты",
  "is_private": false,
  "max_participants": 50,
  "recording_enabled": true,
  "waiting_room_enabled": false
}
```

**Ответ:**
```json
{
  "room_id": 1,
  "room_name": "Моя комната",
  "room_code": "ABC12345",
  "room_url": "http://localhost:8000/video/room/ABC12345",
  "is_private": false,
  "max_participants": 50,
  "recording_enabled": true,
  "waiting_room_enabled": false,
  "created_at": "2024-01-01T12:00:00Z",
  "created_by": 1,
  "is_active": true
}
```

#### Получение списка комнат
```http
GET /video/rooms?limit=20&offset=0&is_private=false
```

#### Получение информации о комнате
```http
GET /video/rooms/{room_code}
```

#### Присоединение к комнате
```http
POST /video/rooms/{room_code}/join
```

#### Выход из комнаты
```http
DELETE /video/rooms/{room_code}/leave
```

### Участники

#### Получение списка участников
```http
GET /video/rooms/{room_code}/participants
```

**Ответ:**
```json
[
  {
    "participant_id": 1,
    "room_id": 1,
    "user_id": 1,
    "user_name": "Иван Иванов",
    "user_avatar": "avatar.jpg",
    "joined_at": "2024-01-01T12:00:00Z",
    "is_online": true,
    "is_muted": false,
    "is_video_enabled": true,
    "is_screen_sharing": false,
    "role": "host",
    "permissions": {
      "can_mute_others": true,
      "can_remove_others": true,
      "can_start_recording": true
    }
  }
]
```

### WebSocket соединение

#### Подключение к видеоконференции
```javascript
const ws = new WebSocket('ws://localhost:8000/video/ws/ABC12345/1');

// Отправка WebRTC offer
ws.send(JSON.stringify({
  type: 'offer',
  data: {
    sdp: '...',
    type: 'offer'
  }
}));

// Отправка ICE кандидата
ws.send(JSON.stringify({
  type: 'ice-candidate',
  data: {
    candidate: '...',
    sdpMid: '...',
    sdpMLineIndex: 0
  }
}));

// Управление аудио/видео
ws.send(JSON.stringify({
  type: 'mute-audio',
  data: { muted: true }
}));

ws.send(JSON.stringify({
  type: 'mute-video',
  data: { muted: false }
}));

// Демонстрация экрана
ws.send(JSON.stringify({
  type: 'start-screen-share'
}));

ws.send(JSON.stringify({
  type: 'stop-screen-share'
}));
```

## Схемы данных

### VideoRoom
```json
{
  "room_id": 1,
  "room_name": "Название комнаты",
  "room_description": "Описание",
  "room_code": "ABC12345",
  "room_url": "http://localhost:8000/video/room/ABC12345",
  "is_private": false,
  "max_participants": 50,
  "recording_enabled": true,
  "waiting_room_enabled": false,
  "created_at": "2024-01-01T12:00:00Z",
  "created_by": 1,
  "is_active": true
}
```

### VideoParticipant
```json
{
  "participant_id": 1,
  "room_id": 1,
  "user_id": 1,
  "joined_at": "2024-01-01T12:00:00Z",
  "is_online": true,
  "is_muted": false,
  "is_video_enabled": true,
  "is_screen_sharing": false,
  "role": "host",
  "permissions": {
    "can_mute_others": true,
    "can_remove_others": true,
    "can_start_recording": true
  }
}
```

### MediaStream
```json
{
  "stream_id": 1,
  "room_id": 1,
  "participant_id": 1,
  "stream_type": "video",
  "stream_id_webrtc": "stream_123",
  "is_active": true,
  "quality": "auto",
  "bitrate": 1500,
  "resolution": "720p"
}
```

## WebRTC интеграция

### Инициализация WebRTC
```javascript
// Создание RTCPeerConnection
const pc = new RTCPeerConnection({
  iceServers: [
    { urls: 'stun:stun.l.google.com:19302' }
  ]
});

// Получение медиа потока
const stream = await navigator.mediaDevices.getUserMedia({
  video: true,
  audio: true
});

// Добавление треков
stream.getTracks().forEach(track => {
  pc.addTrack(track, stream);
});

// Обработка входящих треков
pc.ontrack = (event) => {
  const [remoteStream] = event.streams;
  // Отображение удаленного видео
  document.getElementById('remoteVideo').srcObject = remoteStream;
};
```

### Обработка сигналов
```javascript
// Отправка offer
const offer = await pc.createOffer();
await pc.setLocalDescription(offer);

ws.send(JSON.stringify({
  type: 'offer',
  data: offer
}));

// Обработка answer
ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  
  if (message.type === 'answer') {
    await pc.setRemoteDescription(message.data);
  } else if (message.type === 'ice-candidate') {
    await pc.addIceCandidate(message.data);
  }
};
```

## Безопасность

### Шифрование
Все медиа данные шифруются с использованием AES-256-GCM. Ключи комнат генерируются автоматически и передаются участникам через зашифрованные каналы.

### Аутентификация
- Токены сессий для валидации участников
- Проверка прав доступа к комнатам
- Валидация WebRTC соединений

### Модерация
- Управление микрофонами и камерами
- Удаление участников
- Блокировка доступа

## Запись звонков

### Начало записи
```http
POST /video/rooms/{room_code}/recording/start
```

### Остановка записи
```http
POST /video/rooms/{room_code}/recording/stop
```

### Получение записей
```http
GET /video/recordings?room_id=1&limit=20
```

**Ответ:**
```json
[
  {
    "recording_id": 1,
    "room_id": 1,
    "started_by": 1,
    "started_at": "2024-01-01T12:00:00Z",
    "ended_at": "2024-01-01T13:00:00Z",
    "file_path": "/recordings/room_1/recording_20240101_120000.mp4",
    "file_size": 1024,
    "duration": 3600,
    "is_processing": false,
    "is_available": true,
    "thumbnail_path": "/recordings/room_1/recording_20240101_120000_thumb.jpg"
  }
]
```

## Уведомления

### WebSocket уведомления
```javascript
ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  
  switch (message.type) {
    case 'participant_joined':
      console.log('Участник присоединился:', message.data);
      break;
      
    case 'participant_left':
      console.log('Участник покинул:', message.data);
      break;
      
    case 'recording_started':
      console.log('Запись начата:', message.data);
      break;
      
    case 'recording_stopped':
      console.log('Запись остановлена:', message.data);
      break;
  }
};
```

## Обработка ошибок

### Коды ошибок
- `400` - Некорректные данные запроса
- `401` - Не авторизован
- `403` - Доступ запрещен
- `404` - Комната не найдена
- `409` - Конфликт (например, комната переполнена)
- `410` - Комната неактивна
- `500` - Внутренняя ошибка сервера

### Примеры ошибок
```json
{
  "detail": "Комната переполнена",
  "error_code": "ROOM_FULL",
  "max_participants": 50,
  "current_participants": 50
}
```

## Примеры использования

### Создание комнаты и присоединение
```javascript
// 1. Создание комнаты
const roomResponse = await fetch('/video/rooms', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer ' + token,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    room_name: 'Моя комната',
    max_participants: 10,
    recording_enabled: true
  })
});

const room = await roomResponse.json();
console.log('Комната создана:', room.room_code);

// 2. Присоединение к комнате
const joinResponse = await fetch(`/video/rooms/${room.room_code}/join`, {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer ' + token
  }
});

const participant = await joinResponse.json();
console.log('Присоединились как участник:', participant.participant_id);

// 3. WebSocket подключение
const ws = new WebSocket(`ws://localhost:8000/video/ws/${room.room_code}/${user_id}`);
```

### Полный пример клиента
```html
<!DOCTYPE html>
<html>
<head>
    <title>Видеоконференция</title>ж
</head>
<body>
    <video id="localVideo" autoplay muted></video>
    <video id="remoteVideo" autoplay></video>
    
    <button id="muteBtn">Заглушить</button>
    <button id="videoBtn">Выключить видео</button>
    <button id="screenBtn">Демонстрация экрана</button>
    
    <script>
        let pc, ws, localStream;
        
        async function init() {
            // Получение медиа потока
            localStream = await navigator.mediaDevices.getUserMedia({
                video: true,
                audio: true
            });
            
            document.getElementById('localVideo').srcObject = localStream;
            
            // Создание WebRTC соединения
            pc = new RTCPeerConnection({
                iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
            });
            
            // Добавление треков
            localStream.getTracks().forEach(track => {
                pc.addTrack(track, localStream);
            });
            
            // Обработка входящих треков
            pc.ontrack = (event) => {
                document.getElementById('remoteVideo').srcObject = event.streams[0];
            };
            
            // Обработка ICE кандидатов
            pc.onicecandidate = (event) => {
                if (event.candidate) {
                    ws.send(JSON.stringify({
                        type: 'ice-candidate',
                        data: event.candidate
                    }));
                }
            };
        }
        
        // WebSocket подключение
        function connectWebSocket(roomCode, userId) {
            ws = new WebSocket(`ws://localhost:8000/video/ws/${roomCode}/${userId}`);
            
            ws.onopen = () => {
                console.log('WebSocket подключен');
            };
            
            ws.onmessage = async (event) => {
                const message = JSON.parse(event.data);
                
                if (message.type === 'offer') {
                    await pc.setRemoteDescription(message.data);
                    const answer = await pc.createAnswer();
                    await pc.setLocalDescription(answer);
                    
                    ws.send(JSON.stringify({
                        type: 'answer',
                        data: answer
                    }));
                } else if (message.type === 'ice-candidate') {
                    await pc.addIceCandidate(message.data);
                }
            };
        }
        
        // Управление медиа
        document.getElementById('muteBtn').onclick = () => {
            const audioTrack = localStream.getAudioTracks()[0];
            audioTrack.enabled = !audioTrack.enabled;
        };
        
        document.getElementById('videoBtn').onclick = () => {
            const videoTrack = localStream.getVideoTracks()[0];
            videoTrack.enabled = !videoTrack.enabled;
        };
        
        document.getElementById('screenBtn').onclick = async () => {
            const screenStream = await navigator.mediaDevices.getDisplayMedia();
            const videoTrack = screenStream.getVideoTracks()[0];
            
            const sender = pc.getSenders().find(s => s.track && s.track.kind === 'video');
            if (sender) {
                sender.replaceTrack(videoTrack);
            }
        };
        
        // Инициализация
        init();
    </script>
</body>
</html>
```

## Настройка сервера

### Переменные окружения
```env
# WebRTC настройки
WEBRTC_STUN_SERVERS=stun:stun.l.google.com:19302
WEBRTC_TURN_SERVERS=turn:turn.server.com:3478

# Записи
RECORDINGS_DIR=./recordings
MAX_RECORDING_SIZE_MB=1024

# Шифрование
ENCRYPTION_SALT=your_salt_here
```

### Docker Compose
```yaml
version: '3.8'
services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/dbname
      - REDIS_URL=redis://redis:6379
    volumes:
      - ./recordings:/app/recordings
    depends_on:
      - db
      - redis
  
  db:
    image: postgres:15
    environment:
      - POSTGRES_DB=videoconf
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
    volumes:
      - postgres_data:/var/lib/postgresql/data
  
  redis:
    image: redis:7-alpine

volumes:
  postgres_data:
```

## Мониторинг и логирование

### Логи
- Создание/удаление комнат
- Присоединение/выход участников
- Начало/остановка записей
- Ошибки WebRTC
- Проблемы с шифрованием

### Метрики
- Количество активных комнат
- Количество участников
- Использование ресурсов
- Качество соединений

## Производительность

### Оптимизация
- Адаптивное качество видео
- Сжатие аудио
- Оптимизация записей
- Кэширование статики

### Масштабирование
- Горизонтальное масштабирование
- Балансировка нагрузки
- CDN для записей
- Кластеризация WebRTC
