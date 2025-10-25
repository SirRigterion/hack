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
        
        // Конфигурация ICE-серверов
        this.iceConfig = {
            iceServers: [
                { urls: 'stun:stun.l.google.com:19302' },
                { urls: 'stun:stun1.l.google.com:19302' },
                { urls: 'stun:stun2.l.google.com:19302' }
            ]
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
            // Запрашиваем доступ к камере и микрофону
            this.localStream = await navigator.mediaDevices.getUserMedia({
                video: {
                    width: { ideal: 1280, max: 1920 },
                    height: { ideal: 720, max: 1080 },
                    frameRate: { ideal: 30, max: 60 }
                },
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                }
            });
            
            console.log('Локальный поток получен:', this.localStream);
            
            // Отображаем локальный поток
            this.addVideoElement(this.userId, this.localStream, this.userName + ' (Вы)', true);
            
            console.log('Медиаустройства инициализированы');
            
        } catch (error) {
            console.error('Ошибка доступа к медиаустройствам:', error);
            throw new Error('Не удалось получить доступ к камере и микрофону');
        }
    }

    connectWebSocket() {
        return new Promise((resolve, reject) => {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const host = this.getWebSocketHost();
            const wsUrl = `${protocol}//${host}/video/ws/${this.roomCode}?user_id=${this.userId}`;
            
            console.log('Подключение к WebSocket:', wsUrl);
            this.socket = new WebSocket(wsUrl);
            
            this.socket.onopen = () => {
                console.log('WebSocket подключен');
                
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
                } catch (error) {
                    console.error('Ошибка парсинга сообщения:', error);
                }
            };
            
            this.socket.onclose = () => {
                console.log('WebSocket отключен');
                this.updateConnectionStatus('Отключено', 'red');
            };
            
            this.socket.onerror = (error) => {
                console.error('Ошибка WebSocket:', error);
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
            
            // Добавляем локальные треки
            if (this.localStream) {
                this.localStream.getTracks().forEach(track => {
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
            };
            
            this.peerConnections.set(userId, peerConnection);
            
            // Создаем offer для нового участника
            console.log(`Создание offer для ${userId}`);
            const offer = await peerConnection.createOffer();
            await peerConnection.setLocalDescription(offer);
            this.sendWebRTCSignal('offer', offer, userId);
            
        } catch (error) {
            console.error('Ошибка создания peer connection:', error);
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
            item.innerHTML = `
                <div class="participant-info">
                    <span class="participant-name">${participant.name}</span>
                    <span class="participant-status ${participant.connectionState}"></span>
                </div>
                <div class="participant-controls">
                    <span class="mute-indicator ${participant.isMuted ? 'muted' : ''}">🎤</span>
                    <span class="video-indicator ${participant.isVideoEnabled ? '' : 'disabled'}">📹</span>
                </div>
            `;
            this.participantsList.appendChild(item);
        });
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
        // Закрываем все peer connections
        this.peerConnections.forEach((peerConnection, userId) => {
            peerConnection.close();
        });
        this.peerConnections.clear();
        
        // Останавливаем локальный поток
        if (this.localStream) {
            this.localStream.getTracks().forEach(track => track.stop());
        }
        
        // Закрываем WebSocket
        if (this.socket) {
            this.socket.close();
        }
        
        // Очищаем контейнер видео
        if (this.videoContainer) {
            this.videoContainer.innerHTML = '';
        }
        
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
