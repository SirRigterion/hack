class VideoCallManager {
    constructor() {
        this.localStream = null;
        this.remoteStreams = new Map(); // user_id -> stream
        this.peerConnections = new Map(); // user_id -> RTCPeerConnection
        this.socket = null;
        this.roomCode = '';
        this.userId = '';
        this.userName = '';
        this.isMuted = false;
        this.isVideoEnabled = true;
        this.isScreenSharing = false;
        this.participants = new Map(); // user_id -> participant info
        
        // Настройки переподключения
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000; // 1 секунда
        this.connectionQuality = 'good'; // good, poor, bad
        this.lastHeartbeat = Date.now();
        this.heartbeatInterval = null;
        
        // Конфигурация ICE-серверов для лучшего NAT traversal
        this.iceConfig = {
            iceServers: [
                // Google STUN серверы
                { urls: 'stun:stun.l.google.com:19302' },
                { urls: 'stun:stun1.l.google.com:19302' },
                { urls: 'stun:stun2.l.google.com:19302' },
                { urls: 'stun:stun3.l.google.com:19302' },
                { urls: 'stun:stun4.l.google.com:19302' },
                
                // Дополнительные STUN серверы для лучшей совместимости
                { urls: 'stun:stun.ekiga.net' },
                { urls: 'stun:stun.ideasip.com' },
                { urls: 'stun:stun.schlund.de' },
                { urls: 'stun:stun.stunprotocol.org:3478' },
                { urls: 'stun:stun.voiparound.com' },
                { urls: 'stun:stun.voipbuster.com' },
                { urls: 'stun:stun.voipstunt.com' },
                { urls: 'stun:stun.counterpath.com' },
                { urls: 'stun:stun.1und1.de' },
                { urls: 'stun:stun.gmx.net' },
                { urls: 'stun:stun.callwithus.com' },
                { urls: 'stun:stun.counterpath.net' },
                { urls: 'stun:stun.internetcalls.com' }
            ],
            iceCandidatePoolSize: 10,
            bundlePolicy: 'max-bundle',
            rtcpMuxPolicy: 'require'
        };

        this.initializeElements();
        this.setupEventListeners();
    }

    getWebSocketHost() {
        // Если мы на localhost, используем localhost
        if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
            return window.location.host;
        }
        
        // Для других устройств используем IP адрес сервера
        // Можно настроить конкретный IP или использовать текущий хост
        return window.location.host;
    }

    initializeElements() {
        // Основные элементы
        this.videoContainer = document.getElementById('video-container');
        this.participantsList = document.getElementById('participants-list');
        this.chatContainer = document.getElementById('chat-container');
        this.chatMessages = document.getElementById('chat-messages');
        this.chatInput = document.getElementById('chat-input');
        this.sendChatBtn = document.getElementById('send-chat-btn');
        
        // Кнопки управления
        this.muteBtn = document.getElementById('mute-btn');
        this.videoBtn = document.getElementById('video-btn');
        this.screenShareBtn = document.getElementById('screen-share-btn');
        this.leaveBtn = document.getElementById('leave-btn');
        this.recordingBtn = document.getElementById('recording-btn');
        
        // Индикаторы
        this.connectionStatus = document.getElementById('connection-status');
        this.participantsCount = document.getElementById('participants-count');
        this.recordingIndicator = document.getElementById('recording-indicator');
        
        // Модальные окна
        this.settingsModal = document.getElementById('settings-modal');
        this.participantsModal = document.getElementById('participants-modal');
    }

    setupEventListeners() {
        // Кнопки управления медиа
        this.muteBtn?.addEventListener('click', () => this.toggleMute());
        this.videoBtn?.addEventListener('click', () => this.toggleVideo());
        this.screenShareBtn?.addEventListener('click', () => this.toggleScreenShare());
        this.leaveBtn?.addEventListener('click', () => this.leaveCall());
        this.recordingBtn?.addEventListener('click', () => this.toggleRecording());
        
        // Чат
        this.chatInput?.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.sendChatMessage();
        });
        this.sendChatBtn?.addEventListener('click', () => this.sendChatMessage());
        
        // Обработка закрытия страницы
        window.addEventListener('beforeunload', () => this.leaveCall());
        
        // Обработка изменения размера окна
        window.addEventListener('resize', () => this.adjustVideoLayout());
        
        // Двойной клик на статус соединения для показа статистики
        this.connectionStatus?.addEventListener('dblclick', () => {
            if (this.connectionStatsElement && !this.connectionStatsElement.classList.contains('hidden')) {
                this.hideConnectionStats();
            } else {
                this.showConnectionStats();
            }
        });
        
        // Горячие клавиши
        document.addEventListener('keydown', (e) => {
            // Ctrl+Shift+S для показа статистики
            if (e.ctrlKey && e.shiftKey && e.key === 'S') {
                e.preventDefault();
                this.showConnectionStats();
            }
            // Escape для скрытия статистики
            if (e.key === 'Escape') {
                this.hideConnectionStats();
            }
        });
    }

    async initializeCall(roomCode, userName) {
        try {
            this.roomCode = roomCode;
            this.userName = userName;
            this.userId = `user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
            
            this.updateConnectionStatus('Подключение...', 'orange');
            
            // Получаем доступ к медиаустройствам
            await this.initializeMedia();
            
            // Добавляем себя в список участников СНАЧАЛА
            this.addParticipant(this.userId, this.userName, true);
            
            // Подключаемся к WebSocket
            await this.connectWebSocket();
            
            this.updateConnectionStatus('Подключено', 'green');
            
        } catch (error) {
            console.error('Ошибка инициализации звонка:', error);
            this.updateConnectionStatus('Ошибка подключения', 'red');
            this.showError('Не удалось подключиться к звонку');
        }
    }

    async initializeMedia() {
        try {
            // Проверяем поддержку getUserMedia
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                throw new Error('Ваш браузер не поддерживает видеозвонки');
            }

            // Определяем оптимальные настройки для устройства
            const deviceCapabilities = await this.getDeviceCapabilities();
            
            // Запрашиваем доступ к камере и микрофону с адаптивными настройками
            this.localStream = await navigator.mediaDevices.getUserMedia({
                video: {
                    width: { ideal: deviceCapabilities.videoWidth, max: 1920 },
                    height: { ideal: deviceCapabilities.videoHeight, max: 1080 },
                    frameRate: { ideal: deviceCapabilities.frameRate, max: 60 },
                    facingMode: 'user', // Фронтальная камера по умолчанию
                    aspectRatio: 16/9
                },
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                    sampleRate: 48000,
                    channelCount: 2
                }
            });
            
            console.log('Локальный поток получен:', this.localStream);
            
            // Настраиваем треки для лучшего качества
            this.configureMediaTracks();
            
            // Отображаем локальный поток
            this.addVideoElement(this.userId, this.localStream, this.userName + ' (Вы)', true);
            
            console.log('Медиаустройства инициализированы');
            
        } catch (error) {
            console.error('Ошибка доступа к медиаустройствам:', error);
            
            // Пробуем с более простыми настройками
            try {
                console.log('Попытка с упрощенными настройками...');
                this.localStream = await navigator.mediaDevices.getUserMedia({
                    video: true,
                    audio: true
                });
                
                this.addVideoElement(this.userId, this.localStream, this.userName + ' (Вы)', true);
                console.log('Медиаустройства инициализированы с упрощенными настройками');
                
            } catch (fallbackError) {
                console.error('Ошибка с упрощенными настройками:', fallbackError);
                throw new Error('Не удалось получить доступ к камере и микрофону. Проверьте разрешения браузера.');
            }
        }
    }

    async getDeviceCapabilities() {
        try {
            // Получаем информацию об устройствах
            const devices = await navigator.mediaDevices.enumerateDevices();
            const videoDevices = devices.filter(device => device.kind === 'videoinput');
            
            // Определяем базовые возможности
            let videoWidth = 1280;
            let videoHeight = 720;
            let frameRate = 30;
            
            // Проверяем, мобильное ли устройство
            const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
            
            if (isMobile) {
                videoWidth = 640;
                videoHeight = 480;
                frameRate = 24;
            }
            
            return {
                videoWidth,
                videoHeight,
                frameRate,
                isMobile,
                hasMultipleCameras: videoDevices.length > 1
            };
            
        } catch (error) {
            console.error('Ошибка определения возможностей устройства:', error);
            return {
                videoWidth: 1280,
                videoHeight: 720,
                frameRate: 30,
                isMobile: false,
                hasMultipleCameras: false
            };
        }
    }

    configureMediaTracks() {
        if (!this.localStream) return;

        // Настраиваем аудио треки
        const audioTracks = this.localStream.getAudioTracks();
        audioTracks.forEach(track => {
            const settings = track.getSettings();
            console.log('Аудио трек настроен:', settings);
        });

        // Настраиваем видео треки
        const videoTracks = this.localStream.getVideoTracks();
        videoTracks.forEach(track => {
            const settings = track.getSettings();
            console.log('Видео трек настроен:', settings);
            
            // Добавляем обработчик изменения настроек
            track.addEventListener('ended', () => {
                console.log('Видео трек завершен');
                this.handleTrackEnded('video');
            });
        });
    }

    handleTrackEnded(trackKind) {
        console.log(`Трек ${trackKind} завершен, попытка восстановления...`);
        
        // Уведомляем других участников
        this.sendMessage({
            type: 'media_stream_event',
            event_type: 'stream_ended',
            stream_type: trackKind,
            user_id: this.userId
        });
        
        // Пытаемся восстановить трек
        this.restoreMediaTrack(trackKind);
    }

    async restoreMediaTrack(trackKind) {
        try {
            if (trackKind === 'video') {
                const newStream = await navigator.mediaDevices.getUserMedia({
                    video: true,
                    audio: false
                });
                
                const newVideoTrack = newStream.getVideoTracks()[0];
                const oldVideoTrack = this.localStream.getVideoTracks()[0];
                
                if (oldVideoTrack) {
                    this.localStream.removeTrack(oldVideoTrack);
                }
                
                this.localStream.addTrack(newVideoTrack);
                
                // Обновляем все peer connections
                this.peerConnections.forEach((peerConnection, userId) => {
                    const sender = peerConnection.getSenders().find(s => 
                        s.track && s.track.kind === 'video'
                    );
                    if (sender) {
                        sender.replaceTrack(newVideoTrack);
                    }
                });
                
                // Обновляем локальное видео
                const localVideo = document.getElementById(`video-${this.userId}`);
                if (localVideo) {
                    localVideo.srcObject = this.localStream;
                }
                
                console.log('Видео трек восстановлен');
            }
        } catch (error) {
            console.error(`Ошибка восстановления ${trackKind} трека:`, error);
        }
    }

    connectWebSocket() {
        return new Promise((resolve, reject) => {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const host = this.getWebSocketHost();
            const wsUrl = `${protocol}//${host}/video/websocket/${this.roomCode}?user_id=${this.userId}`;
            
            console.log('Подключение к WebSocket:', wsUrl);
            this.socket = new WebSocket(wsUrl);
            
            this.socket.onopen = () => {
                console.log('WebSocket подключен');
                this.reconnectAttempts = 0; // Сбрасываем счетчик попыток
                this.updateConnectionStatus('Подключено', 'green');
                
                // Запускаем heartbeat для мониторинга соединения
                this.startHeartbeat();
                
                // Отправляем информацию о пользователе
                this.sendMessage({
                    type: 'user_info',
                    user_id: this.userId,
                    user_name: this.userName
                });
                
                // Запрашиваем список участников
                this.sendMessage({ type: 'get_participants' });
                
                resolve();
            };
            
            this.socket.onmessage = (event) => {
                try {
                    const message = JSON.parse(event.data);
                    this.handleWebSocketMessage(message);
                    
                    // Обновляем время последнего heartbeat
                    if (message.type === 'pong') {
                        this.lastHeartbeat = Date.now();
                    }
                } catch (error) {
                    console.error('Ошибка парсинга сообщения:', error);
                }
            };
            
            this.socket.onclose = (event) => {
                console.log('WebSocket отключен:', event.code, event.reason);
                this.stopHeartbeat();
                this.updateConnectionStatus('Отключено', 'red');
                
                // Автоматическое переподключение
                if (this.reconnectAttempts < this.maxReconnectAttempts) {
                    this.attemptReconnect();
                } else {
                    this.showError('Не удалось восстановить соединение. Попробуйте обновить страницу.');
                }
            };
            
            this.socket.onerror = (error) => {
                console.error('Ошибка WebSocket:', error);
                this.updateConnectionStatus('Ошибка соединения', 'red');
                reject(error);
            };
        });
    }

    handleWebSocketMessage(message) {
        console.log('Получено сообщение:', message.type);
        
        switch (message.type) {
            case 'user_joined':
                this.handleUserJoined(message);
                break;
            case 'user_left':
                this.handleUserLeft(message);
                break;
            case 'webrtc_signal':
                this.handleWebRTCSignal(message);
                break;
            case 'chat_message':
                this.handleChatMessage(message);
                break;
            case 'participants_list':
                this.handleParticipantsList(message);
                break;
            case 'user_action':
                this.handleUserAction(message);
                break;
            case 'recording_status':
                this.handleRecordingStatus(message);
                break;
            case 'room_stats':
                this.handleRoomStats(message);
                break;
            case 'error':
                this.showError(message.message);
                break;
        }
    }

    handleUserJoined(message) {
        const { user_id, user_name } = message;
        
        if (user_id !== this.userId) {
            console.log(`Новый участник присоединился: ${user_name} (${user_id})`);
            this.addParticipant(user_id, user_name, false);
            
            // Создаем peer connection для нового участника
            this.createPeerConnection(user_id);
            
            this.showNotification(`${user_name} присоединился к звонку`);
        }
    }

    handleUserLeft(message) {
        const { user_id, user_name } = message;
        
        this.removeParticipant(user_id);
        this.closePeerConnection(user_id);
        this.showNotification(`${user_name} покинул звонок`);
    }

    handleWebRTCSignal(message) {
        const { signal_type, data, sender_user_id } = message;
        
        if (sender_user_id === this.userId) return;
        
        console.log(`Получен WebRTC сигнал: ${signal_type} от ${sender_user_id}`);
        
        switch (signal_type) {
            case 'offer':
                this.handleOffer(data, sender_user_id);
                break;
            case 'answer':
                this.handleAnswer(data, sender_user_id);
                break;
            case 'ice_candidate':
                this.handleIceCandidate(data, sender_user_id);
                break;
        }
    }

    async createPeerConnection(userId) {
        try {
            console.log(`Создание peer connection для ${userId}`);
            
            const peerConnection = new RTCPeerConnection(this.iceConfig);
            
            // Добавляем локальные треки с адаптивным качеством
            if (this.localStream) {
                this.localStream.getTracks().forEach(track => {
                    if (track.kind === 'video') {
                        // Настраиваем качество видео в зависимости от соединения
                        this.configureVideoTrack(track);
                    }
                    peerConnection.addTrack(track, this.localStream);
                    console.log(`Добавлен трек: ${track.kind}`);
                });
            }
            
            // Обрабатываем удаленные треки
            peerConnection.ontrack = (event) => {
                console.log(`Получен удаленный трек от ${userId}:`, event.streams);
                const [remoteStream] = event.streams;
                this.remoteStreams.set(userId, remoteStream);
                this.updateParticipantVideo(userId, remoteStream);
            };
            
            // Собираем ICE кандидаты
            peerConnection.onicecandidate = (event) => {
                if (event.candidate) {
                    console.log(`Отправка ICE candidate для ${userId}`);
                    this.sendWebRTCSignal('ice_candidate', event.candidate, userId);
                }
            };
            
            // Отслеживаем состояние соединения
            peerConnection.onconnectionstatechange = () => {
                console.log(`Соединение с ${userId}:`, peerConnection.connectionState);
                this.updateParticipantConnectionStatus(userId, peerConnection.connectionState);
                
                // Обрабатываем проблемы соединения
                if (peerConnection.connectionState === 'failed') {
                    console.log(`Соединение с ${userId} не удалось, попытка переподключения`);
                    this.reconnectPeerConnection(userId);
                }
            };
            
            // Мониторинг качества соединения
            peerConnection.oniceconnectionstatechange = () => {
                console.log(`ICE соединение с ${userId}:`, peerConnection.iceConnectionState);
                this.updateConnectionQuality(userId, peerConnection.iceConnectionState);
            };
            
            this.peerConnections.set(userId, peerConnection);
            
            // Создаем offer для нового участника
            console.log(`Создание offer для ${userId}`);
            const offer = await peerConnection.createOffer({
                offerToReceiveAudio: true,
                offerToReceiveVideo: true
            });
            await peerConnection.setLocalDescription(offer);
            this.sendWebRTCSignal('offer', offer, userId);
            
        } catch (error) {
            console.error('Ошибка создания peer connection:', error);
            this.showError(`Не удалось подключиться к ${userId}`);
        }
    }

    async handleOffer(offer, userId) {
        try {
            console.log(`Обработка offer от ${userId}`);
            
            let peerConnection = this.peerConnections.get(userId);
            
            if (!peerConnection) {
                console.log(`Создание нового peer connection для ${userId}`);
                peerConnection = new RTCPeerConnection(this.iceConfig);
                this.setupPeerConnection(peerConnection, userId);
                this.peerConnections.set(userId, peerConnection);
            }
            
            await peerConnection.setRemoteDescription(new RTCSessionDescription(offer));
            const answer = await peerConnection.createAnswer();
            await peerConnection.setLocalDescription(answer);
            
            console.log(`Отправка answer для ${userId}`);
            this.sendWebRTCSignal('answer', answer, userId);
            
        } catch (error) {
            console.error('Ошибка обработки offer:', error);
        }
    }

    async handleAnswer(answer, userId) {
        try {
            const peerConnection = this.peerConnections.get(userId);
            if (peerConnection) {
                await peerConnection.setRemoteDescription(new RTCSessionDescription(answer));
            }
        } catch (error) {
            console.error('Ошибка обработки answer:', error);
        }
    }

    async handleIceCandidate(candidate, userId) {
        try {
            const peerConnection = this.peerConnections.get(userId);
            if (peerConnection) {
                await peerConnection.addIceCandidate(new RTCIceCandidate(candidate));
            }
        } catch (error) {
            console.error('Ошибка обработки ICE candidate:', error);
        }
    }

    setupPeerConnection(peerConnection, userId) {
        // Добавляем локальные треки
        if (this.localStream) {
            this.localStream.getTracks().forEach(track => {
                peerConnection.addTrack(track, this.localStream);
            });
        }
        
        // Обрабатываем удаленные треки
        peerConnection.ontrack = (event) => {
            const [remoteStream] = event.streams;
            this.remoteStreams.set(userId, remoteStream);
            this.updateParticipantVideo(userId, remoteStream);
        };
        
        // Собираем ICE кандидаты
        peerConnection.onicecandidate = (event) => {
            if (event.candidate) {
                this.sendWebRTCSignal('ice_candidate', event.candidate, userId);
            }
        };
        
        // Отслеживаем состояние соединения
        peerConnection.onconnectionstatechange = () => {
            console.log(`Соединение с ${userId}:`, peerConnection.connectionState);
            this.updateParticipantConnectionStatus(userId, peerConnection.connectionState);
        };
    }

    sendWebRTCSignal(signalType, data, targetUserId) {
        this.sendMessage({
            type: 'webrtc_signal',
            signal_type: signalType,
            data: data,
            target_user_id: targetUserId,
            sender_user_id: this.userId
        });
    }

    sendMessage(message) {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify(message));
        }
    }

    // Методы для мониторинга соединения
    startHeartbeat() {
        this.heartbeatInterval = setInterval(() => {
            if (this.socket && this.socket.readyState === WebSocket.OPEN) {
                this.sendMessage({ type: 'ping' });
                
                // Проверяем качество соединения
                this.checkConnectionQuality();
            }
        }, 30000); // Ping каждые 30 секунд
    }

    stopHeartbeat() {
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
            this.heartbeatInterval = null;
        }
    }

    checkConnectionQuality() {
        const timeSinceLastHeartbeat = Date.now() - this.lastHeartbeat;
        
        if (timeSinceLastHeartbeat > 60000) { // Более 1 минуты без ответа
            this.connectionQuality = 'bad';
            this.updateConnectionStatus('Плохое соединение', 'orange');
            this.showQualityWarning('Критически плохое соединение!', true);
        } else if (timeSinceLastHeartbeat > 30000) { // Более 30 секунд
            this.connectionQuality = 'poor';
            this.updateConnectionStatus('Слабое соединение', 'yellow');
            this.showQualityWarning('Слабое соединение');
        } else {
            this.connectionQuality = 'good';
            this.updateConnectionStatus('Подключено', 'green');
        }
        
        // Адаптируем качество видео в зависимости от соединения
        this.adaptVideoQuality();
    }

    async attemptReconnect() {
        this.reconnectAttempts++;
        const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1); // Экспоненциальная задержка
        
        console.log(`Попытка переподключения ${this.reconnectAttempts}/${this.maxReconnectAttempts} через ${delay}ms`);
        this.updateConnectionStatus(`Переподключение... (${this.reconnectAttempts}/${this.maxReconnectAttempts})`, 'orange');
        
        // Показываем overlay переподключения
        this.showReconnectingOverlay();
        
        // Показываем предупреждение о качестве
        if (this.reconnectAttempts > 2) {
            this.showQualityWarning('Проблемы с соединением. Попытка восстановления...', true);
        }
        
        setTimeout(async () => {
            try {
                await this.connectWebSocket();
                console.log('Переподключение успешно');
                this.hideReconnectingOverlay();
                this.showNotification('Соединение восстановлено');
            } catch (error) {
                console.error('Ошибка переподключения:', error);
                if (this.reconnectAttempts >= this.maxReconnectAttempts) {
                    this.hideReconnectingOverlay();
                    this.showError('Не удалось восстановить соединение. Попробуйте обновить страницу.');
                }
            }
        }, delay);
    }

    // Методы для адаптивного качества видео
    configureVideoTrack(track) {
        const constraints = track.getConstraints();
        
        // Адаптируем качество в зависимости от соединения
        if (this.connectionQuality === 'poor' || this.connectionQuality === 'bad') {
            track.applyConstraints({
                width: { ideal: 640, max: 1280 },
                height: { ideal: 480, max: 720 },
                frameRate: { ideal: 15, max: 30 }
            });
        } else {
            track.applyConstraints({
                width: { ideal: 1280, max: 1920 },
                height: { ideal: 720, max: 1080 },
                frameRate: { ideal: 30, max: 60 }
            });
        }
    }

    updateConnectionQuality(userId, iceConnectionState) {
        const participant = this.participants.get(userId);
        if (!participant) return;

        switch (iceConnectionState) {
            case 'connected':
            case 'completed':
                participant.connectionQuality = 'good';
                break;
            case 'checking':
                participant.connectionQuality = 'connecting';
                break;
            case 'disconnected':
                participant.connectionQuality = 'poor';
                break;
            case 'failed':
            case 'closed':
                participant.connectionQuality = 'bad';
                break;
        }

        this.updateParticipantsList();
    }

    async reconnectPeerConnection(userId) {
        try {
            console.log(`Переподключение peer connection для ${userId}`);
            
            // Закрываем старое соединение
            const oldConnection = this.peerConnections.get(userId);
            if (oldConnection) {
                oldConnection.close();
                this.peerConnections.delete(userId);
            }
            
            // Создаем новое соединение
            await this.createPeerConnection(userId);
            
        } catch (error) {
            console.error(`Ошибка переподключения peer connection для ${userId}:`, error);
        }
    }

    // Адаптивное качество в зависимости от пропускной способности
    async adaptVideoQuality() {
        if (!this.localStream) return;

        const videoTrack = this.localStream.getVideoTracks()[0];
        if (!videoTrack) return;

        // Получаем статистику соединения
        const stats = await this.getConnectionStats();
        
        if (stats && stats.bitrate) {
            if (stats.bitrate < 500000) { // Менее 500 кбит/с
                this.configureVideoTrack(videoTrack);
                this.connectionQuality = 'poor';
            } else if (stats.bitrate < 1000000) { // Менее 1 Мбит/с
                this.connectionQuality = 'good';
            } else {
                this.connectionQuality = 'excellent';
            }
        }
    }

    async getConnectionStats() {
        try {
            const stats = {};
            
            for (const [userId, peerConnection] of this.peerConnections) {
                const connectionStats = await peerConnection.getStats();
                let bitrate = 0;
                
                connectionStats.forEach(report => {
                    if (report.type === 'outbound-rtp' && report.mediaType === 'video') {
                        bitrate += report.bytesSent * 8; // Конвертируем в биты
                    }
                });
                
                stats[userId] = { bitrate };
            }
            
            return stats;
        } catch (error) {
            console.error('Ошибка получения статистики соединения:', error);
            return null;
        }
    }

    // Управление медиа
    async toggleMute() {
        if (this.localStream) {
            const audioTrack = this.localStream.getAudioTracks()[0];
            if (audioTrack) {
                audioTrack.enabled = !audioTrack.enabled;
                this.isMuted = !audioTrack.enabled;
                this.updateMuteButton();
                
                // Уведомляем других участников
                this.sendMessage({
                    type: 'user_action',
                    user_id: this.userId,
                    action: this.isMuted ? 'mute' : 'unmute'
                });
            }
        }
    }

    async toggleVideo() {
        if (this.localStream) {
            const videoTrack = this.localStream.getVideoTracks()[0];
            if (videoTrack) {
                videoTrack.enabled = !videoTrack.enabled;
                this.isVideoEnabled = videoTrack.enabled;
                this.updateVideoButton();
                
                // Обновляем локальное видео
                const localVideo = document.getElementById(`video-${this.userId}`);
                if (localVideo) {
                    localVideo.style.display = this.isVideoEnabled ? 'block' : 'none';
                }
                
                // Уведомляем других участников
                this.sendMessage({
                    type: 'user_action',
                    user_id: this.userId,
                    action: this.isVideoEnabled ? 'video_on' : 'video_off'
                });
            }
        }
    }

    async toggleScreenShare() {
        try {
            if (this.isScreenSharing) {
                // Останавливаем демонстрацию экрана
                await this.stopScreenShare();
            } else {
                // Начинаем демонстрацию экрана
                await this.startScreenShare();
            }
        } catch (error) {
            console.error('Ошибка демонстрации экрана:', error);
            this.showError('Не удалось начать демонстрацию экрана');
        }
    }

    async startScreenShare() {
        try {
            const screenStream = await navigator.mediaDevices.getDisplayMedia({
                video: true,
                audio: true
            });
            
            // Заменяем видео трек во всех peer connections
            const videoTrack = screenStream.getVideoTracks()[0];
            
            this.peerConnections.forEach((peerConnection, userId) => {
                const sender = peerConnection.getSenders().find(s => 
                    s.track && s.track.kind === 'video'
                );
                if (sender) {
                    sender.replaceTrack(videoTrack);
                }
            });
            
                // Обновляем локальное видео
                const localVideo = document.getElementById(`video-${this.userId}`);
                if (localVideo) {
                    localVideo.srcObject = screenStream;
                }
            
            this.isScreenSharing = true;
            this.updateScreenShareButton();
            
            // Обрабатываем окончание демонстрации экрана
            videoTrack.onended = () => {
                this.stopScreenShare();
            };
            
            this.showNotification('Демонстрация экрана начата');
            
        } catch (error) {
            console.error('Ошибка начала демонстрации экрана:', error);
            throw error;
        }
    }

    async stopScreenShare() {
        try {
            // Возвращаем обычную камеру
            if (this.localStream) {
                const videoTrack = this.localStream.getVideoTracks()[0];
                
                this.peerConnections.forEach((peerConnection, userId) => {
                    const sender = peerConnection.getSenders().find(s => 
                        s.track && s.track.kind === 'video'
                    );
                    if (sender && videoTrack) {
                        sender.replaceTrack(videoTrack);
                    }
                });
                
                // Обновляем локальное видео
                const localVideo = document.getElementById(`video-${this.userId}`);
                if (localVideo) {
                    localVideo.srcObject = this.localStream;
                }
            }
            
            this.isScreenSharing = false;
            this.updateScreenShareButton();
            
            this.showNotification('Демонстрация экрана остановлена');
            
        } catch (error) {
            console.error('Ошибка остановки демонстрации экрана:', error);
        }
    }

    // Управление участниками
    addParticipant(userId, userName, isLocal = false) {
        const participant = {
            id: userId,
            name: userName,
            isLocal: isLocal,
            isMuted: false,
            isVideoEnabled: true,
            isScreenSharing: false,
            connectionState: 'connecting'
        };
        
        this.participants.set(userId, participant);
        this.updateParticipantsList();
        this.updateParticipantsCount();
    }

    removeParticipant(userId) {
        this.participants.delete(userId);
        this.remoteStreams.delete(userId);
        this.removeVideoElement(userId);
        this.updateParticipantsList();
        this.updateParticipantsCount();
    }

    removeVideoElement(userId) {
        const element = document.getElementById(`video-${userId}`);
        if (element) {
            element.parentElement.remove();
        }
    }

    updateParticipantVideo(userId, stream) {
        const participant = this.participants.get(userId);
        if (participant) {
            console.log(`Обновление видео для ${participant.name} (${userId})`);
            this.addVideoElement(userId, stream, participant.name, false);
        }
    }

    addVideoElement(userId, stream, name, isLocal) {
        const container = document.getElementById('video-container');
        
        // Удаляем существующий элемент
        const existing = document.getElementById(`video-${userId}`);
        if (existing) {
            existing.parentElement.remove();
        }

        const wrapper = document.createElement('div');
        wrapper.className = 'video-wrapper';
        wrapper.id = `wrapper-${userId}`;
        if (isLocal) {
            wrapper.style.border = '3px solid #4CAF50';
        }

        const video = document.createElement('video');
        video.id = `video-${userId}`;
        video.className = 'participant-video';
        video.srcObject = stream;
        video.autoplay = true;
        video.muted = true;
        video.playsInline = true;

        const label = document.createElement('div');
        label.className = 'video-label';
        label.textContent = name;

        wrapper.appendChild(video);
        wrapper.appendChild(label);
        container.appendChild(wrapper);

        console.log(`Добавлено видео для ${name} (${userId})`);
        
        // Обновляем раскладку видео
        this.adjustVideoLayout();
    }


    updateParticipantsList() {
        if (!this.participantsList) return;
        
        this.participantsList.innerHTML = '';
        
        this.participants.forEach((participant, userId) => {
            const item = document.createElement('div');
            item.className = 'participant-item';
            
            // Определяем иконку качества соединения
            const qualityIcon = this.getConnectionQualityIcon(participant.connectionQuality || 'good');
            
            item.innerHTML = `
                <div class="participant-info">
                    <span class="participant-name">${participant.name}</span>
                    <span class="participant-status ${participant.connectionState}"></span>
                    <span class="participant-connection-quality ${participant.connectionQuality || 'good'}"></span>
                </div>
                <div class="participant-controls">
                    <span class="mute-indicator ${participant.isMuted ? 'muted' : ''}">🎤</span>
                    <span class="video-indicator ${participant.isVideoEnabled ? '' : 'disabled'}">📹</span>
                    <span class="quality-indicator">${qualityIcon}</span>
                </div>
            `;
            this.participantsList.appendChild(item);
        });
    }

    getConnectionQualityIcon(quality) {
        switch (quality) {
            case 'excellent': return '🟢';
            case 'good': return '🔵';
            case 'poor': return '🟡';
            case 'bad': return '🔴';
            case 'connecting': return '🟣';
            default: return '⚪';
        }
    }

    updateParticipantsCount() {
        if (this.participantsCount) {
            this.participantsCount.textContent = this.participants.size;
        }
    }

    // Чат
    sendChatMessage() {
        const message = this.chatInput?.value.trim();
        if (!message) return;
        
        this.sendMessage({
            type: 'chat_message',
            user_id: this.userId,
            username: this.userName,
            content: message
        });
        
        this.chatInput.value = '';
    }

    handleChatMessage(message) {
        if (!this.chatMessages) return;
        
        const messageElement = document.createElement('div');
        messageElement.className = 'chat-message';
        messageElement.innerHTML = `
            <div class="message-header">
                <span class="username">${message.username}</span>
                <span class="timestamp">${new Date().toLocaleTimeString()}</span>
            </div>
            <div class="message-content">${message.content}</div>
        `;
        
        this.chatMessages.appendChild(messageElement);
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }

    // Управление записью
    async toggleRecording() {
        try {
            const action = this.isRecording ? 'stop' : 'start';
            
            this.sendMessage({
                type: 'recording_control',
                action: action,
                user_id: this.userId
            });
            
        } catch (error) {
            console.error('Ошибка управления записью:', error);
            this.showError('Ошибка управления записью');
        }
    }

    handleRecordingStatus(message) {
        this.isRecording = message.is_recording;
        this.updateRecordingButton();
        
        if (this.recordingIndicator) {
            this.recordingIndicator.style.display = message.is_recording ? 'block' : 'none';
        }
    }

    // Выход из звонка
    leaveCall() {
        console.log('Выход из звонка...');
        
        // Останавливаем heartbeat
        this.stopHeartbeat();
        
        // Скрываем все UI элементы
        this.hideConnectionStats();
        this.hideReconnectingOverlay();
        
        // Закрываем все peer connections
        this.peerConnections.forEach((peerConnection, userId) => {
            try {
                peerConnection.close();
            } catch (error) {
                console.error(`Ошибка закрытия peer connection для ${userId}:`, error);
            }
        });
        this.peerConnections.clear();
        
        // Останавливаем локальный поток
        if (this.localStream) {
            this.localStream.getTracks().forEach(track => {
                try {
                    track.stop();
                } catch (error) {
                    console.error('Ошибка остановки трека:', error);
                }
            });
        }
        
        // Закрываем WebSocket
        if (this.socket) {
            try {
                this.socket.close(1000, 'User leaving call');
            } catch (error) {
                console.error('Ошибка закрытия WebSocket:', error);
            }
        }
        
        // Очищаем контейнер видео
        if (this.videoContainer) {
            this.videoContainer.innerHTML = '';
        }
        
        // Очищаем данные
        this.participants.clear();
        this.remoteStreams.clear();
        
        // Сбрасываем состояние
        this.reconnectAttempts = 0;
        this.connectionQuality = 'good';
        
        // Очищаем UI элементы
        this.connectionStatsElement = null;
        this.reconnectingOverlay = null;
        this.statsUpdateInterval = null;
        
        console.log('Выход из звонка завершен');
        
        // Возвращаемся на главную страницу
        window.location.href = '/';
    }

    // Обновление UI
    updateMuteButton() {
        if (this.muteBtn) {
            this.muteBtn.textContent = this.isMuted ? '🔇' : '🎤';
            this.muteBtn.className = this.isMuted ? 'control-btn muted' : 'control-btn';
        }
    }

    updateVideoButton() {
        if (this.videoBtn) {
            this.videoBtn.textContent = this.isVideoEnabled ? '📹' : '📹❌';
            this.videoBtn.className = this.isVideoEnabled ? 'control-btn' : 'control-btn disabled';
        }
    }

    updateScreenShareButton() {
        if (this.screenShareBtn) {
            this.screenShareBtn.textContent = this.isScreenSharing ? '🖥️❌' : '🖥️';
            this.screenShareBtn.className = this.isScreenSharing ? 'control-btn active' : 'control-btn';
        }
    }

    updateRecordingButton() {
        if (this.recordingBtn) {
            this.recordingBtn.textContent = this.isRecording ? '⏹️' : '⏺️';
            this.recordingBtn.className = this.isRecording ? 'control-btn recording' : 'control-btn';
        }
    }

    updateConnectionStatus(status, color) {
        if (this.connectionStatus) {
            this.connectionStatus.textContent = status;
            this.connectionStatus.style.color = color;
        }
    }

    updateParticipantConnectionStatus(userId, state) {
        const participant = this.participants.get(userId);
        if (participant) {
            participant.connectionState = state;
            this.updateParticipantsList();
        }
    }

    adjustVideoLayout() {
        // Адаптивная раскладка видео в зависимости от количества участников
        const videoContainer = document.getElementById('video-container');
        if (!videoContainer) return;
        
        const participantCount = this.participants.size;
        
        if (participantCount <= 2) {
            videoContainer.className = 'video-container grid-2';
        } else if (participantCount <= 4) {
            videoContainer.className = 'video-container grid-4';
        } else {
            videoContainer.className = 'video-container grid-many';
        }
    }

    // Уведомления и ошибки
    showNotification(message) {
        // Создаем уведомление
        const notification = document.createElement('div');
        notification.className = 'notification';
        notification.textContent = message;
        
        document.body.appendChild(notification);
        
        // Удаляем через 3 секунды
        setTimeout(() => {
            notification.remove();
        }, 3000);
    }

    showError(message) {
        // Создаем модальное окно с ошибкой
        const modal = document.createElement('div');
        modal.className = 'error-modal';
        modal.innerHTML = `
            <div class="modal-content">
                <h3>Ошибка</h3>
                <p>${message}</p>
                <button onclick="this.parentElement.parentElement.remove()">Закрыть</button>
            </div>
        `;
        
        document.body.appendChild(modal);
    }

    // Методы для отображения статистики и предупреждений
    showConnectionStats() {
        if (this.connectionStatsElement) {
            this.connectionStatsElement.classList.remove('hidden');
            return;
        }

        const statsElement = document.createElement('div');
        statsElement.className = 'connection-stats';
        statsElement.innerHTML = `
            <h4>📊 Статистика соединения</h4>
            <div class="stat-item">
                <span class="stat-label">Качество:</span>
                <span class="stat-value" id="overall-quality">${this.connectionQuality}</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">Участников:</span>
                <span class="stat-value" id="participants-count">${this.participants.size}</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">Соединений:</span>
                <span class="stat-value" id="connections-count">${this.peerConnections.size}</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">Попыток переподключения:</span>
                <span class="stat-value" id="reconnect-attempts">${this.reconnectAttempts}</span>
            </div>
        `;

        // Добавляем кнопку закрытия
        const closeBtn = document.createElement('button');
        closeBtn.textContent = '✕';
        closeBtn.style.cssText = `
            position: absolute;
            top: 5px;
            right: 5px;
            background: none;
            border: none;
            color: #ccc;
            cursor: pointer;
            font-size: 1rem;
        `;
        closeBtn.onclick = () => this.hideConnectionStats();
        statsElement.appendChild(closeBtn);

        document.body.appendChild(statsElement);
        this.connectionStatsElement = statsElement;

        // Обновляем статистику каждые 5 секунд
        this.statsUpdateInterval = setInterval(() => {
            this.updateConnectionStats();
        }, 5000);
    }

    hideConnectionStats() {
        if (this.connectionStatsElement) {
            this.connectionStatsElement.classList.add('hidden');
        }
        if (this.statsUpdateInterval) {
            clearInterval(this.statsUpdateInterval);
            this.statsUpdateInterval = null;
        }
    }

    updateConnectionStats() {
        if (!this.connectionStatsElement) return;

        const qualityElement = this.connectionStatsElement.querySelector('#overall-quality');
        const participantsElement = this.connectionStatsElement.querySelector('#participants-count');
        const connectionsElement = this.connectionStatsElement.querySelector('#connections-count');
        const reconnectElement = this.connectionStatsElement.querySelector('#reconnect-attempts');

        if (qualityElement) qualityElement.textContent = this.connectionQuality;
        if (participantsElement) participantsElement.textContent = this.participants.size;
        if (connectionsElement) connectionsElement.textContent = this.peerConnections.size;
        if (reconnectElement) reconnectElement.textContent = this.reconnectAttempts;
    }

    showQualityWarning(message, isCritical = false) {
        // Удаляем существующее предупреждение
        const existingWarning = document.querySelector('.quality-warning');
        if (existingWarning) {
            existingWarning.remove();
        }

        const warning = document.createElement('div');
        warning.className = `quality-warning ${isCritical ? 'critical' : ''}`;
        warning.textContent = message;

        document.body.appendChild(warning);

        // Автоматически скрываем через 5 секунд
        setTimeout(() => {
            if (warning.parentElement) {
                warning.remove();
            }
        }, 5000);
    }

    showReconnectingOverlay() {
        if (this.reconnectingOverlay) return;

        const overlay = document.createElement('div');
        overlay.className = 'reconnecting-overlay';
        overlay.innerHTML = `
            <div class="reconnecting-content">
                <div class="reconnecting-spinner"></div>
                <div class="reconnecting-text">Переподключение...</div>
                <div class="reconnecting-attempt">Попытка ${this.reconnectAttempts}/${this.maxReconnectAttempts}</div>
            </div>
        `;

        document.body.appendChild(overlay);
        this.reconnectingOverlay = overlay;
    }

    hideReconnectingOverlay() {
        if (this.reconnectingOverlay) {
            this.reconnectingOverlay.remove();
            this.reconnectingOverlay = null;
        }
    }

    // Обработчики сообщений
    handleUserAction(message) {
        const { user_id, action } = message;
        const participant = this.participants.get(user_id);
        
        if (participant) {
            switch (action) {
                case 'mute':
                    participant.isMuted = true;
                    break;
                case 'unmute':
                    participant.isMuted = false;
                    break;
                case 'video_on':
                    participant.isVideoEnabled = true;
                    break;
                case 'video_off':
                    participant.isVideoEnabled = false;
                    break;
            }
            
            this.updateParticipantsList();
        }
    }

    handleParticipantsList(message) {
        const { participants } = message;
        
        console.log('Получен список участников:', participants);
        
        participants.forEach(participant => {
            if (participant.user_id !== this.userId) {
                console.log(`Добавление существующего участника: ${participant.user_name} (${participant.user_id})`);
                this.addParticipant(participant.user_id, participant.user_name, false);
                
                // Создаем peer connection для существующего участника
                this.createPeerConnection(participant.user_id);
            }
        });
    }

    handleRoomStats(message) {
        // Обновляем статистику комнаты
        console.log('Статистика комнаты:', message);
    }

    closePeerConnection(userId) {
        const peerConnection = this.peerConnections.get(userId);
        if (peerConnection) {
            peerConnection.close();
            this.peerConnections.delete(userId);
        }
        
        this.removeVideoElement(userId);
        
        // Обновляем раскладку видео
        this.adjustVideoLayout();
    }
}

// Глобальная переменная для менеджера видеозвонков
let videoCallManager = null;

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    // Получаем параметры из URL
    const urlParams = new URLSearchParams(window.location.search);
    const roomCode = window.location.pathname.split('/').pop();
    const userName = urlParams.get('user') || 'Пользователь';
    
    if (roomCode && roomCode !== 'video-demo') {
        // Инициализируем видеозвонок
        videoCallManager = new VideoCallManager();
        videoCallManager.initializeCall(roomCode, userName);
    }
});
